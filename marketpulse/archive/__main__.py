"""
    python -m marketpulse.archive capture [--if-due] [--dir DIR]       지금 화면 전체를 저장 (같은 날짜가 있으면 건너뜀)
    python -m marketpulse.archive import-capture DIR [DIR ...]         커밋된 캡처 디렉터리를 그날 저장본으로 가져옴 (있으면 건너뜀)
    python -m marketpulse.archive list                                  저장된 날짜 · 상태
    python -m marketpulse.archive show 2026-10-15                       한 날짜 요약
    python -m marketpulse.archive correct 2026-10-15 --file F --reason "..." --by NAME   명시적 correction (이전 파일은 superseded/)

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
    p.add_argument("cmd", choices=["capture", "import-capture", "list", "show", "correct"])
    p.add_argument("args", nargs="*")
    p.add_argument("--dir", default=None, help="archive 디렉터리 (기본 settings.archive_dir)")
    p.add_argument("--if-due", action="store_true", help="정기 저장 시각이 지났고 오늘 저장본이 없을 때만")
    p.add_argument("--file"); p.add_argument("--reason", default=""); p.add_argument("--by", default="admin")
    a = p.parse_args(argv)

    from ..config.settings import get_settings
    settings = get_settings()
    svc = DailyArchiveService(ArchiveStore(Path(a.dir) if a.dir else settings.archive_dir))

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
            res = svc.capture(now=capture_dir_asof(directory), collectors=capture_dir_collectors(directory),
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
