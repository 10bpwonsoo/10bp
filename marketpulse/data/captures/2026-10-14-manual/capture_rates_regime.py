"""실데이터 금리·물가 원인 판별 캡처 — 정적 배포본용."""
import pickle, sys
from pathlib import Path
from marketpulse.config.registry import get_instruments
from marketpulse.engines.rates_regime import build_rates_regime
from marketpulse.engines.scenario_check import extra_z_from_investment
from marketpulse.models.intelligence import InvestmentIntelligence
from marketpulse.models.snapshot import IntelligenceSnapshot
CAP = Path(sys.argv[1])
live = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
inv = InvestmentIntelligence.model_validate_json((CAP / "investment.json").read_text(encoding="utf-8"))
market = pickle.load(open("/tmp/snap/market_snapshot.pkl", "rb"))
ins = get_instruments().instruments
# macro fallback layer(2026-10-14) — fetch_macro.py 가 남긴 FRED 원자료(PRIMARY) → 없으면 보도 확인 수기 파일(SECONDARY) → 대체 지표(PROXY) → UNAVAILABLE
import json as _json0
from marketpulse.engines.macro_fallback import build_layer
from marketpulse.engines.policy_events import load_events_file as _lef
_mr = CAP / "macro_raw.json"
macro = build_layer(_json0.loads(_mr.read_text(encoding="utf-8"))["series"] if _mr.exists() else None, as_of=live.as_of, curated=_lef(live.as_of.date()),
                    themes=live.themes, events=live.events)
(CAP / "macro_data.json").write_text(macro.model_dump_json(indent=1), encoding="utf-8")
print("MACRO", {k: (c.source_class, c.score, c.display_label) for k, c in macro.components.items()}, "news", macro.news and macro.news.score)
r = build_rates_regime(market, live.themes, {i.id: i for i in ins}, extra_z=extra_z_from_investment(inv), extra_names={p.id: p.label for p in inv.alternative},
                       series=pickle.load(open("/tmp/snap/series_live.pkl", "rb")), macro=macro)  # 분해를 같은 날짜로 맞춘다(2026-10-14)
# POLICY & MACRO EVENTS(2026-10-14) — 출처 확인된 수기 파일 + 미국채 2Y·10Y 일간 종가로 잰 반응
from marketpulse.engines.policy_events import build_policy_events, load_events_file
_ev = build_policy_events(load_events_file(live.as_of.date()), pickle.load(open("/tmp/snap/series_live.pkl", "rb")), r, as_of=live.as_of)
if _ev is not None:
    r = r.model_copy(update={"events": _ev})
    print("EVENTS recent", [(i.title, i.label, i.reaction_text, i.impact) for i in _ev.recent], "| upcoming", [(u.date.isoformat()[5:], u.name) for u in _ev.upcoming][:5], "| link", _ev.link and (_ev.link.latest_label, _ev.link.impact))
# MARKET READ(2026-10-14) — LLM Macro + Rates Investment Interpretation. 실패하면 규칙 기반 문장 + 이유. 세션 생성본은 같은 검증을 통과해야만 쓴다
import json as _json
from marketpulse.ai.client import build_client
from marketpulse.ai.rates_read import attach_market_read
from marketpulse.config.settings import get_settings as _gs
_sess = CAP / "rates_read_session.json"
r, _ctx = attach_market_read(r, client=build_client(_gs()), market=market, series=pickle.load(open("/tmp/snap/series_live.pkl", "rb")), news=live.events,
                             instrument_kinds={i.id: i.series_kind for i in ins}, as_of=live.as_of,
                             session_read=_json.loads(_sess.read_text(encoding="utf-8")) if _sess.exists() else None)
# INFLATION PRESSURE MAP 하단 해석 — 같은 방식(API → 실패 시 같은 검증을 통과한 세션 생성본 → 규칙 기반)
from marketpulse.ai.inflation_read import attach_inflation_read, build_context as _ictx
_isess = CAP / "inflation_read_session.json"
r = attach_inflation_read(r, client=build_client(_gs()), session_read=_json.loads(_isess.read_text(encoding="utf-8")) if _isess.exists() else None)
_im = r.inflation_map
print("INFLATION READ", _im.read_meta.source, _im.read_meta.generator, "|", _im.read_meta.reason, "| warn", _im.read_meta.warnings, "\n  ", _im.read)
_ctx["inflation_map"] = _ictx(_im)
print("IMAP", [(i.key, i.state, i.score, i.source_class, i.in_signal) for i in _im.items], "official", _im.official_count, "proxy", _im.proxy_count, "news", _im.news_count)
print("PANELS", _im.signal, _im.confirmation, "|", r.curve_move.shape, r.curve_move.level_dir, "|", [(t.tenor, t.primary_label) for t in r.yield_breakdown.tenors], r.yield_breakdown.character_key)
(CAP / "rates_read_context.json").write_text(_json.dumps(_ctx, ensure_ascii=False, indent=1), encoding="utf-8")
_m = r.top.market_read_meta
print("MARKET READ", _m.source, _m.status, _m.generator, "|", _m.reason, "|", _m.themes_ko, _m.move_quality_ko, _m.regime_fit, "| warn", _m.warnings)
print("  ", r.top.market_read)
(CAP / "rates_regime.json").write_text(r.model_dump_json(), encoding="utf-8")
from marketpulse.config.settings import get_settings
from marketpulse.history import DailySnapshotManager, JsonDirStore
from marketpulse.history.calculators import RegimeInputs
from marketpulse.history.integrate import sync_rates
_series = pickle.load(open("/tmp/snap/series_live.pkl", "rb"))
_h = sync_rates(DailySnapshotManager(JsonDirStore(get_settings().history_dir)), r, inputs=RegimeInputs(instruments=ins, series_by_id=_series, events=live.events, mode=live.mode), as_of=live.as_of)
print("HIST", "rec", _h.recorded_days, "bf", _h.backfilled_days, _h.current_label, _h.current_streak, "prev", _h.previous_label, [(p.date.isoformat()[5:], p.source[0], p.state) for p in _h.points[-6:]])
print(r.regime_label, "|", r.signal_strength_label, r.margin, "| infl", r.inflation_status)
print("rate_move", r.rate_move)
for d in r.drivers: print(" ", d.id, d.score, d.status, d.coverage, [(e.label, e.value, e.available) for e in d.evidence])
print("components", [(c.key, c.score, c.status, c.note[:60]) for c in r.inflation_components])
print("curve", r.curve.shape, r.curve.lead, r.curve.spread_z, r.curve.sentence)
print("decomp", r.decomposition)
print("confirm", [(c.label, c.status, c.values) for c in r.confirmations])
print("div", [(d.label, d.severity, d.why) for d in r.divergences])
print("impl", r.market_implication.why, [(i.label, i.pressure) for i in r.market_implication.rows])
print("triggers", [(t.text, t.met) for t in r.triggers]); print("release", [t.text for t in r.release])
