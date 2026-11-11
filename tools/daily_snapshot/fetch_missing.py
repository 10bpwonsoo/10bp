"""사용: fetch_missing.py <out_dir> <기준 inputs(빠짐 판정용, 보통 전날)> <지금까지 합친 inputs> [간격초]
빠진 계열만 하나씩, 요청 사이 간격을 두고 받는다(Yahoo 429 회피). 값은 공급자 응답 그대로."""
import json, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from marketpulse.archive.reconstruct import _dump_series
from marketpulse.config.settings import Settings, get_settings
from marketpulse.config.registry import get_instruments, get_universe
from marketpulse.adapters.registry import build_market_adapter, build_alt_adapter
from marketpulse.models.intelligence import AltInstrument, SourceSpec
from marketpulse.engines.ai_regime import basket_instruments
from marketpulse.engines.investment import shared_driver_ids
out = Path(sys.argv[1]); ref = Path(sys.argv[2]); have = Path(sys.argv[3]); gap = float(sys.argv[4]) if len(sys.argv) > 4 else 4
out.mkdir(parents=True, exist_ok=True)
st = Settings(data_mode="DELAYED", llm_enabled=False, news_search="off")
now = datetime.now(timezone.utc)
want = {n: set(json.loads((ref / f"{n}.json").read_text())) - set(json.loads((have / f"{n}.json").read_text())) for n in ("series_base", "series_universe", "series_basket")}
print({k: len(v) for k, v in want.items()}, flush=True)
res = {"series_base": {}, "series_universe": {}, "series_basket": {}}
fails = []
ins = {i.id: i for i in get_instruments().instruments}
for iid in sorted(want["series_base"]):
    ad = build_market_adapter(st); s = ad.fetch_series([ins[iid]], bars=st.history_bars, as_of=now)
    o = getattr(ad, "outcomes", {}).get(iid); res["series_base"].update(s)
    if iid not in s: fails.append((iid, getattr(o, "reason", "")))
    time.sleep(gap)
u = get_universe(st.config_dir); base_ins = get_instruments().by_id()
shared = [base_ins[i] for i in shared_driver_ids(st.config_dir)]
sources = {a.id: a.sources for a in u.alternative}; sources.update({s.id: [SourceSpec(provider="yahoo", symbol=s.symbol)] for s in u.stocks})
uins = {i.id: i for i in [s.as_instrument() for s in u.stocks] + [a.as_instrument() for a in u.alternative] + shared}
for iid in sorted(want["series_universe"]):
    alt = build_alt_adapter(st, store_path=None); s = alt.fetch_series([uins[iid]], {iid: sources.get(iid) or []}, bars=st.history_bars, as_of=now)
    res["series_universe"].update(s)
    if iid not in s: fails.append((iid, getattr(alt.outcomes.get(iid), "reason", "")))
    time.sleep(gap)
specs = {m["id"]: AltInstrument(id=m["id"], name=m.get("name", m["id"]), group="ai", asset_class="equity", unit="price",
                               sources=[SourceSpec(provider="yahoo", symbol=str(m["symbol"]))], source_type="EXCHANGE") for m in basket_instruments()}
for iid in sorted(want["series_basket"]):
    a = specs[iid]; ad2 = build_alt_adapter(st, store_path=None)
    s = ad2.fetch_series([a.as_instrument()], {iid: a.sources}, bars=120, as_of=now); res["series_basket"].update(s)
    if iid not in s: fails.append((iid, getattr(ad2.outcomes.get(iid), "reason", "")))
    time.sleep(gap)
for n, s in res.items():
    _dump_series(out / f"{n}.json", s)
print({n: len(s) for n, s in res.items()}, "fails", fails, flush=True)
