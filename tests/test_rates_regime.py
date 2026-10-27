"""금리·물가 원인 판별 — driver 점수는 설정 표의 가중 평균, 지배 driver 는 10년 금리 방향과 맞는 것 우선, 커브·명목 분해는 항등식."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.deps import get_investment_service, get_rates_regime_service, get_scenario_check_service, get_service, get_state_history_service
from marketpulse.api.main import create_app
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.engines.rates_regime import build_rates_regime, load_rates_regime_config
from tests.conftest import AS_OF


def _run(scenario: str):
    settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
    r = run_pipeline_detailed(settings, as_of=AS_OF)
    ins = get_instruments().instruments
    market = build_snapshot(ins, r.series_by_id, mode=r.snapshot.mode, as_of=AS_OF, zscore_window=settings.zscore_window, correlations=False)
    return r.snapshot, market, {i.id: i for i in ins}


class TestEngine:
    def test_inflation_shock_mock_confirms_inflation_repricing(self):
        """모의 물가 충격(유가·기대인플레·금리 동반 상승): 10년 금리 up, 물가 리프라이싱이 지배 driver 이고 CONFIRMED."""
        snap, market, by_id = _run("inflation_shock")
        r = build_rates_regime(market, snap.themes, by_id)
        assert r.rate_move.direction == "up"
        assert r.dominant == "inflation_repricing" and r.inflation_status == "CONFIRMED"
        assert r.regime_label.endswith("Inflation Repricing Confirmed")
        assert {d.id for d in r.drivers} == set(load_rates_regime_config()["drivers"].keys())
        assert "probab" not in r.headline.lower() and "확률" not in r.headline

    def test_dominant_prefers_direction_consistent_driver(self):
        """금리와 반대로 가는 driver 는 |점수| 가 커도 지배 driver 가 못 된다 — 위험회피(−)는 금리 상승의 원인이 아니다."""
        snap, market, by_id = _run("inflation_shock")
        r = build_rates_regime(market, snap.themes, by_id)
        dom = next(d for d in r.drivers if d.id == r.dominant)
        assert dom.status == "CONFIRMED"
        contradicted = [d for d in r.drivers if d.status == "CONTRADICTED"]
        assert contradicted and max(abs(d.score) for d in contradicted) > abs(dom.score)  # 더 큰 반대 driver 가 있어도

    def test_score_is_weighted_clipped_mean_and_missing_excluded(self):
        snap, market, by_id = _run("baseline")
        cfg = load_rates_regime_config()
        r = build_rates_regime(market, snap.themes, by_id)  # extra_z 없음 → 대체 계열은 결측
        for d in r.drivers:
            avail = [e for e in d.evidence if e.available]
            if not avail:
                continue
            num = sum(e.contribution for e in avail); den = sum(e.weight for e in avail)
            assert d.score == pytest.approx(100 * num / den, abs=0.15)
            assert d.coverage == pytest.approx(den / sum(e.weight for e in d.evidence), abs=1e-3)
            for e in avail:
                assert abs(e.contribution) <= e.weight + 1e-9
                if e.kind == "price":
                    assert e.contribution == pytest.approx(max(-1, min(1, e.sign * e.value / cfg["z_ref"])) * e.weight, abs=0.01)

    def test_flat_rate_move_marks_everything_unconfirmed(self):
        snap, market, by_id = _run("baseline")
        r = build_rates_regime(market, snap.themes, by_id)
        if r.rate_move.direction == "flat":
            assert all(d.status == "UNCONFIRMED" for d in r.drivers)
            assert r.regime_label.startswith("RATES IN RANGE")

    def test_curve_shape_and_lead(self):
        """2s10s z 가 + 이고 장기물이 오르면 베어 스티프닝. 단기물이 반대로 가면(트위스트) 같이 가는 장기 구간이 주도."""
        snap, market, by_id = _run("inflation_shock")
        f2, f30 = market.features["US2Y"], market.features["US30Y"]
        market.features["US2Y"] = f2.model_copy(update={"z_1d": -1.5, "z_5d": -1.5})
        market.features["US30Y"] = f30.model_copy(update={"z_1d": 1.8, "z_5d": 1.8})
        market.features["US10Y"] = market.features["US10Y"].model_copy(update={"z_1d": 1.4, "z_5d": 1.4})
        market.features["CURVE_2S10S"] = market.features["CURVE_2S10S"].model_copy(update={"z_1d": 2.0, "z_5d": 2.0})
        r = build_rates_regime(market, snap.themes, by_id)
        assert r.curve.shape == "bear_steepening" and r.curve.lead == "long"
        assert {t.label for t in r.curve.tenors} == {"2Y", "5Y", "10Y", "30Y"}
        assert "스티프닝" in r.curve.sentence

    def test_decomposition_identity_and_missing(self):
        snap, market, by_id = _run("inflation_shock")
        r = build_rates_regime(market, snap.themes, by_id)
        for d in r.decomposition:
            if d.nominal_bp is not None and d.breakeven_bp is not None:
                assert d.real_implied_bp == pytest.approx(d.nominal_bp - d.breakeven_bp, abs=0.11)
        # 기대인플레 계열을 빼면 분해하지 못한다고 말해야지 0 으로 채우면 안 된다
        market.features.pop("BE10Y", None)
        r2 = build_rates_regime(market, snap.themes, by_id)
        ten = next(x for x in r2.decomposition if x.tenor == "10Y")
        assert ten.dominant == "unknown" and "기대인플레" in ten.missing and ten.breakeven_bp is None

    def test_components_confirmations_divergences_triggers(self):
        snap, market, by_id = _run("inflation_shock")
        r = build_rates_regime(market, snap.themes, by_id)
        keys = {c.key: c for c in r.inflation_components}
        assert {"realized", "implied", "energy", "wages", "fx"} <= set(keys)
        assert keys["realized"].status == "missing" and keys["realized"].score is None and keys["realized"].note  # CPI·PCE 계열이 없다 — 0 이 아니다
        assert keys["energy"].status == "up"
        assert {c.status for c in r.confirmations} <= {"CONFIRMED", "MIXED", "NOT_CONFIRMED", "MISSING"}
        assert all(d.why and d.severity >= 0 for d in r.divergences)
        assert 3 <= len(r.triggers) <= 5 and all(t.metric and t.condition for t in r.triggers)
        assert any(not t.measurable for t in r.triggers)  # 실현 물가 서프라이즈는 계열이 없어 못 잰다
        assert r.market_implication.rows and r.market_implication.why and all(row.pressure in (-1, 0, 1, 2) for row in r.market_implication.rows)
        assert all(w not in r.market_implication.why for w in ("매수", "매도", "buy", "sell"))
        assert r.release


@pytest.fixture
def client() -> TestClient:
    for svc in (get_service(), get_state_history_service(), get_investment_service(), get_scenario_check_service(), get_rates_regime_service()):
        svc.clear()
    return TestClient(create_app())


class TestApi:
    def test_route(self, client):
        a = client.get("/api/v1/rates-regime?scenario=inflation_shock")
        assert a.status_code == 200
        body = a.json()
        for k in ("regime_label", "dominant", "drivers", "inflation_components", "curve", "decomposition", "confirmations", "divergences", "market_implication", "triggers", "release"):
            assert k in body
        assert client.get("/api/v1/rates-regime?scenario=inflation_shock").json() == body

    def test_inflation_tab_focus_is_rates_regime(self, client):
        checks = client.get("/api/v1/scenario-check?scenario=inflation_shock").json()
        assert next(c for c in checks if c["name"] == "inflation_shock")["focus"] == "rates_regime"
