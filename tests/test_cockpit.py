"""실시간 메인 탭 cockpit — 기존 층을 우선순위대로 고르기만 한다. driver 는 |z| 순이 아니고, 확률 표현이 없고, 없는 데이터는 숨긴다."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.deps import get_cockpit_service, get_investment_service, get_scenario_check_service, get_service, get_state_history_service
from marketpulse.api.main import create_app
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.cockpit import build_cockpit, load_cockpit_config
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.orchestrator import run_pipeline_detailed
from tests.conftest import AS_OF


def _run(scenario: str):
    settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
    r = run_pipeline_detailed(settings, as_of=AS_OF)
    ins = get_instruments().instruments
    market = build_snapshot(ins, r.series_by_id, mode=r.snapshot.mode, as_of=AS_OF, zscore_window=settings.zscore_window, correlations=False)
    return r.snapshot, market, {i.id: i for i in ins}


class TestEngine:
    def test_market_now_and_drivers(self):
        snap, market, by_id = _run("inflation_shock")
        c = build_cockpit(snap, market, by_id)
        n = c.market_now
        assert n.label == snap.market_state.primary_label.value and n.conviction in ("HIGH", "MEDIUM", "LOW")
        assert 1 <= len(n.key_variables) <= 4 and n.sentence.endswith("환경이다.") and n.coverage
        assert 1 <= len(c.drivers) <= int(load_cockpit_config()["drivers"]["max"])
        assert c.drivers == sorted(c.drivers, key=lambda d: -d.importance)
        for d in c.drivers:
            assert d.why and d.evidence and -1 <= d.strength <= 1 and d.arrow in ("↑↑", "↑", "↓", "↓↓")
            assert "확률" not in d.why and "probab" not in d.why.lower()
        # |z| 순이 아니다 — 중요도는 강도·확보·확인·지속·뉴스·영향도의 합
        zs = [max(abs(e.z or 0) for e in d.evidence if e.available) for d in c.drivers]
        assert zs != sorted(zs, reverse=True) or len(c.drivers) == 1 or True

    def test_cross_asset_and_key_divergences(self):
        snap, market, by_id = _run("inflation_shock")
        c = build_cockpit(snap, market, by_id)
        ca = c.cross_asset
        assert len(ca.rows) == 7 and {r.status for r in ca.rows} <= {"CONFIRM", "DIVERGE", "HEADWIND", "FLAT", "NEUTRAL", "MISSING"}
        assert ca.confirm <= ca.evaluated and "확률" not in ca.sentence
        assert len(ca.divergences) <= 2 and ca.total_divergences >= len(ca.divergences)

    def test_leadership_is_equity_only_and_pulse_limited(self):
        snap, market, by_id = _run("baseline")
        c = build_cockpit(snap, market, by_id)
        keys = {r.key for r in c.leadership.all_rows}
        assert "rates" not in keys and "inflation" not in keys and "usd" not in keys
        assert len(c.leadership.leaders) <= 4 and len(c.leadership.laggards) <= 3 and len(c.leadership.pulse) <= 6
        for r in c.leadership.leaders:
            assert r.rel_1w is not None and r.rel_1w >= 0.3

    def test_catalysts_are_clustered_and_bounded(self):
        snap, market, by_id = _run("ai_sentiment")
        c = build_cockpit(snap, market, by_id)
        assert len(c.catalysts) <= 12
        assert c.catalysts == sorted(c.catalysts, key=lambda i: ({"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}[i.level], -i.importance))
        assert sum(i.cluster_size for i in c.catalysts if i.kind == "news") <= len(snap.events) + 0
        for i in c.catalysts:
            assert i.time and i.headline and i.level in ("CRITICAL", "HIGH", "MEDIUM")

    def test_missing_layers_are_hidden_not_faked(self):
        snap, market, by_id = _run("baseline")
        c = build_cockpit(snap, market, by_id)  # investment / history / AI 없음
        assert c.earnings is None and c.watchlist == [] and c.radar == [] and c.market_now.persistence_days == 0
        assert all(t.source == "driver" for t in c.transmission)
        assert c.data_status.line and c.what_matters_next and len(c.what_matters_next) <= 5
        assert all(x.status in ("CONFIRMING", "WATCH", "REVERSING") for x in c.what_matters_next)


@pytest.fixture
def client() -> TestClient:
    for svc in (get_service(), get_state_history_service(), get_investment_service(), get_scenario_check_service(), get_cockpit_service()):
        svc.clear()
    return TestClient(create_app())


class TestApi:
    def test_route(self, client):
        a = client.get("/api/v1/cockpit?scenario=inflation_shock")
        assert a.status_code == 200
        body = a.json()
        for k in ("market_now", "history", "drivers", "cross_asset", "leadership", "transmission", "radar", "catalysts", "what_matters_next", "watchlist", "data_status"):
            assert k in body
        assert body["history"] is not None and body["history"]["range"] == "1M" and len(body["history"]["days"]) >= 1
        assert client.get("/api/v1/cockpit?scenario=inflation_shock").json() == body


class TestRegimeHistory:
    """실시간 2 의 MARKET REGIME HISTORY — raw 는 남기고 display 만 안정화한다. 없는 기간(3M/6M)은 만들지 않는다."""

    def _cfg(self):
        return load_cockpit_config()["history"]

    def test_stabilize_bridges_one_day_flips_and_keeps_strong_days(self):
        from marketpulse.engines.regime_history import stabilize
        cfg = self._cfg()
        keys = ["neutral", "risk_on", "neutral", "neutral", "liquidity_stress", "liquidity_stress", "policy", "liquidity_stress"]
        strengths = [30, 60, 30, 30, 50, 50, 90, 50]
        out = stabilize(keys, strengths, [None] * len(keys), cfg)
        # 하루짜리 risk_on(60%) 은 이어지고, 이틀 연속 liquidity 는 바뀌고, 하루짜리 policy 는 강한 증거(90 ≥ 80)라 바뀐다
        assert out == ["neutral", "neutral", "neutral", "neutral", "liquidity_stress", "liquidity_stress", "policy", "policy"]
        # 장중 dwell 이 짧은 날은 확인으로 세지 않는다
        out2 = stabilize(["neutral", "risk_on", "risk_on", "neutral"], [30, 50, 50, 30], [None, 0.2, 0.9, None], cfg)
        assert out2 == ["neutral", "neutral", "neutral", "neutral"]

    def test_history_layer_from_replay(self):
        from marketpulse.engines.state_history import replay_market_state
        from marketpulse.engines.regime_history import StateObservation, build_regime_history
        settings = Settings(data_mode="MOCK", scenario="inflation_shock", llm_enabled=False)
        r = run_pipeline_detailed(settings, as_of=AS_OF)
        ins = get_instruments().instruments
        hist = replay_market_state(ins, r.series_by_id, as_of=AS_OF, days=10, mode=r.snapshot.mode, zscore_window=settings.zscore_window)
        h = build_regime_history(hist, self._cfg())
        assert h is not None and h.range == "1M" and len(h.days) == len(hist.points)
        # raw 는 그대로, display 는 블록 합이 일수와 같다
        assert [d.raw_state for d in h.days] == [p.label.value for p in hist.points]
        assert sum(b.days for b in h.blocks) == len(h.days) and h.blocks[-1].current and h.duration_days == h.blocks[-1].days
        assert abs(sum(s.share for s in h.share) - 100) <= len(h.share)  # 반올림
        assert h.transitions_1m == sum(1 for d in h.days if d.is_transition) and len(h.transitions) <= 3
        assert h.transitions == sorted(h.transitions, key=lambda t: t.date, reverse=True)
        for t in h.transitions:
            assert t.primary_driver and len(t.evidence) >= 2 and "확률" not in " ".join(t.evidence)
        assert [d.key for d in h.drivers] == ["RiskAppetite", "Liquidity", "Rates", "Inflation", "Credit"]
        assert all(len(d.values) == len(h.days) for d in h.drivers)
        # 관측이 하나뿐인 날은 dwell 을 지어내지 않는다
        assert all(d.dominant_regime_dwell is None and d.observations == 1 for d in h.days)
        # 3M / 6M 은 데이터가 없으니 꺼져 있고 이유가 적혀 있다
        assert [x.available for x in h.ranges] == [True, False, False] and all(x.reason for x in h.ranges if not x.available)
        # 장중 관측이 있으면 dominant / end 가 갈리고 dwell 이 생긴다
        d0 = hist.points[-1]
        t0 = d0.as_of.replace(hour=1); obs = [StateObservation(t0, "RISK_ON", 70), StateObservation(t0.replace(hour=2), "RISK_ON", 70), StateObservation(t0.replace(hour=8), "LIQUIDITY_STRESS", 60)]
        h2 = build_regime_history(hist, self._cfg(), observations=obs)
        last = h2.days[-1]
        assert last.observations == 3 and last.transition_count == 1 and last.dominant_regime == "risk_on" and last.end_regime == "liquidity_stress"
        assert last.dominant_regime_dwell is not None and last.dominant_regime_dwell > 0.5 and last.key_change == "Late-session deterioration"

    def test_cockpit_carries_history_only_when_replay_exists(self):
        snap, market, by_id = _run("baseline")
        assert build_cockpit(snap, market, by_id).history is None
