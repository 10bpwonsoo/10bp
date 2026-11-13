"""MOCK 뷰의 Investment Intelligence 캡처 (정적 배포본용)."""
import json
from pathlib import Path
from marketpulse.config.settings import Settings
from marketpulse.models.common import utcnow
from marketpulse.models.snapshot import IntelligenceSnapshot
from marketpulse.engines.orchestrator import run_pipeline
from marketpulse.engines.investment import run_investment
from marketpulse.adapters.registry import build_news_adapter
SNAP = Path("/tmp/snap")
VIEWS = {"inflation": "inflation_shock", "ai": "ai_sentiment", "baseline": "baseline",
         "oil_spike": "oil_spike", "memory_upcycle": "memory_upcycle"}
as_of = utcnow()
for view, scenario in VIEWS.items():
    settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
    base_path = SNAP / f"{view}.json"
    if base_path.exists():
        base = IntelligenceSnapshot.model_validate_json(base_path.read_text(encoding="utf-8"))
    else:
        base = run_pipeline(settings, as_of=as_of)
        base_path.write_text(base.model_dump_json(), encoding="utf-8")
        news = build_news_adapter(settings).fetch_news(limit=50)
        (SNAP / f"news_{view}.json").write_text(json.dumps([n.model_dump(mode="json") for n in news], ensure_ascii=False), encoding="utf-8")
    inv = run_investment(settings, base, as_of=base.as_of)
    (SNAP / f"inv_{view}.json").write_text(inv.model_dump_json(), encoding="utf-8")
    print(view, scenario, "drivers", len(inv.drivers), "impacts", len(inv.market_stock_impact), "anom", len(inv.unusual_movers),
          "div", len(inv.fundamental_divergences), "commentary", len(inv.commentary), "size", (SNAP / f"inv_{view}.json").stat().st_size)
