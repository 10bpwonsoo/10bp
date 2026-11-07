"""10/14 캡처 보정 — 일괄 수집에서 Yahoo 환율 3종(USDKRW · USDJPY · EURUSD)의 최근 봉이 빠졌다(10/12 23:00 UTC 봉까지만).
단독으로 다시 받아 더 최근 봉이면 바꾼다. 더 오래된 값으로 바꾸지 않는다. 키는 쓰지 않는다."""
import json
from pathlib import Path
from marketpulse.adapters.registry import build_market_adapter
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.models.common import utcnow
from marketpulse.models.market import MarketSeries
OUT = Path(__file__).resolve().parent
want = ("USDKRW", "USDJPY", "EURUSD")
raw = json.loads((OUT / "series_live.json").read_text(encoding="utf-8"))
s = Settings(data_mode="DELAYED", llm_enabled=False)
got = build_market_adapter(s).fetch_series([i for i in get_instruments().instruments if i.id in want], bars=s.history_bars, as_of=utcnow())
changed = []
for iid, ser in got.items():
    old = MarketSeries.model_validate(raw[iid])
    if ser.timestamps and ser.timestamps[-1] > old.timestamps[-1]:
        raw[iid] = ser.model_dump(mode="json"); changed.append((iid, ser.meta.source, ser.timestamps[-1].isoformat()[:16], round(ser.values[-1], 3)))
print("replaced", changed)
(OUT / "series_live.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
rep = json.loads((OUT / "fetch_report.json").read_text(encoding="utf-8")); rep["refetch_fx"] = changed
(OUT / "fetch_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
