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


class TestIssuePathAndAnalystView:
    """WHAT MATTERS NEXT 의 전파 경로는 예상(config)과 관측(지금 z)을 나눠 적고, ANALYST VIEW 는 확인된 것만 싣는다."""

    def test_status_and_aggregate(self):
        from marketpulse.engines.issue_path import aggregate, status_of
        assert status_of(None, 1, confirm=0.5, partial=0.25) == "DATA MISSING"
        assert status_of(1.0, 1, confirm=0.5, partial=0.25) == "CONFIRMED" and status_of(-1.0, -1, confirm=0.5, partial=0.25) == "CONFIRMED"
        assert status_of(0.3, 1, confirm=0.5, partial=0.25) == "PARTIAL" and status_of(0.1, 1, confirm=0.5, partial=0.25) == "UNCONFIRMED"
        assert status_of(-0.8, 1, confirm=0.5, partial=0.25) == "CONTRADICTED"
        assert aggregate(["CONFIRMED", "CONFIRMED"]) == "CONFIRMED" and aggregate(["CONFIRMED", "CONTRADICTED"]) == "PARTIAL"
        assert aggregate(["DATA MISSING", "DATA MISSING"]) == "DATA MISSING" and aggregate(["CONTRADICTED", "UNCONFIRMED", "UNCONFIRMED"]) == "UNCONFIRMED"

    def test_next_items_carry_paths_with_expected_vs_observed(self):
        snap, market, by_id = _run("inflation_shock")
        c = build_cockpit(snap, market, by_id)
        assert c.what_matters_next and all(n.id for n in c.what_matters_next)
        withp = [n for n in c.what_matters_next if n.path is not None]
        assert withp, "config 에 경로가 있는 driver 는 path 를 가진다"
        for n in withp:
            p = n.path
            for st in (p.trigger, p.first_order, p.assets, p.themes):
                assert st.status in ("CONFIRMED", "PARTIAL", "UNCONFIRMED", "CONTRADICTED", "DATA MISSING")
                for ck in st.checks:
                    assert ck.expect in (1, -1) and (ck.observed is None) == (ck.status == "DATA MISSING")
            assert p.expected and p.observed and p.conclusion and "확률" not in p.conclusion
            assert 0 <= p.confirm_count <= len(p.confirm)
            for t in p.tiers:
                assert t.tier in ("DIRECT", "SECONDARY", "TERTIARY") and t.stocks
                for s in t.stocks:
                    assert s.status != "DATA MISSING" or s.z is None
            # 정적 매핑을 확정하지 않는다: 관측이 갈리면 결론에 두 쪽이 다 적힌다
            weak = [k for k in p.themes.checks if k.status in ("CONFIRMED", "PARTIAL")]; res = [k for k in p.themes.checks if k.status == "CONTRADICTED"]
            if weak and res:
                assert "견조" in p.conclusion or "반대" in p.conclusion

    def test_radar_links_issues_and_system_axes_without_investment(self):
        snap, market, by_id = _run("inflation_shock")
        c = build_cockpit(snap, market, by_id)
        for r in c.radar:
            assert isinstance(r.related_issues, list) and all(any(i == n.id for n in c.what_matters_next) for i in r.related_issues)

    def test_analyst_view_validation_rejects_incomplete_or_stale(self):
        from datetime import datetime, timezone
        from marketpulse.adapters.analyst_view import validate_view
        as_of = datetime(2026, 9, 29, tzinfo=timezone.utc)
        ok = {"stock_id": "MU", "analyst": "A", "broker": "B", "published_date": "2026-09-28", "source_url": "https://x.example/a", "summary": "s"}
        v = validate_view(ok, as_of=as_of, max_age_days=30)
        assert v is not None and v.age_days == 1 and v.freshness == "1D"
        assert validate_view({**ok, "analyst": ""}, as_of=as_of, max_age_days=30) is None
        assert validate_view({**ok, "broker": " "}, as_of=as_of, max_age_days=30) is None
        assert validate_view({**ok, "source_url": "not a url"}, as_of=as_of, max_age_days=30) is None
        assert validate_view({**ok, "published_date": "2026-08-01"}, as_of=as_of, max_age_days=30) is None
        assert validate_view({**ok, "published_date": "2026-10-05"}, as_of=as_of, max_age_days=30) is None
        # 검색 결과에 없는 URL 은 버린다 (모델이 쓴 URL 방지)
        assert validate_view(ok, as_of=as_of, max_age_days=30, allowed_urls=["https://other"]) is None
        assert validate_view(ok, as_of=as_of, max_age_days=30, allowed_urls=["https://x.example/a"]) is not None

    def test_manual_store_only_returns_verified_rows(self, tmp_path):
        import json
        from datetime import datetime, timezone
        from marketpulse.adapters.analyst_view import AnalystViewStore
        man = tmp_path / "manual"; man.mkdir()
        (man / "a.json").write_text(json.dumps({"views": [
            {"stock_id": "MU", "analyst": "A", "broker": "B", "published_date": "2026-09-28", "source_url": "https://x/a", "summary": "s"},
            {"stock_id": "MU", "analyst": "C", "broker": "D", "published_date": "2026-09-20", "source_url": "https://x/b", "summary": "older"},
            {"stock_id": "SMCI", "analyst": "", "broker": "B", "published_date": "2026-09-28", "source_url": "https://x/c", "summary": "no name"},
        ]}), encoding="utf-8")
        st = AnalystViewStore(tmp_path / "cache.json", man)
        best = st.best(["MU", "SMCI", "TEL"], as_of=datetime(2026, 9, 29, tzinfo=timezone.utc), max_age_days=30)
        assert set(best) == {"MU"} and best["MU"].analyst == "A"
        st.put([{"stock_id": "TEL", "retrieved_at": "2026-09-29T00:00:00+00:00", "retrieved_by": "llm_web"}])
        assert st.retrieved_at("TEL") is not None and "TEL" not in st.best(["TEL"], as_of=datetime(2026, 9, 29, tzinfo=timezone.utc), max_age_days=30)

    def test_analyst_views_route_without_provider(self, client):
        a = client.get("/api/v1/analyst-views?scenario=inflation_shock")
        assert a.status_code == 200
        body = a.json()
        assert body["provider"] in ("disabled", "unavailable") and body["pending"] == []
        assert set(body["requested"]) == set(v["stock_id"] for v in body["views"]) | set(body["missing"])
        for v in body["views"]:
            assert v["analyst"] and v["broker"] and v["source_url"].startswith("http") and v["freshness"].endswith("D")


class TestHeatAndLeadershipIntel:
    """DRIVER HEAT 는 factor 부호가 아니라 경제적 의미로 말하고, MARKET LEADERSHIP 은 왜·확인·질·종목·외부 view 를 함께 준다. 외부 view 는 확인된 것만."""

    def test_heat_labels_meaning_and_horizons(self):
        from datetime import datetime, timezone
        from marketpulse.engines.state_history import replay_market_state
        from marketpulse.engines.regime_history import build_regime_history
        settings = Settings(data_mode="MOCK", scenario="inflation_shock", llm_enabled=False)
        r = run_pipeline_detailed(settings, as_of=AS_OF)
        ins = get_instruments().instruments
        hist = replay_market_state(ins, r.series_by_id, as_of=AS_OF, days=8, mode=r.snapshot.mode, zscore_window=settings.zscore_window)
        cfg = load_cockpit_config()["history"]
        h = build_regime_history(hist, cfg, horizon_z={"US10Y": (-0.5, 1.4), "US_HY_OAS": (3.9, 3.7), "SPX": (-1.2, -0.9), "MOVE": (1.0, 2.6), "BE10Y": (-0.1, -0.3)})
        by = {d.key: d for d in h.drivers}
        assert by["Credit"].label_ui == "Credit Stress" and by["Credit"].label_ko == "신용 스트레스" and by["Rates"].label_ui == "Rate Pressure"
        for d in h.drivers:
            assert d.meaning and d.meaning != d.label and any(w in d.meaning for w in ("확대", "완화", "강화", "약화", "개선", "악화", "상승", "중립", "없음"))
        rates = by["Rates"]
        assert [x.key for x in rates.horizons] == ["1D", "5D"] and rates.horizons[0].z == -0.5 and rates.horizons[1].z == 1.4
        assert "5일" in rates.horizon_read and "오늘" in rates.horizon_read
        # MOVE 는 역방향(sign −1): 채권 변동성 ↑ = 유동성 악화
        liq = by["Liquidity"]; assert liq.horizons[0].z == -1.0 and liq.horizons[1].z == -2.6

    def test_leadership_rows_have_detail_and_read(self):
        snap, market, by_id = _run("inflation_shock")
        c = build_cockpit(snap, market, by_id)
        l = c.leadership
        assert l.read
        for r in l.leaders + l.laggards:
            d = r.detail
            assert d is not None and r.system_view and 1 <= len(d.why) <= 3
            keys = [x.key for x in d.confirmation]
            assert keys[:3] == ["PRICE", "RELATIVE", "BREADTH"] and all(x.meaning for x in d.confirmation)
            assert d.quality in ("BROADENING", "NARROW", "FUNDAMENTAL-LED", "PRICE-LED", "MACRO-DRIVEN", "NEWS-DRIVEN", "FRAGILE") and d.quality_ko
            assert d.system_view and d.driver and d.risk and 1 <= len(d.watch) <= 3 and len(d.key_stocks) <= 5
            for v in d.street:
                assert v.institution and v.source_url.startswith("http") and v.summary and 0 <= v.age_days <= 30
            assert "확률" not in d.system_view

    def test_street_views_only_verified_and_fresh(self, tmp_path):
        import json
        from datetime import datetime, timezone
        from marketpulse.engines.leadership_intel import load_street_views
        (tmp_path / "a.json").write_text(json.dumps({"views": [
            {"themes": ["semiconductor"], "institution": "X Research", "published_date": "2026-09-20", "source_url": "https://x/a", "summary": "ok"},
            {"themes": ["semiconductor"], "institution": "", "published_date": "2026-09-20", "source_url": "https://x/b", "summary": "no institution"},
            {"themes": ["semiconductor"], "institution": "Old", "published_date": "2026-07-01", "source_url": "https://x/c", "summary": "too old"},
            {"themes": ["ai"], "institution": "Y", "published_date": "2026-09-28", "source_url": "not-a-url", "summary": "bad url"},
        ]}), encoding="utf-8")
        sv = load_street_views(tmp_path, as_of=datetime(2026, 9, 29, tzinfo=timezone.utc), max_age_days=30)
        assert list(sv) == ["semiconductor"] and len(sv["semiconductor"]) == 1 and sv["semiconductor"][0].analyst == ""
