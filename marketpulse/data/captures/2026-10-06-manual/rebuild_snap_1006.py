"""10/6 캡처의 series_live.json(4개 금리 계열 병합본)으로 /tmp/snap 의 pkl 두 개를 다시 만든다. as_of 는 원래 수집 시각."""
import json, pickle
from datetime import datetime
from pathlib import Path
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.normalize import build_snapshot
from marketpulse.models.common import DataMode
from marketpulse.models.market import MarketSeries
CAP = Path("marketpulse/data/captures/2026-10-06-manual")
rep = json.loads((CAP / "fetch_report.json").read_text(encoding="utf-8"))
as_of = datetime.fromisoformat(rep["as_of"])
raw = json.loads((CAP / "series_live.json").read_text(encoding="utf-8"))
series = {k: MarketSeries.model_validate(v) for k, v in raw.items()}
ins = get_instruments().instruments
snap = build_snapshot(ins, series, mode=DataMode.DELAYED, as_of=as_of, zscore_window=Settings().zscore_window)
pickle.dump(snap, open("/tmp/snap/market_snapshot.pkl", "wb")); pickle.dump(series, open("/tmp/snap/series_live.pkl", "wb"))
print("as_of", snap.as_of, "series", len(series), "missing", snap.missing)
for k in ["US2Y", "US5Y", "US10Y", "US30Y", "BE5Y", "BE10Y", "TIPS5Y", "TIPS10Y", "CURVE_2S10S", "MOVE"]:
    f = snap.features.get(k) if hasattr(snap, "features") else None
    print(k, f and (round(f.z_1d, 2) if f.z_1d is not None else None, round(f.z_5d, 2) if f.z_5d is not None else None, getattr(f, "last", None)))
