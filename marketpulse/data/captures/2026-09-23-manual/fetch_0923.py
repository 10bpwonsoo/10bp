"""2026-09-18 실데이터 수집: 시장(Yahoo/CSV) + RSS 기사. 키 없음, LLM 없음."""
import json, logging, pickle, time
from pathlib import Path
logging.basicConfig(level=logging.WARNING)
from marketpulse.adapters.registry import build_market_adapter, build_news_adapter
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.normalize import build_snapshot
from marketpulse.models.common import utcnow

OUT = Path("marketpulse/data/captures/2026-09-23-manual")
settings = Settings(data_mode="DELAYED", llm_enabled=False)
from datetime import datetime, timezone
as_of = utcnow()  # 오늘(9/23) 장중 기준 — 아시아 봉은 장중값이다
instruments = get_instruments().instruments
t = time.perf_counter()
adapter = build_market_adapter(settings)
series = adapter.fetch_series(instruments, bars=settings.history_bars, as_of=as_of)
print("market fetch", round(time.perf_counter() - t, 1), "s", len(series), "/", len(instruments))
snap = build_snapshot(instruments, series, mode=adapter.mode, as_of=utcnow(), zscore_window=settings.zscore_window)  # 봉은 9/17 종가까지, 기준 시각은 수집 시각
pickle.dump(snap, open("/tmp/snap/market_snapshot.pkl", "wb"))
pickle.dump(series, open("/tmp/snap/series_live.pkl", "wb"))
print("as_of", snap.as_of, "missing", snap.missing)
failed = [(k, o.reason) for k, o in getattr(adapter, "outcomes", {}).items() if not o.ok]
print("failed", failed[:20])
t = time.perf_counter()
try:
    items = build_news_adapter(settings).fetch_news(limit=80, as_of=as_of)
except Exception as exc:
    print("news failed", exc); items = []
print("news", len(items), round(time.perf_counter() - t, 1), "s", sorted({i.publisher for i in items}))
(OUT / "news_raw.json").write_text(json.dumps([i.model_dump(mode="json") for i in items], ensure_ascii=False), encoding="utf-8")

for i in items:
    print(" ", i.id, i.published_at.strftime("%m-%d %H:%M"), i.publisher[:8], "|", i.title[:90])
