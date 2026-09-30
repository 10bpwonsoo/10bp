"""AI Trade Intelligence — 바스켓·상대 z·리더십·breadth·내러티브×가격·매크로 확인·스트레스·전환 조건. 온도계가 아니라 AI 트레이드 자체를 잰다."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marketpulse.adapters.registry import build_alt_adapter
from marketpulse.api.deps import get_ai_regime_service, get_investment_service, get_scenario_check_service, get_service, get_state_history_service
from marketpulse.api.main import create_app
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.ai_regime import basket_instruments, build_ai_regime, load_ai_regime_config
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.models.intelligence import AltInstrument, SourceSpec
from tests.conftest import AS_OF


def _run(scenario: str):
    settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
    r = run_pipeline_detailed(settings, as_of=AS_OF)
    ins = get_instruments().instruments
    market = build_snapshot(ins, r.series_by_id, mode=r.snapshot.mode, as_of=AS_OF, zscore_window=settings.zscore_window, correlations=False)
    specs = [AltInstrument(id=m["id"], name=m.get("name", m["id"]), group="ai", asset_class="equity", unit="price", sources=[SourceSpec(provider="yahoo", symbol=str(m["symbol"]))], source_type="EXCHANGE") for m in basket_instruments()]
    basket = build_alt_adapter(settings).fetch_series([], specs, [], bars=120, as_of=AS_OF)
    return r.snapshot, market, r.series_by_id, basket, {i.id: i for i in ins}


def _shocked(basket, pct_per_day: float, days: int = 5):
    """모의 바스켓의 마지막 며칠을 일정 비율로 밀어 방향을 결정적으로 만든다 — 시나리오 파일에는 AI 종목 충격이 없다."""
    out = {}
    for k, s in basket.items():
        vals = list(s.values)
        for i in range(days, 0, -1):
            vals[-i] = vals[-i - 1] * (1.0 + pct_per_day)
        out[k] = s.model_copy(update={"values": vals})
    return out


def _build(scenario: str, basket=None, shock: float | None = None, benchmarks_too: bool = False):
    snap, market, series, bk, by_id = _run(scenario)
    if shock is not None:
        bk = _shocked(bk, shock)
        if benchmarks_too:  # 벤치마크도 같이 밀면 상대 z 는 제자리 — '시장과 같이 빠진다'
            series = {**series, **_shocked({k: series[k] for k in ("NDX", "SPX") if k in series}, shock)}
    t = snap.thermometer
    return build_ai_regime(market, series, bk if basket is None else basket, snap.themes, snap.events, by_id, market_label=snap.market_state.primary_label.value,
                           market_confidence=snap.market_state.confidence, thermometer=t.composite if t else None, band=t.band if t else None, as_of=AS_OF)


class TestEngine:
    def test_shocked_basket_up_with_broad_breadth_is_confirmed_risk_on_or_narrowing(self):
        """바스켓 5일 +6%: 절대 상승. breadth 가 넓으면 CONFIRMED AI RISK-ON, 좁으면 LEADERSHIP NARROWING — 둘 중 하나여야 한다."""
        r = _build("baseline", shock=0.012)
        assert r.ai_vs_market.abs_direction == "up" and r.ai_vs_market.rel_verdict == "outperform"
        assert r.regime in ("confirmed_risk_on", "leadership_narrowing", "price_resilience")
        assert r.breadth.above_ma5_pct == 100.0  # 전 종목이 5일 연속 올랐다

    def test_ai_sentiment_mock_is_narrative_ahead_of_price(self):
        """모의 AI 센티(뉴스는 뜨겁고 가격은 제자리·하락): 2×2 는 NARRATIVE AHEAD, 판정도 그것."""
        r = _build("ai_sentiment", shock=-0.006, benchmarks_too=True)  # 바스켓·Nasdaq 같이 5일 −3%: 뉴스↑ 가격↓, 상대는 제자리
        assert r.narrative.news_tone is not None and r.narrative.news_tone >= 10
        assert r.ai_vs_market.abs_direction == "down" and r.ai_vs_market.rel_verdict != "underperform"
        assert r.narrative.quadrant == "narrative_ahead"
        assert r.regime == "narrative_ahead" and "NARRATIVE AHEAD" in r.regime_label
        assert r.ai_vs_market.members_used == len({str(m) for g in load_ai_regime_config()["groups"] if g["key"] in load_ai_regime_config()["basket_groups"] for m in g["members"]})
        for w in ("확률", "probab", "시장 온도"):
            assert w not in r.headline

    def test_relative_metrics_are_basket_minus_benchmark(self):
        r = _build("baseline")
        a = r.ai_vs_market
        assert a.basket_ret_5d is not None and a.ndx_ret_5d is not None
        assert a.rel_ndx_5d is not None and abs(a.rel_ndx_5d) < 60
        assert a.rel_ndx_z_5d is not None and a.basket_z_5d is not None
        assert a.abs_direction in ("up", "down", "flat") and a.rel_verdict in ("outperform", "inline", "underperform")
        # 그룹 상대 = 그룹 수익 − 벤치마크 수익 (반올림 오차 안)
        for g in r.leadership.groups:
            if g.ret_5d is not None and g.rel_5d is not None and g.benchmark == "NDX":
                assert g.rel_5d == pytest.approx(g.ret_5d - a.ndx_ret_5d, abs=0.02)

    def test_groups_leadership_and_breadth(self):
        r = _build("baseline")
        keys = [g.key for g in r.leadership.groups]
        for k in ("semis_compute", "memory", "hyperscalers", "networking_infra", "power_datacenter", "software_app"):
            assert k in keys
        korea = next(g for g in r.leadership.groups if g.key == "korea_ai")
        assert not korea.in_basket and korea.benchmark == "KOSPI"
        ranked = [g for g in r.leadership.groups if g.rank_1w is not None]
        assert [g.rank_1w for g in sorted(ranked, key=lambda g: -(g.rel_5d or 0))] == list(range(1, len(ranked) + 1))
        assert r.leadership.leader_1w == next(g.key for g in ranked if g.rank_1w == 1)
        assert r.leadership.rotation in ("none", "rotating", "early")
        b = r.breadth
        assert b.members > 0 and b.above_ma20_pct is not None and 0 <= b.above_ma20_pct <= 100
        assert b.above_ma5_pct is not None and b.advancing_pct is not None and b.change_1w_pts is not None
        assert b.trend in ("widening", "narrowing", "stable")

    def test_missing_basket_series_is_reported_not_zeroed(self):
        snap, market, series, bk, by_id = _run("baseline")
        bk = {k: v for k, v in bk.items() if k not in ("NVDA", "MSFT")}
        r = build_ai_regime(market, series, bk, snap.themes, snap.events, by_id, market_label="NEUTRAL", market_confidence=0.0, as_of=AS_OF)
        assert any("NVDA" in m and "MSFT" in m for m in r.missing)
        rows = {m.id: m for m in r.members}
        assert not rows["NVDA"].available and rows["NVDA"].ret_5d is None
        r2 = build_ai_regime(market, series, {}, snap.themes, snap.events, by_id, market_label="NEUTRAL", market_confidence=0.0, as_of=AS_OF)
        assert r2.regime == "unknown" and r2.ai_vs_market.basket_z is None and r2.breadth.above_ma20_pct is None

    def test_ai_specific_derisking_when_basket_falls_but_market_does_not(self):
        """바스켓만 5일 −6%: Nasdaq 대비 −1σ 아래 → AI-SPECIFIC DE-RISKING, 매크로 판정도 ai_specific, 상대 z 트리거 충족."""
        r = _build("ai_sentiment", shock=-0.012)
        assert r.ai_vs_market.rel_ndx_z_5d is not None and r.ai_vs_market.rel_ndx_z_5d <= -1.0
        assert r.regime == "ai_specific_derisking" and r.macro.verdict == "ai_specific"
        assert next(t for t in r.triggers if t.metric == "AI_REL_NDX_Z5").met
        assert r.stress.level in ("MODERATE", "HIGH")

    def test_macro_confirmation_and_stress_and_triggers(self):
        r = _build("ai_sentiment", shock=-0.012)
        assert {row.status for row in r.macro.rows} <= {"EXPLAINS", "DOES_NOT_EXPLAIN", "NEUTRAL", "MISSING"}
        assert r.macro.verdict in ("macro_driven", "ai_specific", "mixed", "not_weak", "unknown")
        assert r.stress.level in ("LOW", "MODERATE", "HIGH", "UNKNOWN") and r.stress.max_score >= r.stress.score
        assert 3 <= len(r.triggers) <= 5 and all(t.condition and t.current for t in r.triggers)
        assert r.release
        assert r.context.market_label and "맥락" in r.context.note

    def test_driver_score_is_weighted_clipped_mean(self):
        r = _build("baseline")
        cfg = load_ai_regime_config()
        for d in r.drivers:
            avail = [e for e in d.evidence if e.available]
            if not avail:
                continue
            num = sum(e.contribution for e in avail); den = sum(e.weight for e in avail)
            assert d.score == pytest.approx(100 * num / den, abs=0.15)
            for e in avail:
                assert abs(e.contribution) <= e.weight + 1e-9
                if e.kind == "price":
                    assert e.contribution == pytest.approx(max(-1, min(1, e.sign * e.value / cfg["z_ref"])) * e.weight, abs=0.01)

    def test_narrative_drivers_are_keyword_rules_over_ai_events(self):
        r = _build("ai_sentiment")
        keys = {d.key for d in r.narrative.drivers}
        assert {"capex", "gpu_demand", "hyperscaler_spending", "monetization", "competition", "regulation", "valuation"} <= keys
        assert sum(d.count for d in r.narrative.drivers) >= 0 and "룰 기반" in r.narrative.method
        for d in r.narrative.drivers:
            assert (d.tone is None) == (d.count == 0)


@pytest.fixture
def client() -> TestClient:
    for svc in (get_service(), get_state_history_service(), get_investment_service(), get_scenario_check_service(), get_ai_regime_service()):
        svc.clear()
    return TestClient(create_app())


class TestApi:
    def test_route(self, client):
        a = client.get("/api/v1/ai-regime?scenario=ai_sentiment")
        assert a.status_code == 200
        body = a.json()
        for k in ("regime_label", "ai_vs_market", "drivers", "leadership", "breadth", "narrative", "macro", "stress", "triggers", "context", "checks"):
            assert k in body
        assert client.get("/api/v1/ai-regime?scenario=ai_sentiment").json() == body

    def test_ai_tab_focus_is_ai_regime(self, client):
        checks = client.get("/api/v1/scenario-check?scenario=ai_sentiment").json()
        assert next(c for c in checks if c["name"] == "ai_sentiment")["focus"] == "ai_regime"
        # AI 센티2 — 같은 시나리오를 확장 화면으로 한 번 더. 서명·일치도는 같고 탭 이름·focus 만 다르다
        c2 = next(c for c in checks if c["name"] == "ai_sentiment2")
        assert c2["focus"] == "ai_regime_full" and c2["title"].startswith("AI 센티2")
        assert c2["match_score"] == next(c for c in checks if c["name"] == "ai_sentiment")["match_score"]


class TestValueChain:
    """확장 층 — 반도체는 Fundamental Confirmation Layer. 값이 없으면 N/A, 단일 점수 없음."""

    def test_extension_blocks_exist_and_are_consistent(self):
        r = _build("baseline")
        assert len(r.transmission.stages) == 9 and r.transmission.sentence
        assert {s.status for s in r.transmission.stages} <= {"ACCELERATING", "POSITIVE", "STRONG", "IMPROVING", "STABLE", "MIXED", "DETERIORATING", "UNCONFIRMED"}
        assert next(s for s in r.transmission.stages if s.key == "eps").status == "UNCONFIRMED"  # 컨센서스 없음 — 임의 값 없음
        assert len(r.value_chain.segments) == 10 and len(r.value_chain.leadership) <= 4 and len(r.value_chain.lagging) <= 3
        assert not set(r.value_chain.leadership) & set(r.value_chain.lagging)
        assert all(s.eps is None and "컨센서스 없음" in s.eps_note for s in r.value_chain.segments)
        assert len(r.semi_confirmation.areas) == 6 and len(r.semi_confirmation.memory) == 6
        assert r.fundamental_confirmation.level in ("STRONG", "PARTIAL", "WEAK", "UNCONFIRMED")
        assert "FUNDAMENTALS" in r.regime_subtitle and r.regime_label in r.regime_subtitle
        assert [x.key for x in r.status_strip][-1] == "fundamental" and r.summary
        assert len(r.expectation_gap) == 10 and all(g.note for g in r.expectation_gap)
        assert 1 <= len(r.what_matters) <= 5 and all(m.status in ("CONFIRMING", "WATCH", "DETERIORATING") for m in r.what_matters)

    def test_stock_axes_are_separate_and_reasoned(self):
        r = _build("ai_sentiment", shock=-0.012)
        assert r.stocks and all(len(s.axes) == 4 and [a.key for a in s.axes] == ["theme", "fundamental", "market", "macro"] for s in r.stocks)
        assert all(s.interpretation and s.eps_revision == "N/A" for s in r.stocks)  # EPS 컨센서스 없음 → N/A
        assert all(s.overall in ("STRONG", "CONFIRMED", "MIXED", "UNCONFIRMED", "NEGATIVE PRESSURE", "NO DATA") for s in r.stocks)
        for w in ("매수", "매도", "목표"):
            assert all(w not in s.interpretation for s in r.stocks)
        buckets = {b.key: b for b in r.radar}
        assert set(buckets) == {"strongest", "improving", "narrative_ahead", "fundamentals_ahead", "macro_pressure"}
        assert all(i["reason"] for b in r.radar for i in b.items)
        assert all(n.confirmation for n in r.news_impact)

    def test_missing_memory_data_is_na_not_zero(self):
        r = _build("baseline")  # investment 없음 → 메모리 행 전부 계열 없음
        assert all(m.status == "N/A" and m.value is None for m in r.semi_confirmation.memory)
        assert next(a for a in r.semi_confirmation.areas if a.key == "commodity").status == "UNCONFIRMED"


class TestSentiment:
    """AI SENTIMENT · GREED & FEAR — 다섯 구성요소의 가중 평균(0~100). 확률이 아니라 현재 상태. 결측은 분모에서 뺀다."""

    def test_index_is_weighted_mean_of_available_components_and_bands_match_config(self):
        r = _build("baseline")
        s = r.sentiment
        assert s is not None and len(s.components) == 5 and [c.key for c in s.components] == ["narrative", "price", "breadth", "fundamentals", "macro"]
        cfg = load_ai_regime_config()["sentiment"]
        avail = [c for c in s.components if c.score is not None]
        if s.index is not None:
            assert s.index == pytest.approx(sum(c.score * c.weight for c in avail) / sum(c.weight for c in avail), abs=0.15)
            assert 0 <= s.index <= 100
            band = next(b for b in cfg["bands"] if s.index >= b["min"])
            assert s.state == band["key"] and s.state_label == band["label"] and s.state_ko == band["ko"]
        for c in s.components:
            ins = [i for i in c.inputs if i.available]
            if ins:
                assert c.score == pytest.approx(sum(i.score * i.weight for i in ins) / sum(i.weight for i in ins), abs=0.15)
                assert 0 <= c.score <= 100 and c.read
            for i in c.inputs:
                assert (i.score is None) == (not i.available)
                if not i.available:
                    assert i.note  # 결측은 이유가 있고 0 으로 채우지 않는다
        assert s.coverage <= 1.0 and s.bands and s.read and s.secondary_label
        for w in ("확률", "probab", "매수", "매도", "전망"):
            assert w not in s.read  # 심리 상태 문장은 확률·추천·전망을 말하지 않는다
        assert "확률" in s.note and "아니다" in s.note  # 그리고 지표 설명은 그것이 아님을 명시한다

    def test_components_are_taken_from_existing_regime_values_not_new_judgements(self):
        """PRICE 는 바스켓 z·상대 z, BREADTH 는 breadth 비율, MACRO 는 매크로 행 z × 기대 부호 — 이미 계산된 값의 재표현이다."""
        r = _build("baseline")
        s = r.sentiment; cfg = load_ai_regime_config()["sentiment"]
        price = next(c for c in s.components if c.key == "price"); zref = float(cfg["z_ref"])
        bp = next(i for i in price.inputs if i.id == "basket_price")
        assert bp.value == r.ai_vs_market.basket_z and bp.score == pytest.approx(50 + 50 * max(-1, min(1, r.ai_vs_market.basket_z / zref)), abs=0.1)
        breadth = next(c for c in s.components if c.key == "breadth")
        assert next(i for i in breadth.inputs if i.id == "above_ma20").score == r.breadth.above_ma20_pct
        macro = next(c for c in s.components if c.key == "macro")
        for i in macro.inputs:
            row = next((m for m in r.macro.rows if m.key == {"credit": "hy"}.get(i.id, i.id)), None)
            if row is not None and row.z is not None:
                assert i.value == pytest.approx(row.z * row.expected_sign, abs=0.01)
        fund = next(c for c in s.components if c.key == "fundamentals")
        assert not next(i for i in fund.inputs if i.id == "eps").available  # 컨센서스 없음 → 결측, 0 아님
        assert not next(i for i in fund.inputs if i.id == "commodity_memory").available

    def test_secondary_state_structure_and_history_basis(self):
        r = _build("ai_sentiment", shock=-0.006, benchmarks_too=True)  # 뉴스 ↑ · 가격 ↓
        s = r.sentiment; cfg = load_ai_regime_config()["sentiment"]
        keys = {x["key"] for x in cfg["secondary"]["rules"]} | {"none"}
        assert s.secondary_key in keys
        by = {c.key: c.score for c in s.components}
        if by["narrative"] is not None and by["price"] is not None and by["narrative"] - by["price"] >= cfg["secondary"]["gap"]:
            assert s.secondary_key in ("narrative_ahead", "fundamentals_over_price", "macro_capped", "macro_supported", "fragile")
        assert len(s.support) <= 3 and len(s.pressure) <= 3
        assert all(f.score >= cfg["structure"]["support_min"] for f in s.support) and all(f.score <= cfg["structure"]["pressure_max"] for f in s.pressure)
        h = s.history
        assert h.days == cfg["history"]["days"] and len(h.points) <= h.days
        assert set(h.basis) <= {"narrative", "price", "breadth", "fundamentals", "macro"}
        assert "fundamentals" not in h.basis and "fundamentals" in h.excluded  # 메모리·EPS 는 날짜별 계열이 없다 — 채워 넣지 않는다
        for p in h.points:
            if p.index is not None:
                use = [(p.components[k], next(c.weight for c in s.components if c.key == k)) for k in h.basis]
                assert p.index == pytest.approx(sum(v * w for v, w in use) / sum(w for _, w in use), abs=0.15)
        if h.change_1d is not None:
            assert h.change_1d == pytest.approx(h.points[-1].index - h.points[-2].index, abs=0.15)
        assert "기준" in h.note or "이력" in h.note

    def test_missing_basket_yields_no_index_and_no_fabricated_history(self):
        snap, market, series, bk, by_id = _run("baseline")
        r = build_ai_regime(market, series, {}, snap.themes, snap.events, by_id, market_label="NEUTRAL", market_confidence=0.0, as_of=AS_OF)
        s = r.sentiment
        assert s is not None
        price = next(c for c in s.components if c.key == "price"); breadth = next(c for c in s.components if c.key == "breadth")
        assert price.score is None and breadth.score is None and price.coverage == 0.0
        assert s.coverage < 1.0
        assert all(p.index is None for p in s.history.points) or not s.history.points
