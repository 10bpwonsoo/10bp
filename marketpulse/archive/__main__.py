"""
    python -m marketpulse.archive capture [--if-due] [--dir DIR]       지금 화면 전체를 저장 (같은 날짜가 있으면 건너뜀)
    python -m marketpulse.archive import-capture DIR [DIR ...]         커밋된 캡처 디렉터리를 그날 저장본으로 가져옴 (있으면 건너뜀)
    python -m marketpulse.archive list                                  저장된 날짜 · 상태
    python -m marketpulse.archive show 2026-10-15                       한 날짜 요약
    python -m marketpulse.archive correct 2026-10-15 --file F --reason "..." --by NAME   명시적 correction (이전 파일은 superseded/)
    python -m marketpulse.archive plan [--until 2026-10-21]             기존 저장본 · 빠진 평일 · 건너뛸 주말 표
    python -m marketpulse.archive fetch-inputs DIR                      backfill 입력(시장·종목·AI 바스켓 계열, RSS)을 지금 한 번 받는다
    python -m marketpulse.archive backfill --inputs DIR [--until D] [--date D] [--context-only]
                                                                        빠진 평일만 오래된 날짜부터 그 날짜 07:30 KST 기준으로 재구성·저장.
                                                                        until 이 오늘이면 오늘은 지금 데이터로 만든 최신 저장(latest_update)

capture 는 MARKETPULSE_DATA_MODE 등 API 서버와 같은 설정으로 수집한다. --if-due 는 config/archive.yaml 의
archive_time(기본 07:30 Asia/Seoul)이 지났고 오늘 저장본이 없을 때만 저장한다 — cron · GitHub Actions 가 이것을 부른다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .collect import capture_dir_asof, capture_dir_collectors, live_collectors
from .service import ArchiveCaptureError, DailyArchiveService
from .store import ArchiveStore, parse_date


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="marketpulse.archive")
    p.add_argument("cmd", choices=["capture", "import-capture", "list", "show", "correct", "plan", "fetch-inputs", "backfill", "validate"])
    p.add_argument("--until"); p.add_argument("--date"); p.add_argument("--inputs"); p.add_argument("--context-only", action="store_true")
    p.add_argument("--cutoff", help="오늘 최신 저장의 기준 시각(ISO). 없으면 지금 — 입력을 받은 시각으로 고정하면 미리보기와 저장이 같은 시점을 쓴다")
    p.add_argument("args", nargs="*")
    p.add_argument("--dir", default=None, help="archive 디렉터리 (기본 settings.archive_dir)")
    p.add_argument("--if-due", action="store_true", help="정기 저장 시각이 지났고 오늘 저장본이 없을 때만")
    p.add_argument("--file"); p.add_argument("--reason", default=""); p.add_argument("--by", default="admin")
    a = p.parse_args(argv)

    from ..config.settings import get_settings
    settings = get_settings()
    svc = DailyArchiveService(ArchiveStore(Path(a.dir) if a.dir else settings.archive_dir))

    if a.cmd in ("plan", "backfill"):
        from zoneinfo import ZoneInfo
        from .backfill import build_one, plan
        from .reconstruct import cutoff_for
        today = datetime.now(timezone.utc).astimezone(ZoneInfo(str(svc.cfg.get("timezone", "Asia/Seoul")))).date()
        until = parse_date(a.until) if a.until else today
        rows = plan(svc, until)
        if a.cmd == "plan":
            print("DATE        DAY  ACTION")
            for r in rows:
                print(f"{r['date']}  {r['weekday']}  {r['action']}")
            return 0
        if not a.inputs:
            print("backfill 에는 --inputs 가 필요합니다 (fetch-inputs 로 먼저 받는다)", file=sys.stderr)
            return 2
        todo = [r["date"] for r in rows if r["action"] == "MISSING" and (a.date is None or r["date"].isoformat() == a.date)]
        for r in rows:
            if r["action"] != "MISSING":
                print(f"{r['date']} {r['action'].replace('_', ' - ', 1) if r['action'].startswith('SKIPPED') else r['action']}")
        for d in sorted(todo):  # 반드시 과거 → 미래
            latest = d == today
            cutoff = (datetime.fromisoformat(a.cutoff) if a.cutoff else datetime.now(timezone.utc)) if latest else cutoff_for(d, str(svc.cfg.get("cutoff_time", "07:30")))
            res, cap = build_one(svc, d, inputs=Path(a.inputs), cutoff=cutoff, latest=latest, context_only=a.context_only)
            print(f"{d} {'CONTEXT ONLY' if cap is None else cap.line()} · {json.dumps({k: res.summary.get(k) for k in ('market', 'ai', 'rates', 'oil', 'news')}, ensure_ascii=False, default=str)}")
        return 0
    if a.cmd == "fetch-inputs":
        from .reconstruct import fetch_inputs
        print(json.dumps(fetch_inputs(Path(a.args[0])), ensure_ascii=False, indent=1, default=str)[:3000])
        return 0
    if a.cmd == "validate":
        from .service import future_data_paths, skip_reason
        from .store import parse_date as _pd
        day = _pd(a.args[0]) if a.args else svc.archive_date(datetime.now(timezone.utc))
        if not svc.store.exists(day):
            print(f"{day} 저장본 없음 — {'SKIPPED ' + skip_reason(day, svc.cfg) if skip_reason(day, svc.cfg) else '아직 저장되지 않음'}")
            return 0 if skip_reason(day, svc.cfg) else 1
        doc = svc.get(day)
        problems = []
        if not doc.get("schema_version"):
            problems.append("schema_version 없음")
        if doc.get("snapshot_date") != day.isoformat():
            problems.append("snapshot_date 불일치")
        if day.weekday() >= 5:
            problems.append("주말 저장본")
        cut = doc.get("cutoff")
        if cut:
            t = datetime.fromisoformat(str(cut))
            for name in svc.cfg.get("sections") or []:
                bad = future_data_paths(doc.get(name), t, path=name) if doc.get(name) is not None else []
                if bad:
                    problems.append(f"{name}: cutoff 뒤 데이터 {bad[:2]}")
        print(f"{day} {doc.get('archive_status')} · sections {json.dumps((doc.get('meta') or {}).get('sections'), ensure_ascii=False)}")
        for p in problems:
            print("  PROBLEM", p)
        return 1 if problems else 0
    if a.cmd == "list":
        for r in svc.index():
            print(r["date"], str(r.get("archive_status")).ljust(9), str(r.get("data_mode")).ljust(8), r.get("source_asof"), r.get("created_by"), ("missing " + ",".join(r["missing"])) if r.get("missing") else "")
        return 0
    if a.cmd == "show":
        doc = svc.get(a.args[0])
        print(json.dumps({k: doc.get(k) for k in ("schema_version", "snapshot_date", "generated_at", "archive_status", "errors", "meta")}, ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "capture":
        now = datetime.now(timezone.utc)
        if a.if_due and not svc.due(now):
            print(f"정기 저장 시각 전이거나 오늘({svc.archive_date(now)}) 저장본이 이미 있음 — 건너뜀")
            return 0
        try:
            res = svc.capture(now=now, collectors=live_collectors(settings))
        except ArchiveCaptureError as exc:
            print(f"저장 실패: {exc}", file=sys.stderr)
            return 2
        print(res.line())
        return 0
    if a.cmd == "import-capture":
        for d in a.args:
            directory = Path(d)
            res = svc.capture(now=capture_dir_asof(directory), collectors=capture_dir_collectors(directory), origin="capture_import",
                              created_by=f"capture_import:{directory.name}", generated_at_basis="snapshot.as_of (imported capture)")
            print(res.line())
        return 0
    if a.cmd == "correct":
        if not a.file or not a.reason:
            print("correct 에는 --file 과 --reason 이 필요합니다", file=sys.stderr)
            return 2
        final, keep = svc.correct(parse_date(a.args[0]), json.loads(Path(a.file).read_text(encoding="utf-8")), reason=a.reason, by=a.by)
        print(f"교체: {final} · 이전 파일: {keep}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
