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
            "/api/v1/themes",
            "/api/v1/divergences",
            "/api/v1/alerts",
            "/api/v1/whats-moving",
            "/api/v1/health",
            "/api/v1/info",
            "/api/v1/scenarios",
            "/api/v1/news",
            "/api/v1/events",
            "/api/v1/impact-map",
            "/api/v1/relationships",
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


class TestP1Payload:
    def test_market_state_is_evaluated(self, client):
        ms = client.get("/api/v1/market-state").json()
        assert len(ms["factors"]) == 11
        assert ms["hypotheses"]
        assert ms["narrative"]
        assert ms["narrative_source"] == "template"

    def test_every_score_carries_its_reasoning(self, client):
        """요구 15-6. 점수만 있고 근거가 없는 응답은 내보내지 않는다."""
        for t in client.get("/api/v1/themes").json():
            bd = t["breakdown"]
            assert bd["method"] and bd["inputs_hash"]
            assert bd["contributions"] or bd["missing_inputs"]

    def test_rule_trace_reaches_the_client(self, client):
        """요구 14. 어떤 rule 로 판정됐는지 화면에서 확인할 수 있어야 한다."""
        d = client.get("/api/v1/snapshot?scenario=inflation_shock").json()
        top = d["market_state"]["hypotheses"][0]
        assert top["label"] == "INFLATION_SHOCK"
        assert any(r["kind"] == "require" and r["passed"] for r in top["matched_rules"])
        assert all("observed" in r and "evaluable" in r for r in top["matched_rules"])

    def test_events_declare_their_extractor(self, client):
        for e in client.get("/api/v1/snapshot").json()["events"]:
            assert e["extractor"] == "rule"
            assert e["validation"]["schema_ok"] is True

    def test_scenarios_are_switchable(self, client):
        quiet = client.get("/api/v1/snapshot?scenario=baseline").json()
        shock = client.get("/api/v1/snapshot?scenario=inflation_shock").json()
        assert quiet["market_state"]["primary_label"] == "NEUTRAL"
        assert shock["market_state"]["primary_label"] == "INFLATION_SHOCK"


class TestSignals:
    def _two_ticks(self, client, scenario="ai_divergence"):
        """괴리는 최소 두 틱이 있어야 확정된다."""
        get_service().clear()
        client.get(f"/api/v1/snapshot?scenario={scenario}")
        get_service()._cache.clear()  # TTL 을 우회해 다음 틱을 강제한다
        return client.get(f"/api/v1/snapshot?scenario={scenario}").json()

    def test_divergences_need_two_ticks(self, client):
        get_service().clear()
        first = client.get("/api/v1/snapshot?scenario=ai_divergence").json()
        assert first["divergences"] == []
        second = self._two_ticks(client)
        assert second["divergences"]

    def test_requirement_7_shape(self, client):
        """AI 뉴스·가격은 긍정적인데 외국인 수급이 동반되지 않는 상황."""
        d = self._two_ticks(client)
        ai = next(t for t in d["themes"] if t["theme_id"] == "ai")
        assert ai["price_momentum"] > 0 and ai["flow_momentum"] < 0
        assert any(
            x["related_theme"] == "ai" and x["type"] == "PRICE_VS_FLOW"
            for x in d["divergences"]
        )

    def test_every_divergence_carries_its_legs(self, client):
        for x in self._two_ticks(client)["divergences"]:
            assert len(x["legs"]) == 2
            assert x["explanation"]
            assert x["duration_periods"] >= 2

    def test_every_alert_carries_a_baseline(self, client):
        """요구 9. 기준선 없는 알림은 스키마가 만들지 못한다."""
        for a in self._two_ticks(client)["alerts"]:
            t = a["trigger"]
            assert {"metric", "current", "baseline", "delta", "threshold"} <= set(t)

    def test_band_filter(self, client):
        self._two_ticks(client)
        all_rows = client.get("/api/v1/divergences?scenario=ai_divergence").json()
        high = client.get(
            "/api/v1/divergences?scenario=ai_divergence&min_band=HIGH"
        ).json()
        assert len(high) <= len(all_rows)
        assert all(r["severity_band"] in ("HIGH", "CRITICAL") for r in high)

    def test_resolved_alerts_hidden_by_default(self, client):
        self._two_ticks(client)
        live = client.get("/api/v1/alerts?scenario=ai_divergence").json()
        every = client.get(
            "/api/v1/alerts?scenario=ai_divergence&include_resolved=true"
        ).json()
        assert len(live) <= len(every)
        assert all(a["state"] != "RESOLVED" for a in live)


class TestCaching:
    def test_repeat_calls_are_consistent(self, client):
        a = client.get("/api/v1/snapshot").json()
        b = client.get("/api/v1/snapshot").json()
        assert a["as_of"] == b["as_of"]

    def test_cache_can_be_cleared(self, client):
        client.get("/api/v1/snapshot")
        get_service().clear()
        assert client.get("/api/v1/snapshot").status_code == 200


class TestHistoryContinuity:
    """
    캐시에 있는 것이 가장 최근 틱이다. 그것을 history 에 붙이지 않으면
    엔진이 보는 '직전 스냅샷' 이 한 틱 밀리고, divergence 의 지속 기간이
    이어지지 않아 결과가 매 틱 나타났다 사라진다.
    """

    def _tick(self, client, scenario="ai_divergence"):
        get_service()._cache.clear()  # TTL 을 우회해 다음 틱을 강제한다
        return client.get(f"/api/v1/snapshot?scenario={scenario}").json()

    def test_divergences_do_not_flicker(self, client):
        get_service().clear()
        counts = [len(self._tick(client)["divergences"]) for _ in range(6)]
        assert counts[0] == 0, "첫 틱은 후보만 있어야 한다"
        assert all(c > 0 for c in counts[1:]), f"괴리가 깜빡인다: {counts}"

    def test_duration_keeps_growing(self, client):
        get_service().clear()
        self._tick(client)
        seen: list[int] = []
        for _ in range(4):
            rows = self._tick(client)["divergences"]
            assert rows
            seen.append(max(d["duration_periods"] for d in rows))
        assert seen == sorted(seen), f"지속 기간이 되돌아갔다: {seen}"
        assert seen[-1] > seen[0]


class TestStream:
    """
    WebSocket 은 폴링을 **대체하지 않고** 보탠다. 소켓이 죽어도 폴링이
    화면을 유지한다.
    """

    def test_first_message_is_the_whole_snapshot(self, client):
        """붙자마자 화면이 채워져야 한다."""
        with client.websocket_connect("/api/v1/stream") as ws:
            msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        for key in ("market_state", "themes", "impact_maps", "data_health"):
            assert key in msg["snapshot"]

    def test_unknown_scenario_says_so_and_closes(self, client):
        """조용히 기본값으로 돌지 않는다."""
        with client.websocket_connect("/api/v1/stream?scenario=nope") as ws:
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "nope" in msg["detail"]

    def test_digest_changes_only_when_something_changes(self, client):
        from marketpulse.api.routes.stream import digest

        a = client.get("/api/v1/snapshot?scenario=baseline").json()
        from marketpulse.models.snapshot import IntelligenceSnapshot

        snap = IntelligenceSnapshot.model_validate(a)
        assert digest(snap) == digest(snap)
        moved = snap.model_copy(
            update={
                "market_state": snap.market_state.model_copy(
                    update={"confidence": snap.market_state.confidence + 0.1}
                )
            }
        )
        assert digest(snap) != digest(moved)
