"""9/29 캡처에 FRED 금리 계열 4개(US5Y·BE5Y·TIPS10Y·TIPS5Y)를 보탠다 — 기존 series_live.json 은 그대로 두고 새 계열만 붙인다.

FRED 일간 계열은 수집 시각과 무관하게 같은 값이므로 원래 as_of(00:45 UTC) 를 그대로 쓴다. 키 값은 출력하지 않는다.
"""
import json, os
from datetime import datetime
from pathlib import Path
from marketpulse.adapters.registry import build_market_adapter
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings

OUT = Path(__file__).resolve().parent
print("FRED key present:", bool(os.environ.get("FRED_API_KEY")))
rep = json.loads((OUT / "fetch_report.json").read_text(encoding="utf-8"))
as_of = datetime.fromisoformat(rep["as_of"])
want = ["US5Y", "BE5Y", "TIPS10Y", "TIPS5Y"]
ins = [i for i in get_instruments().instruments if i.id in want]
settings = Settings(data_mode="DELAYED", llm_enabled=False)
adapter = build_market_adapter(settings)
got = adapter.fetch_series(ins, bars=settings.history_bars, as_of=as_of)
failed = [(k, o.reason) for k, o in getattr(adapter, "outcomes", {}).items() if not o.ok]
print("got", sorted(got), "failed", failed)
for iid, s in got.items():
    print(iid, "bars", len(s.values), "last", s.timestamps[-1].date().isoformat(), s.values[-1])
raw = json.loads((OUT / "series_live.json").read_text(encoding="utf-8"))
for iid, s in got.items():
    raw[iid] = s.model_dump(mode="json")
(OUT / "series_live.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
rep["extra_rates"] = {"got": sorted(got), "failed": failed}
(OUT / "fetch_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
print("merged", len(raw), "series")
