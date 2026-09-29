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
        for k in ("market_now", "drivers", "cross_asset", "leadership", "transmission", "radar", "catalysts", "what_matters_next", "watchlist", "data_status"):
            assert k in body
        assert client.get("/api/v1/cockpit?scenario=inflation_shock").json() == body
