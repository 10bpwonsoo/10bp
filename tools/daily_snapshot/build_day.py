"""Daily Snapshot 한 날짜 재구성 — 그 날짜 07:30 KST cutoff(historical_backfill 규칙). 오늘 날짜여도 '지금 데이터' 저장이 아니다.

    python tools/daily_snapshot/build_day.py 2026-11-11 <inputs_dir> context   # 컨텍스트만(history 복사본 위, 저장 안 함) — 해석 세션본 작성용
    python tools/daily_snapshot/build_day.py 2026-11-11 <inputs_dir> full      # 저장(archive · history 행 · 캡처)

캡처 폴더 marketpulse/data/captures/<날짜>-backfill/ 에 manual_tags.json · *_session.json 이 있으면 쓴다.
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from marketpulse.archive.backfill import build_one  # noqa: E402
from marketpulse.archive.reconstruct import cutoff_for  # noqa: E402
from marketpulse.archive.service import DailyArchiveService  # noqa: E402
from marketpulse.archive.store import ArchiveStore  # noqa: E402
from marketpulse.config.settings import get_settings  # noqa: E402

d = date.fromisoformat(sys.argv[1])
inputs = Path(sys.argv[2])
ctx = (sys.argv[3] if len(sys.argv) > 3 else "context") == "context"
svc = DailyArchiveService(ArchiveStore(get_settings().archive_dir))
cut = cutoff_for(d, str(svc.cfg.get("cutoff_time", "07:30")))
print("cutoff", cut.isoformat())
res, cap = build_one(svc, d, inputs=inputs, cutoff=cut, latest=False, context_only=ctx)
print("CONTEXT ONLY" if cap is None else cap.line(),
      json.dumps({k: res.summary.get(k) for k in ("market", "ai", "rates", "oil", "news", "semiconductor_cycle", "cockpit")}, ensure_ascii=False, default=str))
