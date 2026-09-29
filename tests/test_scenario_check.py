"""시나리오 점검 — 모의 시나리오의 충격 서명을 실데이터에 대어 본다. 숫자는 설정 규칙에서만 나온다."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marketpulse.adapters.market.scenario import load_scenario
from marketpulse.api.deps import get_investment_service, get_scenario_check_service, get_service, get_state_history_service
from marketpulse.api.main import create_app
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import MOCK_DIR, Settings
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.engines.scenario_check import check_scenario, check_scenarios, load_scenario_checks
from tests.conftest import AS_OF


def _run(scenario: str):
    settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
    r = run_pipeline_detailed(settings, as_of=AS_OF)
    ins = get_instruments().instruments
    market = build_snapshot(ins, r.series_by_id, mode=r.snapshot.mode, as_of=AS_OF, zscore_window=settings.zscore_window, correlations=False)
    return r.snapshot, market, {i.id: i for i in ins}


class TestEngine:
    def test_scenario_matches_its_own_mock_data_best(self):
        """물가 충격 모의 데이터에 물가 충격 서명을 대면 가장 닮아야 하고, 평시보다 높아야 한다."""
        snap, market, by_id = _run("inflation_shock")
        inf = check_scenario(load_scenario(MOCK_DIR, "inflation_shock"), market, snap.market_state, snap.themes, by_id)
        base = check_scenario(load_scenario(MOCK_DIR, "baseline"), market, snap.market_state, snap.themes, by_id)
        assert inf.match_score >= 70 and inf.match_label == "강하게 닮음"
        assert inf.match_score > base.match_score
        assert inf.label is not None and inf.label.value == "INFLATION_SHOCK"
        assert inf.require_passed is True and inf.require_observed is not None and inf.require_observed >= 1.0
        assert inf.current_label.value == "INFLATION_SHOCK" and "시나리오와 같다" in inf.verdict

    def test_missing_is_excluded_not_zero(self):
        """서명에 있지만 확보되지 않은 계열은 결측으로 적히고 분모에서 빠진다."""
        snap, market, by_id = _run("baseline")
        sc = load_scenario(MOCK_DIR, "oil_spike")  # DIESEL_PROXY·SOIL 등 시장 층 밖 계열이 있다
        chk = check_scenario(sc, market, snap.market_state, snap.themes, by_id)
        assert "DIESEL_PROXY" in chk.missing and "SOIL" in chk.missing
        assert chk.evaluated == len(chk.rows) - len(chk.missing)
        assert all(r.status == "missing" and r.used_z is None for r in chk.rows if r.instrument_id in chk.missing)
        # 대체·종목 z 를 넘기면 그 계열이 채워진다
        chk2 = check_scenario(sc, market, snap.market_state, snap.themes, by_id, extra_z={"DIESEL_PROXY": (2.0, None, "alternative"), "SOIL": (1.0, None, "stock")})
        assert "DIESEL_PROXY" not in chk2.missing and chk2.evaluated == chk.evaluated + 2
        row = next(r for r in chk2.rows if r.instrument_id == "DIESEL_PROXY")
        assert row.layer == "alternative" and row.status == "agree" and row.ratio == pytest.approx(2.0 / 2.4, abs=1e-3)

    def test_score_is_weighted_ratio_of_config_rules(self):
        """일치도 = Σ(weight·ratio)/Σ(weight). 가중치는 |기대 z|(조용 조건은 quiet_weight)."""
        snap, market, by_id = _run("baseline")
        chk = check_scenario(load_scenario(MOCK_DIR, "inflation_shock"), market, snap.market_state, snap.themes, by_id)
        th = load_scenario_checks()["thresholds"]
        rows = [r for r in chk.rows if r.status != "missing"]
        num = sum(r.weight * r.ratio for r in rows); den = sum(r.weight for r in rows)
        assert chk.match_score == pytest.approx(100 * num / den, abs=0.15)
        for r in rows:
            if r.layer == "theme":
                continue  # 테마 조건의 가중치는 설정에 명시된 값이다
            expected_w = abs(r.expected_z) if abs(r.expected_z) >= th["quiet_abs"] else th["quiet_weight"]
            assert r.weight == pytest.approx(expected_w)
            if r.status == "oppose":
                assert r.ratio == 0.0 and r.used_z is not None and r.used_z * r.expected_z < 0

    def test_theme_conditions_catch_news_vs_price_signature(self):
        """AI 센티 시나리오의 본질(뉴스 뜨겁고 가격 제자리)은 가격 z 로는 안 잡힌다 — 테마 조건 행이 그것을 잰다."""
        snap, market, by_id = _run("ai_sentiment")
        chk = check_scenario(load_scenario(MOCK_DIR, "ai_sentiment"), market, snap.market_state, snap.themes, by_id)
        theme_rows = [r for r in chk.rows if r.layer == "theme"]
        assert len(theme_rows) == 3
        news = next(r for r in theme_rows if r.instrument_id == "theme:ai:news_sentiment")
        assert news.status in ("agree", "weak") and news.used_z is not None and news.used_z > 0
        price = next(r for r in theme_rows if r.instrument_id == "theme:ai:theme_score")
        assert price.status in ("quiet_ok", "quiet_broken") and price.used_window is None
        assert chk.match_score >= 45  # 자기 모의 데이터에서는 적어도 부분적으로 닮아야 한다

    def test_all_configured_scenarios_in_config_order(self):
        snap, market, by_id = _run("baseline")
        from marketpulse.adapters.market.scenario import available_scenarios
        scs = [load_scenario(MOCK_DIR, n) for n in available_scenarios(MOCK_DIR)]
        out = check_scenarios(scs, market, snap.market_state, snap.themes, by_id)
        assert [c.name for c in out] == list(load_scenario_checks()["checks"].keys())
        base = next(c for c in out if c.name == "baseline")
        assert base.current_label.value == "NEUTRAL" and base.label is not None and base.label.value == "NEUTRAL"
        for c in out:
            assert 0 <= c.match_score <= 100 and c.verdict and c.note


@pytest.fixture
def client() -> TestClient:
    get_service().clear(); get_state_history_service().clear(); get_investment_service().clear(); get_scenario_check_service().clear()
    return TestClient(create_app())


class TestApi:
    def test_route_returns_checks_and_caches_per_as_of(self, client):
        a = client.get("/api/v1/scenario-check?scenario=baseline")
        assert a.status_code == 200
        rows = a.json()
        assert [r["name"] for r in rows] == list(load_scenario_checks()["checks"].keys())
        r0 = rows[0]
        for k in ("match_score", "match_label", "rows", "verdict", "note", "current_label", "as_of"):
            assert k in r0
        b = client.get("/api/v1/scenario-check?scenario=baseline")
        assert b.json() == rows
