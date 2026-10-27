"""유가 시장 원인 판별 — driver 점수는 설정 표의 가중 평균, 상태는 유가 관측과의 일치, 감시 조건은 임계에서 나온다."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.deps import get_investment_service, get_oil_regime_service, get_scenario_check_service, get_service, get_state_history_service
from marketpulse.api.main import create_app
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.oil_regime import build_oil_regime, load_oil_regime_config
from marketpulse.engines.orchestrator import run_pipeline_detailed
from tests.conftest import AS_OF


def _run(scenario: str):
    settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
    r = run_pipeline_detailed(settings, as_of=AS_OF)
    ins = get_instruments().instruments
    market = build_snapshot(ins, r.series_by_id, mode=r.snapshot.mode, as_of=AS_OF, zscore_window=settings.zscore_window, correlations=False)
    return r.snapshot, market, {i.id: i for i in ins}


class TestEngine:
    def test_oil_spike_mock_confirms_an_oil_up_driver(self):
        """브렌트 +2.8σ 모의 데이터: 유가 관측은 up, 지배 driver 는 상승 방향이어야 하고 CONFIRMED 또는(증거 약하면) UNCONFIRMED."""
        snap, market, by_id = _run("oil_spike")
        r = build_oil_regime(market, snap.themes, snap.divergences, by_id)
        assert r.oil_move.direction == "up" and not r.oil_move.suspect
        dom = next(d for d in r.drivers if d.id == r.dominant)
        assert dom.score > 0 and dom.status in ("CONFIRMED", "UNCONFIRMED")
        assert {d.id for d in r.drivers} == set(load_oil_regime_config()["drivers"].keys())
        assert r.confirmations and r.watch and r.note

    def test_score_is_weighted_clipped_mean_and_missing_excluded(self):
        snap, market, by_id = _run("baseline")
        cfg = load_oil_regime_config()
        r = build_oil_regime(market, snap.themes, snap.divergences, by_id)  # extra_z 없음 → 대체 계열은 결측
        d = next(x for x in r.drivers if x.id == "demand")
        avail = [e for e in d.evidence if e.available]
        miss = [e for e in d.evidence if not e.available]
        assert {e.id for e in miss} >= {"DRY_BULK_ETF", "CSI300"}  # 시장 층에 없는 계열
        num = sum(e.contribution for e in avail); den = sum(e.weight for e in avail)
        assert d.score == pytest.approx(100 * num / den, abs=0.15)
        assert d.coverage == pytest.approx(den / sum(e.weight for e in d.evidence), abs=1e-3)
        for e in avail:
            assert abs(e.contribution) <= e.weight + 1e-9
            if e.kind == "price":
                assert e.contribution == pytest.approx(max(-1, min(1, e.sign * e.value / cfg["z_ref"])) * e.weight, abs=0.01)  # value·contribution 은 각각 반올림돼 있다

    def test_status_logic_by_oil_move(self):
        """유가와 driver 가 같은 방향이면 CONFIRMED, 반대면 CONTRADICTED, 유가 두 계열이 갈리면 UNCONFIRMED."""
        snap, market, by_id = _run("oil_spike")
        r = build_oil_regime(market, snap.themes, snap.divergences, by_id)
        oil_sign = 1 if r.oil_move.oil_z and r.oil_move.oil_z > 0 else -1
        min_score = load_oil_regime_config()["status"]["min_score"]
        for d in r.drivers:
            if abs(d.score) < min_score:
                assert d.status == "UNCONFIRMED"
            elif (d.score > 0) == (oil_sign > 0):
                assert d.status == "CONFIRMED"
            else:
                assert d.status == "CONTRADICTED"
        # 브렌트·WTI 를 억지로 갈라 놓으면 확인 보류
        f = market.features["WTI"]
        market.features["WTI"] = f.model_copy(update={"z_1d": (f.z_1d or 0) - 3.0})
        r2 = build_oil_regime(market, snap.themes, snap.divergences, by_id)
        assert r2.oil_move.suspect and all(d.status == "UNCONFIRMED" for d in r2.drivers)
        assert any("정합" in w.text for w in r2.watch)

    def test_narrative_sentence_reflects_news_vs_price(self):
        snap, market, by_id = _run("oil_spike")
        r = build_oil_regime(market, snap.themes, snap.divergences, by_id)
        row = next((n for n in r.narrative if n.theme_id == "oil"), None)
        assert row is not None and row.sentence
        if row.news is not None and row.price is not None and row.news >= 10 and row.price >= 10:
            assert "같은 방향" in row.sentence
        if row.news is not None and row.price is not None and row.news >= 10 and row.price <= -10:
            assert "확인하지 않는다" in row.sentence


@pytest.fixture
def client() -> TestClient:
    for svc in (get_service(), get_state_history_service(), get_investment_service(), get_scenario_check_service(), get_oil_regime_service()):
        svc.clear()
    return TestClient(create_app())


class TestApi:
    def test_route(self, client):
        a = client.get("/api/v1/oil-regime?scenario=oil_spike")
        assert a.status_code == 200
        body = a.json()
        for k in ("regime_label", "dominant", "drivers", "confirmations", "narrative", "watch", "signal_strength_label"):
            assert k in body
        assert client.get("/api/v1/oil-regime?scenario=oil_spike").json() == body
