"""이미 저장된 Daily Snapshot 에 반도체 사이클 CYCLE READ 를 붙인다(그날 저장 데이터만 · API → 세션 생성본). 바꾸는 것은 semiconductor_cycle.cycle_read 하나.

    python tools/daily_snapshot/semi_cycle_read_attach.py 2026-11-24 --reason "..." --by NAME [--context-only]

--context-only 는 캡처 폴더에 semiconductor_cycle_read_context.json 만 쓴다(세션본 작성용). 저장본은 archive correct 로만 교체한다(이전 파일 superseded/).
앞으로의 Daily Snapshot 은 build_day.py 가 직접 만든다.
"""
import argparse, json, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from marketpulse.ai import semi_cycle_read as CR  # noqa: E402
from marketpulse.ai.client import build_client  # noqa: E402
from marketpulse.archive.service import DailyArchiveService  # noqa: E402
from marketpulse.archive.store import ArchiveStore  # noqa: E402
from marketpulse.config.settings import get_settings  # noqa: E402
from marketpulse.engines.semiconductor_cycle import load_config  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("day"); ap.add_argument("--reason", default=""); ap.add_argument("--by", default=""); ap.add_argument("--context-only", action="store_true")
a = ap.parse_args(); d = date.fromisoformat(a.day)
svc = DailyArchiveService(ArchiveStore(get_settings().archive_dir))
doc = svc.store.read(d)
if not doc.get("semiconductor_cycle"):
    raise SystemExit("이 날짜 저장본에는 반도체 사이클 섹션이 없다")
cap = ROOT / "marketpulse" / "data" / "captures" / f"{d.isoformat()}-backfill"
semi = {k: v for k, v in doc["semiconductor_cycle"].items() if k != "cycle_read"}
ctx = CR.build_context(semi, load_config().get("regime") or {})
(cap / "semiconductor_cycle_read_context.json").write_text(json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8")
if a.context_only:
    raise SystemExit(0)
if not a.reason:
    raise SystemExit("--reason 이 필요하다")
sr = cap / "semiconductor_cycle_read_session.json"
out = CR.attach_cycle_read(dict(semi), json.loads(sr.read_text(encoding="utf-8")) if sr.exists() else None, client=build_client(get_settings()))
cr = out["cycle_read"]
print(json.dumps({k: cr[k] for k in ("source", "status", "generator", "reason", "verdict")}, ensure_ascii=False), cr["warnings"])
if cr["status"] != "ok":
    raise SystemExit("생성되지 않았다 — 저장하지 않는다")
assert {k: v for k, v in out.items() if k != "cycle_read"} == semi  # 국면 · 점수 · 다른 필드는 그대로
cap_semi = json.loads((cap / "semiconductor_cycle.json").read_text(encoding="utf-8")); cap_semi["cycle_read"] = cr
(cap / "semiconductor_cycle.json").write_text(json.dumps(cap_semi, ensure_ascii=False), encoding="utf-8")
final, keep = svc.correct(d, {**doc, "semiconductor_cycle": {**doc["semiconductor_cycle"], "cycle_read": cr}}, reason=a.reason, by=a.by)
print("correction", final.relative_to(ROOT), "이전", keep.relative_to(ROOT))
