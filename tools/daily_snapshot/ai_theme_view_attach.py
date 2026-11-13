"""이미 저장된 Daily Snapshot 에 AI THEME VIEW 를 붙인다(그날 저장 데이터만 · API → 세션 생성본). 바꾸는 것은 ai_regime.theme_view 하나.

    python tools/daily_snapshot/ai_theme_view_attach.py 2026-11-12 --reason "..." --by NAME

캡처 폴더의 ai_regime.json 에 붙이고, 저장본은 archive correct 로만 교체한다(이전 파일 superseded/). 앞으로의 Daily Snapshot 은 build_day.py 가 직접 만든다.
"""
import argparse, json, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from marketpulse.ai import ai_theme_view as ATV  # noqa: E402
from marketpulse.ai.client import build_client  # noqa: E402
from marketpulse.archive.service import DailyArchiveService  # noqa: E402
from marketpulse.archive.store import ArchiveStore  # noqa: E402
from marketpulse.config.settings import get_settings  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("day"); ap.add_argument("--reason", required=True); ap.add_argument("--by", default="")
a = ap.parse_args(); d = date.fromisoformat(a.day)
svc = DailyArchiveService(ArchiveStore(get_settings().archive_dir))
doc = svc.store.read(d)
cap = ROOT / "marketpulse" / "data" / "captures" / f"{d.isoformat()}-backfill"
ctx = ATV.build_context(doc["ai_regime"], semi=doc.get("semiconductor_cycle"), cockpit=doc.get("cockpit"))
(cap / "ai_theme_view_context.json").write_text(json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8")
sr = cap / "ai_theme_view_session.json"
tv = ATV.write(ctx, client=build_client(get_settings()), session_read=json.loads(sr.read_text(encoding="utf-8")) if sr.exists() else None)
print(json.dumps({k: tv[k] for k in ("source", "status", "reason", "headline")}, ensure_ascii=False))
if tv["status"] != "ok":
    raise SystemExit("생성되지 않았다 — 저장하지 않는다")
ai_cap = json.loads((cap / "ai_regime.json").read_text(encoding="utf-8")); ai_cap["theme_view"] = tv
(cap / "ai_regime.json").write_text(json.dumps(ai_cap, ensure_ascii=False), encoding="utf-8")
new = {**doc, "ai_regime": {**doc["ai_regime"], "theme_view": tv}}
final, keep = svc.correct(d, new, reason=a.reason, by=a.by)
print("correction", final.relative_to(ROOT), "이전", keep.relative_to(ROOT))
