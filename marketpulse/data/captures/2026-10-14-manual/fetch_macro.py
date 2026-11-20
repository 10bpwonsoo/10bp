"""macro fallback layer 원자료 수집(2026-10-14) — FRED API(PRIMARY) → FRED CSV(MIRROR). 결과는 macro_raw.json. 키 값은 출력하지 않는다."""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path
from marketpulse.adapters.macro_fred import fetch_macro_raw
from marketpulse.engines.macro_fallback import load_macro_config
from marketpulse.models.snapshot import IntelligenceSnapshot
CAP = Path(sys.argv[1])
live = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
print("FRED key present:", bool(os.environ.get("FRED_API_KEY")))
raw = fetch_macro_raw(load_macro_config(), api_key=os.environ.get("FRED_API_KEY"), as_of=live.as_of)
(CAP / "macro_raw.json").write_text(json.dumps({"as_of": live.as_of.isoformat(), "fetched_at": datetime.now(timezone.utc).isoformat(), "series": raw}, ensure_ascii=False), encoding="utf-8")
for k, v in raw.items():
    obs = [o for o in v["observations"] if o[1] is not None]
    print(k, v["path"], v["vintage"], v["error"], obs[-1] if obs else None, len(obs))
