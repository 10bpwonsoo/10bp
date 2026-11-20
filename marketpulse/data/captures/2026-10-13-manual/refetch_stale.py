"""10/13 캡처 보정 — 일괄 수집에서 Yahoo 가 일시 실패해 오래된 대체 계열(CSV 등)로 떨어진 계열만 한 번 더 받아, 더 최근 봉이면 바꾼다.
키는 환경변수로만 읽고 출력하지 않는다. 더 오래된 값으로 바꾸지 않는다."""
import json, time
from pathlib import Path
from marketpulse.adapters.registry import build_market_adapter
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.models.common import utcnow
from marketpulse.models.market import MarketSeries
OUT = Path(__file__).resolve().parent
raw = json.loads((OUT / "series_live.json").read_text(encoding="utf-8"))
stale = [k for k, v in raw.items() if (v.get("meta") or {}).get("is_stale") and not str((v.get("meta") or {}).get("source", "")).startswith(("yahoo", "fred"))]
print("stale fallback series", stale)
settings = Settings(data_mode="DELAYED", llm_enabled=False); ad = build_market_adapter(settings)
ins = [i for i in get_instruments().instruments if i.id in stale]
time.sleep(2)
got = ad.fetch_series(ins, bars=settings.history_bars, as_of=utcnow()) if ins else {}
changed = []
for iid, s in got.items():
    old = MarketSeries.model_validate(raw[iid])
    if s.timestamps and s.timestamps[-1] > old.timestamps[-1]:
        raw[iid] = s.model_dump(mode="json"); changed.append((iid, s.meta.source, s.timestamps[-1].isoformat()[:16]))
print("replaced", changed)
(OUT / "series_live.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
rep = json.loads((OUT / "fetch_report.json").read_text(encoding="utf-8")); rep["refetch_stale"] = changed
(OUT / "fetch_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
