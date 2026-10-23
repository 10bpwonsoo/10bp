"""
누락 평일 backfill — 기존 저장본은 보존하고, 토·일을 제외한 빠진 평일만 오름차순으로 채운다.

    plan(store, until)   기존 저장본 최소 날짜 ~ until 의 모든 날짜를 EXISTING · MISSING · SKIPPED_WEEKEND 로 분류
    run(...)             MISSING 을 오래된 날짜부터: 그 날짜 cutoff(07:30 KST) 재구성 → 검증(미래 데이터) → 원자적 저장 → index 갱신.
                         until 이 오늘이면 그날은 과거 재구성이 아니라 지금 데이터로 만든 최신 저장(latest_update)이다.
이미 있는 날짜는 다시 계산하지도, 덮어쓰지도 않는다(EXISTING). 토·일 파일은 만들지 않는다(이미 있으면 그대로 둔다).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .service import DailyArchiveService, skip_reason

PKG = Path(__file__).resolve().parent.parent


def plan(svc: DailyArchiveService, until: date, start: date | None = None) -> list[dict[str, Any]]:
    existing = set(svc.store.dates())
    start = start or (min(existing) if existing else until)
    rows: list[dict[str, Any]] = []
    d = start
    while d <= until:
        why = skip_reason(d, svc.cfg)
        if d in existing:
            action = "EXISTING"   # 주말 파일이 이미 있어도 지우거나 바꾸지 않는다
        elif why:
            action = f"SKIPPED_{why}"
        else:
            action = "MISSING"
        rows.append({"date": d, "weekday": d.strftime("%a"), "action": action})
        d += timedelta(days=1)
    return rows


def capture_dir_for(day: date, *, latest: bool) -> Path:
    return PKG / "data" / "captures" / f"{day.isoformat()}-{'latest' if latest else 'backfill'}"


def _previous_archive(svc: DailyArchiveService, day: date) -> dict[str, Any] | None:
    prev = [d for d in svc.store.dates() if d < day]
    return svc.store.read(max(prev)) if prev else None


def _ts(text: Any) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def build_one(svc: DailyArchiveService, day: date, *, inputs: Path, cutoff: datetime, latest: bool, context_only: bool = False):
    """한 날짜 재구성. context_only 면 history 복사본 위에서 돌려 금리 해석 컨텍스트만 남기고 저장하지 않는다."""
    from ..config.settings import get_settings
    from ..history import DailySnapshotManager, JsonDirStore
    from .collect import capture_dir_collectors
    from .reconstruct import fetch_macro_vintage, reconstruct

    out = capture_dir_for(day, latest=latest)
    out.mkdir(parents=True, exist_ok=True)
    if not (out / "macro_raw.json").exists():
        fetch_macro_vintage(out / "macro_raw.json", cutoff)
    tags = json.loads((out / "manual_tags.json").read_text(encoding="utf-8"))["tags"] if (out / "manual_tags.json").exists() else {}
    extra = json.loads((out / "extra_news.json").read_text(encoding="utf-8")) if (out / "extra_news.json").exists() else []
    reads = {k: json.loads((out / f"{k}_session.json").read_text(encoding="utf-8")) for k in ("rates_read", "inflation_read", "semiconductor_read") if (out / f"{k}_session.json").exists()}
    prev = _previous_archive(svc, day)
    since = _ts(((prev or {}).get("meta") or {}).get("source_asof")) if prev else None
    hist_dir = get_settings().history_dir
    tmp = None
    if context_only:
        tmp = Path(tempfile.mkdtemp(prefix="history-dry-"))
        shutil.copytree(hist_dir, tmp / "h")
        hist_dir = tmp / "h"
    try:
        res = reconstruct(day, inputs=inputs, out=out, cutoff=cutoff, tags=tags, extra_news=extra,
                          previous_investment=(prev or {}).get("investment"), news_since=since,
                          origin="latest_update" if latest else "historical_backfill", session_reads=reads,
                          manager=DailySnapshotManager(JsonDirStore(hist_dir)))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    if context_only:
        return res, None
    manifest = res.summary
    extra_meta = {
        "cutoff_rule": "그 한국 날짜 07:30 KST 에 이미 끝나 공개된 봉·발행된 기사·발표된 지표만" if not latest else "저장 시각에 받을 수 있던 최신 데이터(오늘 최신 저장)",
        "data_vintage": manifest.get("vintage"),
        "news_coverage": manifest.get("news"),
        "llm": {"rates_market_read": manifest.get("rates", {}).get("market_read"), "inflation_read": manifest.get("rates", {}).get("inflation_read"),
                "semiconductor_market_read": (manifest.get("semiconductor_cycle") or {}).get("market_read"),
                "api_status": "API 호출 실패 시 같은 컨텍스트·프롬프트·검증의 세션 생성본 → 없으면 규칙 문장(화면에 출처 표시)"},
        "capture_dir": str(out.relative_to(PKG)),
        "policy_events_file": "data/policy_events — 그 날짜 이하 가장 최근 수기 파일(일정은 as_of 로 다시 거름)",
    }
    result = svc.capture(now=cutoff, collectors=capture_dir_collectors(out), created_by="historical_backfill" if not latest else "latest_update",
                         origin="latest_update" if latest else "historical_backfill", cutoff=cutoff, check_future=True, extra_meta=extra_meta)
    return res, result
