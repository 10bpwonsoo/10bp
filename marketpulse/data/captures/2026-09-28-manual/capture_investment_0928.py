"""실데이터 Investment Intelligence 캡처. 키·비밀 없음. Yahoo 차트 + CSV 리플레이만."""
import json, logging, sys, time
from datetime import timezone
from pathlib import Path
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
from marketpulse.config.settings import Settings
from marketpulse.models.common import utcnow
from marketpulse.models.snapshot import IntelligenceSnapshot
from marketpulse.engines.investment import run_investment

CAP = Path("/home/user/10bp/marketpulse/data/captures/2026-09-28-manual")
PREV = Path("/home/user/10bp/marketpulse/data/captures/2026-09-23-manual/investment.json")
base = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
settings = Settings(data_mode="DELAYED", llm_enabled=False)
from datetime import datetime
as_of = utcnow()  # 오늘(9/28) 오후 기준 — 한국·아시아 종가, 미국·유럽 9/25 종가
from marketpulse.models.intelligence import InvestmentIntelligence
previous = InvestmentIntelligence.model_validate_json(PREV.read_text(encoding="utf-8"))
t = time.perf_counter()
inv = run_investment(settings, base, as_of=as_of, previous=previous, store_path=sys.argv[1])
print("elapsed", round(time.perf_counter() - t, 1), "s")
h = inv.health
print("health", h.model_dump())
print("drivers", [(d.instrument_id, round(d.z, 2), d.change_1d_display) for d in inv.drivers])
print("impacts", [(i.stock_name, i.driver_label, round(i.score)) for i in inv.market_stock_impact[:12]])
print("rollover followup", [(p.id, p.z and round(p.z,2), p.rollover_suspect, p.rollover_followup) for p in inv.alternative if p.rollover_suspect or p.rollover_followup])
print("alt quality", {q: sum(1 for p in inv.alternative if p.quality == q) for q in ("OK", "PARTIAL", "STALE", "MISSING")})
print("anomalies", [(a.stock_name, a.label, a.flags) for a in inv.unusual_movers])
print("divergences", [(d.kind, d.stock_name, round(d.severity)) for d in inv.fundamental_divergences])
print("semi", inv.semiconductor.model_dump().get("interpretation", "")[:300])
print("leadlag", [(l.lead_id, l.lag_id, l.best_lag_days, l.corr_at_best, l.verdict) for l in inv.lead_lag][:10])
print("watch", [(w.name, w.badges) for w in inv.watchlist][:20])
(CAP / "investment.json").write_text(inv.model_dump_json(), encoding="utf-8")
print("wrote", CAP / "investment.json", (CAP / "investment.json").stat().st_size)
