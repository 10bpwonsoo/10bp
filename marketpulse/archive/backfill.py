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

from .input_status import summary_of
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


def build_one(svc: DailyArchiveService, day: date, *, inputs: Path, cutoff: datetime, latest: bool, context_only: bool = False,
              input_status: dict[str, Any] | None = None):
    """한 날짜 재구성. context_only 면 history 복사본 위에서 돌려 금리 해석 컨텍스트만 남기고 저장하지 않는다.

    input_status  archive.input_status.assess() 결과. 주면 STALE 계열을 계산에서 빼고, 판정 요약을 캡처 폴더와 저장본 meta 에 남긴다.
                  판정이 PARTIAL 인데 저장하려 하면 거절한다 — 그날은 build_partial 로 따로 저장한다.
    """
    from ..config.settings import get_settings
    from ..history import DailySnapshotManager, JsonDirStore
    from .collect import capture_dir_collectors
    from .reconstruct import fetch_macro_vintage, reconstruct

    if input_status is not None and not context_only and (input_status.get("gate") or {}).get("verdict") != "FULL":
        raise PartialInputsError("핵심 입력이 모자라 확정 저장을 하지 않습니다 — " + " · ".join((input_status.get("gate") or {}).get("reasons") or []))
    out = capture_dir_for(day, latest=latest)
    out.mkdir(parents=True, exist_ok=True)
    if input_status is not None:
        (out / "input_status.json").write_text(json.dumps(input_status, ensure_ascii=False, indent=1), encoding="utf-8")
    if not (out / "macro_raw.json").exists():
        fetch_macro_vintage(out / "macro_raw.json", cutoff)
    tags = json.loads((out / "manual_tags.json").read_text(encoding="utf-8"))["tags"] if (out / "manual_tags.json").exists() else {}
    extra = json.loads((out / "extra_news.json").read_text(encoding="utf-8")) if (out / "extra_news.json").exists() else []
    reads = {k: json.loads((out / f"{k}_session.json").read_text(encoding="utf-8")) for k in ("rates_read", "inflation_read", "semiconductor_read", "semiconductor_cycle_read", "regime_select", "transition_read", "ai_theme_view", "market_overview") if (out / f"{k}_session.json").exists()}
    prev = _previous_archive(svc, day)
    since = _ts(((prev or {}).get("meta") or {}).get("source_asof")) if prev else None
    hist_dir = get_settings().history_dir
    state_dir = get_settings().regime_state_dir
    tmp = None
    if context_only:
        tmp = Path(tempfile.mkdtemp(prefix="history-dry-"))
        shutil.copytree(hist_dir, tmp / "h")
        hist_dir = tmp / "h"
        if state_dir.exists():
            shutil.copytree(state_dir, tmp / "rs")
        state_dir = tmp / "rs"
    try:
        res = reconstruct(day, inputs=inputs, out=out, cutoff=cutoff, tags=tags, extra_news=extra,
                          previous_investment=(prev or {}).get("investment"), news_since=since,
                          origin="latest_update" if latest else "historical_backfill", session_reads=reads,
                          manager=DailySnapshotManager(JsonDirStore(hist_dir)),
                          previous_official=(((prev or {}).get("cockpit") or {}).get("history") or {}).get("current_label"), regime_state_dir=state_dir,
                          drop=(input_status or {}).get("stale"))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    if context_only:
        return res, None
    manifest = res.summary
    had_partial = svc.store.partial_path(day).is_file()
    extra_meta = {
        **({"input_status": summary_of(input_status)} if input_status is not None else {}),
        **({"finalized_from_partial": {"partial_generated_at": svc.store.read_partial(day).get("generated_at"),
                                       "note": "이 날짜는 먼저 PARTIAL 로 저장됐고, 정상 입력을 받은 뒤 확정 저장본을 새로 만들었다. PARTIAL 파일은 superseded/ 에 남긴다"}} if had_partial else {}),
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
    if had_partial and result.status == "WRITTEN":
        svc.store.retire_partial(day)
    return res, result


class PartialInputsError(RuntimeError):
    """핵심 입력이 모자라다 — 확정 저장(full)을 하지 않는다. build_partial 로 따로 저장한다."""


def partial_capture_dir(day: date) -> Path:
    return PKG / "data" / "captures" / f"{day.isoformat()}-partial"


def build_partial(svc: DailyArchiveService, day: date, *, inputs: Path, cutoff: datetime, input_status: dict[str, Any]):
    """
    PARTIAL 스냅샷 — 핵심 입력이 모자란 날, 받은 데이터만으로 계산해 **따로** 저장한다(archive/partial/<날짜>.json).

    지키는 것
      · history(data/history) · regime 상태 로그(data/regime_state) · 확정 저장본(archive/YYYY/MM) 은 읽기만 한다. 계산은 복사본 위에서 돈다.
      · 오늘의 REGIME 선택을 하지 않는다(hold_regime). 공식 regime 은 직전 확정 스냅샷의 값 그대로이고, 그 사실을 meta.regime_decision 에 적는다.
      · STALE 계열은 뺀다. 못 받은 계열은 결측이다. 0 · 보간 · 전날 값으로 채우지 않는다.
      · 나중에 정상 입력을 받으면 build_one(full) 이 확정 저장본을 새로 만들고, 이 파일은 superseded/ 로 옮겨 남긴다.
    """
    from ..config.settings import get_settings
    from ..history import DailySnapshotManager, JsonDirStore
    from .collect import capture_dir_collectors
    from .input_status import summary_of
    from .reconstruct import fetch_macro_vintage, reconstruct

    if svc.store.exists(day):
        raise RuntimeError(f"{day} 확정 저장본이 이미 있습니다 — PARTIAL 을 만들지 않습니다")
    src = capture_dir_for(day, latest=False)   # 기사 태그는 그날 작업 폴더의 것을 읽는다(같은 날 · 같은 기사)
    out = partial_capture_dir(day)
    out.mkdir(parents=True, exist_ok=True)
    (out / "input_status.json").write_text(json.dumps(input_status, ensure_ascii=False, indent=1), encoding="utf-8")
    if not (out / "macro_raw.json").exists():
        if (src / "macro_raw.json").exists():
            shutil.copy(src / "macro_raw.json", out / "macro_raw.json")
        else:
            fetch_macro_vintage(out / "macro_raw.json", cutoff)
    tags_file = out / "manual_tags.json" if (out / "manual_tags.json").exists() else src / "manual_tags.json"
    tags = json.loads(tags_file.read_text(encoding="utf-8"))["tags"] if tags_file.exists() else {}
    extra_file = out / "extra_news.json" if (out / "extra_news.json").exists() else src / "extra_news.json"
    extra = json.loads(extra_file.read_text(encoding="utf-8")) if extra_file.exists() else []
    # 해석 세션본은 이 PARTIAL 폴더에 직접 쓴 것만 쓴다. regime 선택 · 전환 해설은 보류라 읽지 않는다
    reads = {k: json.loads((out / f"{k}_session.json").read_text(encoding="utf-8")) for k in ("rates_read", "inflation_read", "semiconductor_read", "semiconductor_cycle_read", "ai_theme_view", "market_overview") if (out / f"{k}_session.json").exists()}
    prev = _previous_archive(svc, day)
    since = _ts(((prev or {}).get("meta") or {}).get("source_asof")) if prev else None
    prev_official = (((prev or {}).get("cockpit") or {}).get("history") or {}).get("current_label")
    tmp = Path(tempfile.mkdtemp(prefix="partial-dry-"))
    try:
        shutil.copytree(get_settings().history_dir, tmp / "h")
        if get_settings().regime_state_dir.exists():
            shutil.copytree(get_settings().regime_state_dir, tmp / "rs")
        res = reconstruct(day, inputs=inputs, out=out, cutoff=cutoff, tags=tags, extra_news=extra, previous_investment=(prev or {}).get("investment"),
                          news_since=since, origin="partial_snapshot", session_reads=reads, manager=DailySnapshotManager(JsonDirStore(tmp / "h")),
                          previous_official=prev_official, regime_state_dir=tmp / "rs", drop=input_status.get("stale"), hold_regime=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    gate = input_status.get("gate") or {}
    extra_meta = {
        "snapshot_kind": "PARTIAL_INPUTS",
        "input_status": summary_of(input_status),
        "regime_decision": {"status": "HELD", "reasons": gate.get("reasons") or [], "official_regime": prev_official,
                            "official_as_of": (prev or {}).get("snapshot_date"),
                            "note": "핵심 입력이 모자라 오늘의 regime 판정을 보류했다. 공식 regime 은 직전 확정 스냅샷의 값 그대로다. 이 문서의 market_state · cockpit 에 있는 "
                                    "regime 값은 받은 데이터만으로 계산한 잠정치이며 history · regime 상태 로그에 쓰지 않았다."},
        "cutoff_rule": "그 한국 날짜 07:30 KST 에 이미 끝나 공개된 봉·발행된 기사·발표된 지표만",
        "data_vintage": res.summary.get("vintage"), "news_coverage": res.summary.get("news"), "capture_dir": str(out.relative_to(PKG)),
        "finalize": "정상 입력을 받으면 tools/daily_snapshot/build_day.py <날짜> <inputs> full 로 확정 저장본을 만든다(이 파일은 superseded/ 로 옮겨 남는다)",
    }
    payload = svc.build(now=cutoff, collectors=capture_dir_collectors(out), created_by="partial_snapshot", origin="partial_snapshot", cutoff=cutoff,
                        check_future=True, extra_meta=extra_meta)
    payload["archive_status"] = "PARTIAL"
    path, replaced = svc.store.write_partial(day, payload)
    return res, {"path": path, "replaced": replaced, "errors": dict(payload.get("errors") or {})}
