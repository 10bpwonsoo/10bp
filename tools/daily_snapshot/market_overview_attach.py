"""이미 저장된 Daily Snapshot 에 MARKET OVERVIEW 종합을 붙인다(그날 저장 섹션만 · API → 세션 생성본). 바꾸는 것은 market_overview 섹션 하나(+ meta.sections).

    python tools/daily_snapshot/market_overview_attach.py 2026-11-12 --reason "..." --by NAME

캡처 폴더에 market_overview.json 을 쓰고, 저장본은 archive correct 로만 교체한다(이전 파일 superseded/). 앞으로의 Daily Snapshot 은 build_day.py 가 직접 만든다.
"""
import argparse, json, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from marketpulse.ai import market_overview as MO  # noqa: E402
from marketpulse.ai.client import build_client  # noqa: E402
from marketpulse.archive.service import DailyArchiveService  # noqa: E402
from marketpulse.archive.store import ArchiveStore  # noqa: E402
from marketpulse.config.settings import get_settings  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("day"); ap.add_argument("--reason", required=True); ap.add_argument("--by", default="")
a = ap.parse_args(); d = date.fromisoformat(a.day)
svc = DailyArchiveService(ArchiveStore(get_settings().archive_dir))
doc = svc.store.read(d)
cap = ROOT / "marketpulse" / "data" / "captures" / f"{d.isoformat()}-backfill"
ctx = MO.build_context(doc)
(cap / "market_overview_context.json").write_text(json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8")
sr = cap / "market_overview_session.json"
mo = MO.write(ctx, client=build_client(get_settings()), session_read=json.loads(sr.read_text(encoding="utf-8")) if sr.exists() else None)
print(json.dumps({k: mo[k] for k in ("source", "status", "reason")}, ensure_ascii=False), (mo.get("view") or {}).get("headline"))
if mo["status"] != "ok":
    raise SystemExit("생성되지 않았다 — 저장하지 않는다")
(cap / "market_overview.json").write_text(json.dumps(mo, ensure_ascii=False), encoding="utf-8")
meta = dict(doc.get("meta") or {})
if isinstance(meta.get("sections"), dict):
    meta["sections"] = {**meta["sections"], "market_overview": "OK"}
final, keep = svc.correct(d, {**doc, "market_overview": mo, "meta": meta}, reason=a.reason, by=a.by)
print("correction", final.relative_to(ROOT), "이전", keep.relative_to(ROOT))
