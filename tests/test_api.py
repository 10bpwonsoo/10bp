"""API 계약 테스트."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.deps import get_service
from marketpulse.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    get_service().clear()
    return TestClient(create_app())


class TestRoutes:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/snapshot",
            "/api/v1/market-state",
            "/api/v1/whats-moving",
            "/api/v1/health",
            "/api/v1/info",
            "/api/v1/scenarios",
            "/api/v1/news",
            "/api/v1/events",
        ],
    )
    def test_ok(self, client, path):
        assert client.get(path).status_code == 200

    def test_snapshot_shape(self, client):
        d = client.get("/api/v1/snapshot").json()
        for key in (
            "as_of", "mode", "scenario", "market_state", "themes", "divergences",
            "alerts", "impact_maps", "events", "whats_moving", "data_health",
            "engine_versions",
        ):
            assert key in d, f"{key} 누락"

    def test_single_call_draws_whole_screen(self, client):
        """패널마다 호출을 나누면 패널 간 시점이 어긋난다 (설계서 STEP 4.8)."""
        d = client.get("/api/v1/snapshot").json()
        assert d["market_state"]["as_of"] == d["as_of"]

    def test_health_exposes_mode_and_freshness(self, client):
        h = client.get("/api/v1/health").json()
        assert h["mode"] == "MOCK"
        assert h["coverage"] == 1.0
        assert "max_freshness_sec" in h
        assert h["llm_status"] == "disabled"

    def test_info_is_cheap(self, client):
        """파이프라인을 돌리지 않는 기동 점검 경로."""
        d = client.get("/api/v1/info").json()
        assert d["status"] == "ok" and d["mode"] == "MOCK"

    def test_scenarios_listed(self, client):
        rows = client.get("/api/v1/scenarios").json()
        assert any(r["name"] == "baseline" and r["is_active"] for r in rows)
        assert all(r["title"] for r in rows)


class TestScenarioControl:
    def test_known_scenario_accepted(self, client):
        r = client.get("/api/v1/snapshot?scenario=baseline")
        assert r.status_code == 200
        assert r.json()["scenario"] == "baseline"

    def test_unknown_scenario_404_with_alternatives(self, client):
        r = client.get("/api/v1/snapshot?scenario=nope")
        assert r.status_code == 404
        assert "baseline" in r.json()["detail"]


class TestCaching:
    def test_repeat_calls_are_consistent(self, client):
        a = client.get("/api/v1/snapshot").json()
        b = client.get("/api/v1/snapshot").json()
        assert a["as_of"] == b["as_of"]

    def test_cache_can_be_cleared(self, client):
        client.get("/api/v1/snapshot")
        get_service().clear()
        assert client.get("/api/v1/snapshot").status_code == 200
