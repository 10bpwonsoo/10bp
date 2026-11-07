"""MOCK 뷰 5개를 오늘 시각으로 다시 만든다 — 세 틱을 돌려 지속 조건(괴리 2틱·알림 기준선)이 살아 있게."""
import json
from datetime import timedelta
from pathlib import Path
from marketpulse.adapters.registry import build_news_adapter
from marketpulse.config.settings import Settings
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.models.common import utcnow
SNAP = Path("/tmp/snap")
VIEWS = {"inflation": "inflation_shock", "ai": "ai_sentiment", "baseline": "baseline", "oil_spike": "oil_spike", "memory_upcycle": "memory_upcycle"}
now = utcnow()
for view, scenario in VIEWS.items():
    settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
    history, pending, snap = [], [], None
    for k in (2, 1, 0):
        r = run_pipeline_detailed(settings, as_of=now - timedelta(minutes=k), history=history, pending_divergences=pending)
        history.append(r.snapshot); pending = r.pending; snap = r.snapshot
    (SNAP / f"{view}.json").write_text(snap.model_dump_json(), encoding="utf-8")
    news = build_news_adapter(settings).fetch_news(limit=50, as_of=now)
    (SNAP / f"news_{view}.json").write_text(json.dumps([n.model_dump(mode="json") for n in news], ensure_ascii=False), encoding="utf-8")
    print(view, snap.as_of.isoformat()[:16], snap.market_state.primary_label.value, round(snap.market_state.confidence), "div", len(snap.divergences), "alerts", len(snap.alerts), "news", len(news))
