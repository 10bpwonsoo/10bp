"""2026-10-06 실데이터 수집: 시장(Yahoo/FRED/CSV) + RSS 기사. 키는 환경변수로만 읽고 값은 출력하지 않는다.

FRED_API_KEY 가 있으면 BE10Y(T10YIE)·US_HY_OAS 가 처음으로 들어온다. 결과는 JSON 으로 남겨
다른 세션에서도 같은 봉으로 스냅샷을 만들 수 있게 한다.
"""
import json, logging, os, time
from pathlib import Path
logging.basicConfig(level=logging.WARNING)
from marketpulse.adapters.registry import build_market_adapter, build_news_adapter
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.normalize import build_snapshot
from marketpulse.models.common import utcnow

OUT = Path(__file__).resolve().parent
print("FRED key present:", bool(os.environ.get("FRED_API_KEY")))  # 값은 절대 출력하지 않는다
settings = Settings(data_mode="DELAYED", llm_enabled=False)
as_of = utcnow()
instruments = get_instruments().instruments
t = time.perf_counter()
adapter = build_market_adapter(settings)
series = adapter.fetch_series(instruments, bars=settings.history_bars, as_of=as_of)
print("market fetch", round(time.perf_counter() - t, 1), "s", len(series), "/", len(instruments))
# 코스피200 단독 재시도 — Yahoo 가 1봉만 주는 날이 있다
for iid in ("KOSPI200",):
    if iid not in series:
        time.sleep(3)
        got = adapter.fetch_series([i for i in instruments if i.id == iid], bars=settings.history_bars, as_of=utcnow())
        series.update(got)
        print(iid, "retry", "ok" if iid in got else "failed")
snap = build_snapshot(instruments, series, mode=adapter.mode, as_of=utcnow(), zscore_window=settings.zscore_window)
print("as_of", snap.as_of, "coverage", snap.coverage, "missing", snap.missing)
failed = [(k, o.reason) for k, o in getattr(adapter, "outcomes", {}).items() if not o.ok]
print("failed", failed)
for iid in ("BE10Y", "US_HY_OAS"):
    s = series.get(iid)
    print(iid, "bars", len(s.values) if s else 0, "last", (s.timestamps[-1].date().isoformat(), s.values[-1]) if s else None)
(OUT / "series_live.json").write_text(json.dumps({k: v.model_dump(mode="json") for k, v in series.items()}, ensure_ascii=False), encoding="utf-8")
(OUT / "fetch_report.json").write_text(json.dumps({"as_of": snap.as_of.isoformat(), "coverage": snap.coverage, "missing": snap.missing, "failed": failed,
                                                    "fred_key_present": bool(os.environ.get("FRED_API_KEY"))}, ensure_ascii=False, indent=1), encoding="utf-8")

t = time.perf_counter()
try:
    items = build_news_adapter(settings).fetch_news(limit=80, as_of=as_of)
except Exception as exc:
    print("news failed", exc); items = []
print("news", len(items), round(time.perf_counter() - t, 1), "s", sorted({i.publisher for i in items}))
(OUT / "news_raw.json").write_text(json.dumps([i.model_dump(mode="json") for i in items], ensure_ascii=False), encoding="utf-8")
for i in items:
    print(" ", i.id, i.published_at.strftime("%m-%d %H:%M"), i.publisher[:8], "|", i.title[:90])
