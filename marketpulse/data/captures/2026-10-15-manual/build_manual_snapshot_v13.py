"""13차 수기 캡처 (2026-10-15). 9차와 같은 구조 — run_tick 헬퍼와 태그 파일을 이 폴더에서 읽는다(scratchpad 의존 제거)."""
import hashlib, json, pickle, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manual_tags_v13 import FOREIGN, TAGS
from build_manual_snapshot import run_tick

from marketpulse.config.registry import get_instruments, get_themes
from marketpulse.models.common import DataMeta, DataMode, DataQuality, utcnow
from marketpulse.models.news import NewsEvent, RawNewsItem, ValidationReport

OUT = Path("marketpulse/data/captures/2026-10-15-manual")
raw_items = json.loads((OUT / "news_raw.json").read_text(encoding="utf-8"))
by_id = {i["id"]: i for i in raw_items}
retrieved = utcnow()

# 해외 검색 기사를 RawNewsItem 으로 — LlmSearchNewsAdapter.hits_to_items 와 같은 규약
foreign_raw = []
for f in FOREIGN:
    host = f["url"].split("/")[2]
    host = host[4:] if host.startswith("www.") else host
    published = datetime.fromisoformat(f["date"]).replace(hour=12, tzinfo=timezone.utc)
    item = RawNewsItem(
        id=hashlib.sha256(f["url"].encode()).hexdigest()[:16], title=f["title"], body="",
        url=f["url"], publisher=host, published_at=published, language="en",
        meta=DataMeta(source=f"web_search:{host}", mode=DataMode.DELAYED, retrieved_at=retrieved,
                      as_of=published, quality=DataQuality.PARTIAL),
    )
    foreign_raw.append(item)
    by_id[item.id] = item.model_dump(mode="json")
    TAGS[item.id] = {k: f[k] for k in ("themes", "theme_sentiment", "theme_direction", "sentiment", "impact", "novelty", "horizon", "event_type", "reason")}

events = []
for item_id, tag in TAGS.items():
    item = by_id.get(item_id)
    if item is None:
        continue  # 1차에 있었지만 이번 RSS 에서 밀려난 기사
    events.append(NewsEvent(
        id=f"manual-{item_id}", source_item_ids=[item_id], event=item["title"],
        event_type=tag["event_type"], themes=tag["themes"], theme_sentiment=tag["theme_sentiment"],
        theme_direction=tag["theme_direction"], sentiment=tag["sentiment"], impact_score=tag["impact"],
        novelty_score=tag["novelty"], time_horizon=tag["horizon"], reason=tag["reason"],
        source=item["publisher"], url=item.get("url"), timestamp=item["published_at"],
        extractor="manual", validation=ValidationReport(schema_ok=True), confidence=0.55,
    ))
events.sort(key=lambda e: e.timestamp, reverse=True)

snapshot = pickle.load(open("/tmp/snap/market_snapshot.pkl", "rb"))
by_iid = get_instruments().by_id(); themes_registry = get_themes().by_id()
t1, p1 = run_tick(snapshot, events, by_iid, themes_registry, previous=None, pending_in=[])
t2, _ = run_tick(snapshot, events, by_iid, themes_registry, previous=t1, pending_in=p1)

all_raw = raw_items + [i.model_dump(mode="json") for i in foreign_raw]
(OUT / "live.json").write_text(t2.model_dump_json(), encoding="utf-8")
(OUT / "news_live.json").write_text(json.dumps(all_raw, ensure_ascii=False), encoding="utf-8")

ms, th = t2.market_state, t2.thermometer
print(f"events {len(events)} (국내 {len(events)-len(foreign_raw)} + 해외검색 {len(foreign_raw)}) / raw {len(all_raw)}")
print(f"as_of={t2.as_of} state={ms.primary_label.value} conf={ms.confidence:.0f}%  coverage {t2.data_health.available_instruments}/{t2.data_health.expected_instruments}")
print("drivers:", ", ".join(f"{d.label} {d.z:+.1f}σ" for d in ms.main_drivers))
print(f"thermo comp={th.composite:+.0f} price={th.price:+.0f} news={th.news:+.0f} gap={th.gap_flag} conf={th.confidence:.0f} n={th.news_events}")
print("themes:", [(t.name, round(t.theme_score), t.news_sentiment and round(t.news_sentiment)) for t in sorted(t2.themes, key=lambda x: -abs(x.theme_score))[:8]])
print("divergences:", [(d.type.value, d.related_theme, round(d.severity)) for d in t2.divergences])
print("alerts:", len(t2.alerts))
