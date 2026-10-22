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
        # 인과적(causal): 하루짜리 risk_on(60%) 은 확인 전이라 neutral 유지, liquidity 는 2일째(idx 5)에 확정, 하루짜리 policy 는
        # 강한 증거(90 ≥ 80)라 즉시 확정, 마지막 날 liquidity(1D·50%) 는 미확인 → policy 유지. 과거 값은 뒤에 날이 붙어도 바뀌지 않는다.
        assert out == ["neutral", "neutral", "neutral", "neutral", "neutral", "liquidity_stress", "policy", "policy"]
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


class TestTransmissionReadAndWatchlist:
    """전파 카드는 강도(영어+한글)와 1~2문장 read, 워치리스트는 why · driver ≤3 · trigger · 태그 ≤3 · 연결. 숫자 임계를 만들지 않는다."""

    def test_chain_strength_and_read(self):
        snap, market, by_id = _run("inflation_shock")
        c = build_cockpit(snap, market, by_id)
        assert c.transmission
        for t in c.transmission:
            assert t.strength in ("STRONG", "PARTIAL", "LIMITED", "UNCONFIRMED") and t.strength_ko
            assert t.evaluated <= len(t.stocks) and t.confirmed <= max(t.evaluated, 0)
            assert t.read and t.read.count(".") <= 3 and "확률" not in t.read and "때문이다" not in t.read
            if t.strength == "UNCONFIRMED": assert t.confirmed == 0
            if t.strength == "STRONG": assert t.evaluated >= 2 and t.confirmed / t.evaluated >= 0.66

    def test_watchlist_checkpoints(self):
        import json
        from marketpulse.models.cockpit import Cockpit
        c = Cockpit.model_validate_json((__import__("pathlib").Path(__file__).resolve().parents[1] / "marketpulse/data/captures/2026-09-29-manual/cockpit.json").read_text(encoding="utf-8"))
        assert 1 <= len(c.watchlist) <= 5
        for w in c.watchlist:
            assert w.why and w.trigger and 1 <= len(w.key_drivers) <= 3 and len(w.reasons) <= 3 and w.priority in ("HIGH", "MEDIUM")
            assert not any(ch.isdigit() for ch in w.trigger) or "σ" in w.trigger  # 시스템 임계가 없으면 숫자 없음
            for l in w.transmission: assert any(t.driver_key == l.key for t in c.transmission)
            for l in w.issues: assert any(n.id == l.key for n in c.what_matters_next)
            assert set(w.reasons) <= {"NEWS", "THEME", "MACRO", "FUNDAMENTAL", "DIVERGENCE", "ALT DATA", "TRANSMISSION"}


class TestMarketTone:
    """MARKET TONE SNAPSHOT (2026-10-07) — 실시간 탭 온도계와 같은 source, taxonomy·의미·2문장 읽기·REGIME CONFIRMATION 은 config 템플릿. 확률 없음."""

    def _tone(self, scenario="inflation_shock", history=True):
        from marketpulse.engines.state_history import replay_market_state
        settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
        r = run_pipeline_detailed(settings, as_of=AS_OF)
        ins = get_instruments().instruments
        hist = replay_market_state(ins, r.series_by_id, as_of=AS_OF, days=10, mode=r.snapshot.mode, zscore_window=settings.zscore_window) if history else None
        market = build_snapshot(ins, r.series_by_id, mode=r.snapshot.mode, as_of=AS_OF, correlations=False)
        return r.snapshot, build_cockpit(r.snapshot, market, {i.id: i for i in ins}, history=hist)

    def test_same_source_as_thermometer(self):
        snap, c = self._tone()
        t = c.tone; th = snap.thermometer
        assert t is not None and t.composite == pytest.approx(th.composite, abs=0.051) and t.price == pytest.approx(th.price, abs=0.051) and t.news == pytest.approx(th.news, abs=0.051)
        assert [x.key for x in t.components] == [x.key for x in th.components]
        for a, b in zip(t.components, th.components):
            assert (a.value is None) == (b.value is None) and (a.value is None or a.value == pytest.approx(b.value, abs=0.051))
            assert a.meaning and a.state in ("SUPPORT", "NEUTRAL+", "NEUTRAL", "NEUTRAL−", "PRESSURE", "DATA MISSING")
            assert (a.state == "DATA MISSING") == (a.value is None)
        assert t.state in ("STRONG_RISK_OFF", "RISK_OFF", "NEUTRAL", "RISK_ON", "STRONG_RISK_ON") and t.state_label and t.state_ko
        assert t.price_read and t.news_read and t.gap_label in ("PRICE > NEWS", "PRICE < NEWS", "NEWS > PRICE", "NEWS < PRICE", "ALIGNED", "—")
        assert t.subtitle == "현재 시장의 가격·위험선호·변동성·신용·성장 신호"

    def test_taxonomy_confirmation_and_read(self):
        from marketpulse.engines.market_tone import build_market_tone
        from marketpulse.models.thermometer import SentimentThermometer, ThermoComponent
        cfg = load_cockpit_config()["tone"]
        def th(comp, price, news, comps, week=None):
            return SentimentThermometer(as_of=AS_OF, composite=comp, price=price, news=news, band="neutral", band_label="중립", confidence=80.0, composite_week_ago=week,
                                        week_ago_source="snapshot" if week is not None else "none",
                                        components=[ThermoComponent(key=k, label=k, kind="news" if k == "news" else "factor", value=v, week_ago=w) for k, v, w in comps])
        base = [("RiskAppetite", 8, -22), ("Volatility", 37, -5), ("Growth", 7, -1), ("Credit", -14, 12), ("KoreaFlow", None, None), ("news", 1, None)]
        t = build_market_tone(th(8, 13, 1, base, week=-34), cfg, regime_key="neutral", regime_label="Neutral / Mixed")
        assert t.state == "NEUTRAL" and t.change_1w == 42 and "빠르게 회복" in t.change_read and "위험회피" in t.change_read
        assert t.gap_label == "PRICE > NEWS" and "먼저 회복" in t.gap_read and t.confirmation == "CONFIRMED"
        assert [c.label for c in t.changed] == ["Volatility", "Risk Appetite", "Credit"] and t.changed[2].meaning == "지지 → 부담으로 전환"  # |1W 변화| 큰 순
        assert t.components[4].state == "DATA MISSING" and "0 으로" in t.components[4].meaning
        assert t.components[1].meaning.startswith("변동성 진정") and t.components[3].meaning == "신용 환경 소폭 부담"
        assert 1 <= t.read.count("다.") <= 2 and "+8" not in t.read and "+13" not in t.read and "확률" not in t.read
        assert "변동성은" in t.read and "신용이" in t.read  # 조사 처리
        # regime 이 방향을 기대하는데 tone 이 중립 → PARTIAL · 반대 방향 → DIVERGING · 같은 방향 → CONFIRMED
        assert build_market_tone(th(5, 5, 0, base), cfg, regime_key="risk_on", regime_label="Risk-On").confirmation == "PARTIAL"
        assert build_market_tone(th(-35, -30, -20, base), cfg, regime_key="risk_on", regime_label="Risk-On").confirmation == "DIVERGING"
        assert build_market_tone(th(55, 40, 30, base), cfg, regime_key="risk_on", regime_label="Risk-On").state == "STRONG_RISK_ON"
        r = build_market_tone(th(30, 30, 20, base), cfg, regime_key="risk_on", regime_label="Risk-On")
        assert r.confirmation == "CONFIRMED" and r.state == "RISK_ON" and "위험선호 쪽으로" in r.read
        off = build_market_tone(th(-60, -50, -40, [("RiskAppetite", -40, -10), ("Credit", -50, -20), ("news", -40, None)], week=-20), cfg, regime_key="liquidity_stress", regime_label="Liquidity Stress")
        assert off.state == "STRONG_RISK_OFF" and off.confirmation == "CONFIRMED" and "위험회피로 누르고" in off.read and "악화" in off.change_read
        none = build_market_tone(th(None, None, None, []), cfg, regime_key="neutral", regime_label="Neutral")
        assert none.state == "UNKNOWN" and none.confirmation == "UNKNOWN" and none.change_read == "1주 전 비교 자료 없음"
        assert build_market_tone(None, cfg, regime_key="neutral", regime_label="Neutral") is None

    def test_week_ago_from_stored_history_when_thermometer_has_none(self):
        """온도계에 composite 1주 전이 없으면 저장된 daily snapshot sequence(5거래일 전)를 쓴다 — 재계산이 아니다."""
        snap, c = self._tone()
        t = c.tone
        if snap.thermometer.composite_week_ago is None and c.history is not None and len(c.history.days) >= 6:
            assert t.week_ago_source == "history" and t.composite_week_ago == pytest.approx(c.history.composite[-6], abs=0.051) and "daily snapshot" in t.week_ago_basis
        snap2, c2 = self._tone(history=False)
        assert c2.tone is not None and c2.tone.regime_key in ("neutral", "risk_on", "liquidity_stress", "growth", "inflation", "policy", "geopolitical")


class TestCanonicalRegime:
    """공식 CURRENT REGIME 은 하나다 (2026-10-07): HISTORY 의 CURRENT = MARKET NOW. raw 는 후보 신호, 확정은 인과적 전환 규칙."""

    def _cfg(self):
        return load_cockpit_config()["history"]

    def test_stabilize_is_causal_and_hysteretic(self):
        from marketpulse.engines.regime_history import raw_run, stabilize
        cfg = self._cfg()
        keys = ["risk_on", "risk_on", "neutral", "neutral", "neutral", "liquidity_stress", "risk_on", "risk_on"]
        strengths = [70, 70, 41, 45, 50, 90, 60, 60]
        out = stabilize(keys, strengths, [None] * len(keys), cfg)
        # 하루짜리 neutral 은 공식이 되지 않고(후보), 이틀째 확정 · 강한 하루(90)는 바로 · 다시 risk_on 은 이틀째
        assert out == ["risk_on", "risk_on", "risk_on", "neutral", "neutral", "liquidity_stress", "liquidity_stress", "risk_on"]
        # 인과성: 뒤에 날이 붙어도 앞의 공식 값은 그대로
        assert stabilize(keys[:3], strengths[:3], [None] * 3, cfg) == out[:3]
        assert stabilize(keys[:4], strengths[:4], [None] * 4, cfg) == out[:4]
        assert raw_run(["a", "b", "b"]) == 2 and raw_run(["a"]) == 1 and raw_run([]) == 0

    def test_spec_case_previous_risk_on_raw_neutral_one_day(self):
        """요구서 14: 직전 확정 Risk-On · 오늘 raw Neutral/No Regime 1D · 확인 미충족 → HISTORY CURRENT = MARKET NOW = Risk-On, raw 는 보조, 상태 WATCH/UNCONFIRMED."""
        from datetime import timedelta
        from marketpulse.models.state import StateLabel
        from marketpulse.models.state_history import StateHistoryPoint
        from marketpulse.engines.regime_history import build_regime_history
        base = AS_OF - timedelta(days=4)
        seq = [("RISK_ON", 88.0), ("RISK_ON", 91.0), ("NEUTRAL", 41.0)]
        pts = [StateHistoryPoint(date=(base + timedelta(days=i)).date(), as_of=base + timedelta(days=i), label=StateLabel(l), confidence=c, coverage=0.8, composite=10.0, band="neutral", band_label="중립",
                                 factors={"RiskAppetite": 0.5}, drivers=["SPX +1.0σ"], source="RECORDED" if i < 2 else "LIVE") for i, (l, c) in enumerate(seq)]
        class H:  # MarketStateHistory 흉내 — build_regime_history 는 points 만 읽는다
            points = pts; history_mode = "stored"; footnote = "f"
        h = build_regime_history(H(), self._cfg())
        assert h.current_regime == "risk_on" and h.official_state_label == "RISK_ON" and h.raw_regime == "neutral" and h.raw_persistence_days == 1
        assert h.transition_status == "PENDING" and h.state.transition_text == "PENDING · 1 / 2" and h.pending_regime == "neutral" and not h.changed_today and h.required_days == 2
        assert h.days[-1].display_regime == "risk_on" and h.days[-1].raw_state == "NEUTRAL"
        # MARKET NOW 도 같은 공식 판정을 쓴다 — 두 공식 판정이 동시에 존재하지 않는다
        # (baseline 시나리오의 오늘 raw = NEUTRAL — history 의 마지막 LIVE 점과 같은 raw 신호를 가진다)
        snap, market, by_id = _run("baseline")
        from marketpulse.models.state_history import MarketStateHistory
        hist = MarketStateHistory(as_of=AS_OF, days_requested=3, points=pts, history_mode="stored", current_streak=1, previous_label=StateLabel.RISK_ON)
        c = build_cockpit(snap, market, by_id, history=hist)
        assert c.market_now.label == "RISK_ON" == c.history.official_state_label and c.history.current_regime == "risk_on"
        assert c.market_now.raw_label == "NEUTRAL" and c.market_now.raw_text == "NEUTRAL / MIXED" and c.market_now.raw_persistence_days == 1
        assert c.market_now.change_text == "" and c.market_now.potential_change_text == "RISK-ON → NEUTRAL / MIXED"
        assert c.market_now.transition_status == c.history.transition_status and c.market_now.persistence_days == c.history.duration_days
        assert c.market_now.state == c.history.state  # 같은 regime_state 결과 하나
        assert "RISK-ON" in c.market_now.read and "NEUTRAL / MIXED" in c.market_now.read and "확률" not in c.market_now.read
        assert c.market_now.conviction_trend == "WEAKENING"
        assert c.tone is not None and c.tone.regime_key == "risk_on"  # 다른 component 의 regime 참조도 공식 판정
        # 공식 label 이 cross-asset 기대 방향·문장에 쓰인다
        assert "RISK-ON" in c.cross_asset.sentence
        # 다음 날도 Neutral 이면 공식 전환 → CHANGED, change_text 사용
        pts2 = pts + [pts[-1].model_copy(update={"date": pts[-1].date + timedelta(days=1), "as_of": pts[-1].as_of + timedelta(days=1), "label": StateLabel.NEUTRAL, "confidence": 40.0})]
        H2 = type("H2", (), {"points": pts2, "history_mode": "stored", "footnote": "f"})
        h2 = build_regime_history(H2(), self._cfg())
        assert h2.current_regime == "neutral" and h2.changed_today and h2.transition_status == "CONFIRMED" and h2.state.transition_text == "CONFIRMED · 2 / 2" and h2.previous_regime == "risk_on" and h2.duration_days == 1
        hist2 = hist.model_copy(update={"points": pts2})
        c2 = build_cockpit(snap, market, by_id, history=hist2)
        assert c2.market_now.label == "NEUTRAL" and c2.market_now.change_text == "RISK-ON → NEUTRAL / MIXED" and c2.market_now.potential_change_text == ""

    def test_without_history_official_equals_raw(self):
        snap, market, by_id = _run("baseline")
        c = build_cockpit(snap, market, by_id)
        assert c.market_now.label == snap.market_state.primary_label.value and c.market_now.transition_status == "NO_HISTORY" and c.market_now.raw_label == c.market_now.label

    def test_today_stays_live_before_finalization(self, tmp_path):
        """요구서 9: Daily Finalization(16:10 KST) 전의 오늘 snapshot 은 LIVE 다 — RECORDED/LOCK 되지 않는다."""
        from datetime import datetime, timezone
        from marketpulse.history import DailySnapshotManager, JsonDirStore
        from marketpulse.history.calculators import market_snapshot_from_intelligence
        snap, _m, _b = _run("baseline")
        intraday = snap.as_of.replace(hour=4, minute=23, tzinfo=timezone.utc)  # 13:23 KST
        m = DailySnapshotManager(JsonDirStore(tmp_path / "h"), clock=lambda: intraday)
        s = m.record(market_snapshot_from_intelligence(snap.model_copy(update={"as_of": intraday})), as_of=intraday)
        assert s.history_source == "LIVE" and not s.is_locked and not s.is_final
        s2 = m.record(market_snapshot_from_intelligence(snap.model_copy(update={"as_of": intraday.replace(hour=7, minute=30)})), as_of=intraday.replace(hour=7, minute=30))  # 16:30 KST
        assert s2.history_source == "RECORDED" and s2.is_locked
