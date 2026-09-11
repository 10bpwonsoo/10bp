"""RelationshipEngine / Impact Map 테스트 (설계서 STEP 4.7 / 요구 8)."""

from __future__ import annotations

import pytest

from marketpulse.ai.rule_extractor import extract_events
from marketpulse.config.settings import Settings
from marketpulse.engines.orchestrator import run_pipeline
from marketpulse.engines.relationship import (
    Observation,
    DEFAULT_MAX_DEPTH,
    MACRO_LABELS,
    NodeResolver,
    build_impact_maps,
    build_map,
    load_relationship_spec,
    predefined_edges,
    traverse,
)
from marketpulse.models.news import NewsEvent
from marketpulse.models.relationship import NodeType, RelationshipEdge
from marketpulse.models.state import FACTOR_NAMES


@pytest.fixture(scope="module")
def edges():
    return predefined_edges()


@pytest.fixture
def resolver(themes, instruments_by_id):
    return NodeResolver({t.id: t for t in themes}, instruments_by_id)


class TestConfig:
    def test_every_reference_resolves(self, edges, themes, instruments_by_id):
        """끊어진 참조가 있으면 그래프에 구멍이 생긴다."""
        spec = load_relationship_spec()
        pools = {
            "theme": {t.id for t in themes},
            "macro": set(FACTOR_NAMES),
            "asset": set(instruments_by_id),
            "sector": {s["id"] for s in spec["sectors"]},
        }
        for e in edges:
            for node in (e.source_id, e.target_id):
                kind, _, ref = node.partition(":")
                assert kind in pools, node
                assert ref in pools[kind], node

    def test_all_predefined(self, edges):
        """
        이 파일의 관계는 전부 사람이 적은 것이다. LLM 제안은 여기 섞이지
        않고 origin="llm_proposed" 로 따로 들어온다 (요구 15-11).
        """
        assert edges
        assert all(e.origin == "predefined" for e in edges)
        assert all(e.status == "active" for e in edges)

    def test_every_edge_has_a_reason(self, edges):
        """근거 없는 관계는 그리지 않는다."""
        for e in edges:
            assert e.reason, e.id
            assert 0.0 <= e.strength <= 1.0
            assert 0.0 <= e.confidence <= 1.0

    def test_macro_labels_cover_every_factor(self):
        assert set(MACRO_LABELS) == set(FACTOR_NAMES)


class TestTraversal:
    def test_follows_outgoing_edges(self, edges):
        nodes, used, depth, hops = traverse(["theme:oil"], edges, max_depth=2)
        assert "asset:BRENT" in nodes
        assert "macro:Inflation" in nodes
        assert depth <= 2

    def test_depth_limits_reach(self, edges):
        shallow, _, _, _ = traverse(["theme:oil"], edges, max_depth=1)
        deep, _, _, _ = traverse(["theme:oil"], edges, max_depth=4)
        assert len(deep) > len(shallow)

    def test_cycle_does_not_hang(self):
        loop = [
            RelationshipEdge(id="a", source_id="theme:x", target_id="theme:y"),
            RelationshipEdge(id="b", source_id="theme:y", target_id="theme:x"),
        ]
        nodes, _, _, _ = traverse(["theme:x"], loop, max_depth=10)
        assert nodes == ["theme:x", "theme:y"]

    def test_isolated_root_yields_no_map(self, resolver, edges, as_of):
        assert build_map(["asset:NATGAS"], resolver, edges, as_of) is None


class TestRequirement8:
    """
    요구 8 의 예시 연쇄.

        Middle East War → Oil → {Energy, Inflation}
        Inflation → Rates → Growth Stocks
    """

    def test_chain_is_reachable(self, edges):
        nodes, _, _, _ = traverse(
            ["theme:geopolitical_risk"], edges, max_depth=DEFAULT_MAX_DEPTH
        )
        for expected in (
            "theme:oil",
            "sector:energy",
            "macro:Inflation",
            "macro:Rates",
            "sector:growth_equity",
        ):
            assert expected in nodes, expected

    def test_growth_equity_link_is_negative(self, edges):
        edge = next(
            e
            for e in edges
            if e.source_id == "macro:Rates" and e.target_id == "sector:growth_equity"
        )
        assert edge.direction == "negative"

    def test_oil_hurts_airlines(self, edges):
        edge = next(
            e
            for e in edges
            if e.source_id == "theme:oil" and e.target_id == "sector:airlines"
        )
        assert edge.direction == "negative"

    def test_full_chain_fits_in_default_depth(self, resolver, edges, as_of):
        """사건 → 유가 → 인플레 → 금리 → 성장주 → 나스닥 이 다 담겨야 한다."""
        nodes, _, _, _ = traverse(["theme:oil"], edges, max_depth=DEFAULT_MAX_DEPTH)
        assert "asset:NDX" in nodes


class TestNodeResolution:
    def test_labels_come_from_registries(self, resolver):
        assert resolver.resolve("theme:ai").label == "AI"
        assert resolver.resolve("asset:BRENT").label == "브렌트 원유"
        assert resolver.resolve("macro:Inflation").label == "인플레이션"
        assert resolver.resolve("sector:energy").label == "에너지"

    def test_types_are_tagged(self, resolver):
        assert resolver.resolve("theme:ai").type is NodeType.THEME
        assert resolver.resolve("macro:Rates").type is NodeType.MACRO_FACTOR
        assert resolver.resolve("asset:VIX").type is NodeType.ASSET
        assert resolver.resolve("sector:defense").type is NodeType.SECTOR

    def test_unknown_prefix_rejected(self, resolver):
        assert resolver.resolve("nonsense:x") is None
        assert resolver.resolve("theme:") is None


class TestImpactMaps:
    @pytest.fixture
    def maps(self, news_adapter, themes, instruments_by_id, as_of):
        events = extract_events(news_adapter.fetch_news(as_of=as_of))
        return build_impact_maps(
            events, {t.id: t for t in themes}, instruments_by_id, as_of
        )

    def test_rooted_at_events(self, maps):
        assert maps
        for m in maps:
            assert m.root_event_id
            assert any(n.type is NodeType.EVENT for n in m.nodes)

    def test_edges_reference_present_nodes(self, maps):
        for m in maps:
            ids = {n.id for n in m.nodes}
            for e in m.edges:
                assert e.source_id in ids and e.target_id in ids

    def test_no_duplicate_edges(self, maps):
        for m in maps:
            ids = [e.id for e in m.edges]
            assert len(ids) == len(set(ids))

    def test_falls_back_to_themes_without_news(self, themes, instruments_by_id, as_of):
        """뉴스가 없다고 관계 그래프까지 사라지면 안 된다."""
        maps = build_impact_maps([], {t.id: t for t in themes}, instruments_by_id, as_of)
        assert maps
        assert all(m.root_event_id is None for m in maps)

    def test_rule_extracted_links_are_not_llm_proposed(self, maps):
        """룰 추출 결과는 LLM 제안이 아니다. 점선으로 그려지면 안 된다."""
        for m in maps:
            for e in m.edges:
                assert e.origin == "predefined"

    def test_reaches_the_pipeline(self, settings):
        snap = run_pipeline(settings)
        assert snap.impact_maps
        assert all(m.nodes and m.edges for m in snap.impact_maps)


class TestReaction:
    """
    지도에 실측을 올린다.

    관계 그래프만 그리면 이 지도는 가설만 보여준다. 요구 7 이 묻는 것은
    "내러티브와 실제 가격·수급이 일치하는가" 이므로 예상 부호 옆에 실측이
    있어야 지도가 그 질문에 답한다.
    """

    @pytest.fixture
    def chain(self):
        return [
            RelationshipEdge(id="e1", source_id="theme:oil", target_id="macro:Inflation"),
            RelationshipEdge(id="e2", source_id="macro:Inflation", target_id="macro:Rates"),
            RelationshipEdge(
                id="e3",
                source_id="macro:Rates",
                target_id="sector:growth_equity",
                direction="negative",
            ),
            RelationshipEdge(
                id="e4", source_id="sector:growth_equity", target_id="asset:NDX"
            ),
        ]

    def test_hop_is_shortest_distance(self, resolver, chain, as_of):
        m = build_map(["theme:oil"], resolver, chain, as_of)
        hops = {n.id: n.hop for n in m.nodes}
        assert hops["theme:oil"] == 0
        assert hops["macro:Inflation"] == 1
        assert hops["asset:NDX"] == 4

    def test_negative_edge_flips_expected_sign(self, resolver, chain, as_of):
        m = build_map(["theme:oil"], resolver, chain, as_of)
        signs = {n.id: n.expected_sign for n in m.nodes}
        assert signs["macro:Rates"] == 1
        # 금리 상승은 성장주에 역방향이고, 그 아래 나스닥까지 이어진다
        assert signs["sector:growth_equity"] == -1
        assert signs["asset:NDX"] == -1

    def test_every_node_names_the_edge_it_came_through(self, resolver, chain, as_of):
        """부호의 계산 근거를 추적할 수 있어야 한다 (요구 15-6)."""
        m = build_map(["theme:oil"], resolver, chain, as_of)
        ids = {e.id for e in m.edges}
        for n in m.nodes:
            if n.hop == 0:
                assert n.via_edge_id is None
            else:
                assert n.via_edge_id in ids

    def test_observed_z_decides_the_verdict(self, resolver, chain, as_of):
        m = build_map(
            ["theme:oil"],
            resolver,
            chain,
            as_of,
            observed={"NDX": Observation(z=-1.6, display="-1.88%")},
        )
        ndx = next(n for n in m.nodes if n.id == "asset:NDX")
        assert ndx.observed_z == -1.6
        assert ndx.observed_display == "-1.88%"
        # 예상 −, 실측 − → 일치
        assert ndx.reaction == "confirmed"

    def test_opposite_move_is_flagged(self, resolver, chain, as_of):
        m = build_map(
            ["theme:oil"], resolver, chain, as_of, observed={"NDX": Observation(z=1.9)}
        )
        ndx = next(n for n in m.nodes if n.id == "asset:NDX")
        assert ndx.reaction == "mismatch"
        assert [n.id for n in m.mismatches] == ["asset:NDX"]

    def test_small_move_is_muted_not_a_verdict(self, resolver, chain, as_of):
        """0.3σ 짜리 움직임으로 내러티브의 옳고 그름을 말하지 않는다."""
        m = build_map(
            ["theme:oil"], resolver, chain, as_of, observed={"NDX": Observation(z=0.2)}
        )
        ndx = next(n for n in m.nodes if n.id == "asset:NDX")
        assert ndx.reaction == "muted"
        assert m.mismatches == []

    def test_conflicting_paths_withhold_the_verdict(self, resolver, as_of):
        """
        같은 단계의 두 경로가 반대 부호를 주면 판정하지 않는다.
        관계가 상충하는 것이지 시장이 틀린 것이 아니다 (개발 규칙 11).
        """
        edges = [
            RelationshipEdge(id="p", source_id="theme:oil", target_id="macro:Inflation"),
            RelationshipEdge(
                id="n",
                source_id="theme:oil",
                target_id="macro:Inflation",
                direction="negative",
                strength=0.9,
            ),
        ]
        m = build_map(
            ["theme:oil"],
            resolver,
            edges,
            as_of,
            observed={"Inflation": Observation(z=2.0)},
        )
        node = next(n for n in m.nodes if n.id == "macro:Inflation")
        assert node.sign_conflict is True
        assert node.reaction == "unknown"
        assert m.mismatches == []

    def test_missing_price_is_not_zero(self, resolver, chain, as_of):
        """가격이 없는 노드를 0 으로 채우지 않는다 (개발 규칙 3)."""
        m = build_map(["theme:oil"], resolver, chain, as_of, observed={})
        for n in m.nodes:
            assert n.observed_z is None
            assert n.reaction == "unknown"

    def test_pipeline_puts_prices_on_the_map(self, settings):
        """
        파이프라인을 통과하면 종목과 매크로 factor 에 실측이 붙는다.
        테마·업종은 가격이 없으므로 비어 있어야 한다 — 테마 점수는 뉴스를
        섞은 합성값이라 '실측 가격 반응' 자리에 넣으면 내러티브를
        내러티브로 검증하게 된다.
        """
        snap = run_pipeline(Settings(scenario="inflation_shock"))
        m = max(snap.impact_maps, key=lambda x: x.max_depth)
        assets = [n for n in m.nodes if n.type is NodeType.ASSET]
        assert assets and all(n.observed_z is not None for n in assets)
        for n in m.nodes:
            if n.type in (NodeType.THEME, NodeType.SECTOR, NodeType.EVENT):
                assert n.observed_z is None

    def test_deterministic_across_runs(self, settings):
        """같은 시나리오는 같은 지도를 만든다 (요구 14)."""
        a = run_pipeline(Settings(scenario="inflation_shock")).impact_maps
        b = run_pipeline(Settings(scenario="inflation_shock")).impact_maps
        key = lambda ms: [  # noqa: E731
            [(n.id, n.hop, n.expected_sign, n.reaction) for n in m.nodes] for m in ms
        ]
        assert key(a) == key(b)


class TestEventThemeDirection:
    """
    사건→테마 관계의 부호는 **방향**에서 온다. 감성이 아니다.

    감성 부호를 방향으로 쓰면 "수입 물가 부담 확대 우려" 가 '물가가
    내린다' 로 읽히고, 그 아래 금리·업종·자산까지 부호가 전부 뒤집힌다.
    """

    def _link(self, event, themes_by_id, instruments_by_id, as_of, theme_id):
        maps = build_impact_maps([event], themes_by_id, instruments_by_id, as_of)
        assert maps
        return next(
            e for e in maps[0].edges if e.target_id == f"theme:{theme_id}"
        )

    @pytest.fixture
    def bad_news_rising(self, as_of):
        """감성은 −, 방향은 ↑. 이 조합이 버그를 드러낸 자리다."""
        return NewsEvent(
            id="x",
            event="수입 물가 부담 확대 우려",
            themes=["inflation"],
            theme_sentiment={"inflation": -39},
            theme_direction={"inflation": "up"},
            impact_score=50,
            timestamp=as_of,
        )

    def test_sign_follows_direction_not_sentiment(
        self, bad_news_rising, themes, instruments_by_id, as_of
    ):
        link = self._link(
            bad_news_rising, {t.id: t for t in themes}, instruments_by_id, as_of, "inflation"
        )
        assert link.direction == "positive"
        assert "상승" in link.reason

    def test_good_news_falling_is_negative(self, themes, instruments_by_id, as_of):
        event = NewsEvent(
            id="y",
            event='연준 위원 "물가 둔화 흐름 확인"',
            themes=["inflation"],
            theme_sentiment={"inflation": 26},  # 호재
            theme_direction={"inflation": "down"},  # 그러나 물가는 내려간다
            impact_score=50,
            timestamp=as_of,
        )
        link = self._link(
            event, {t.id: t for t in themes}, instruments_by_id, as_of, "inflation"
        )
        assert link.direction == "negative"

    def test_unknown_direction_is_ambiguous_not_a_guess(
        self, themes, instruments_by_id, as_of
    ):
        """
        방향을 못 읽었으면 ambiguous 다. 아래 연쇄의 예상 부호가 0 이 되어
        '예상과 반대' 판정이 막힌다. 모르는 것을 아는 것처럼 그리면 그
        아래가 전부 거짓이 된다 (요구 15-11).
        """
        event = NewsEvent(
            id="z",
            event="반도체 대형주에 집중",
            themes=["semiconductor"],
            theme_sentiment={"semiconductor": 40},
            theme_direction={"semiconductor": "neutral"},
            impact_score=50,
            timestamp=as_of,
        )
        maps = build_impact_maps(
            [event], {t.id: t for t in themes}, instruments_by_id, as_of
        )
        link = next(e for e in maps[0].edges if e.target_id == "theme:semiconductor")
        assert link.direction == "ambiguous"
        assert "읽지 못했다" in link.reason
        for n in maps[0].nodes:
            assert n.expected_sign == 0
            assert n.reaction == "unknown"

    def test_missing_direction_field_does_not_fall_back_to_sentiment(
        self, themes, instruments_by_id, as_of
    ):
        """theme_direction 이 아예 비어도 감성으로 대신 채우지 않는다."""
        event = NewsEvent(
            id="w",
            event="무언가",
            themes=["inflation"],
            theme_sentiment={"inflation": 80},
            impact_score=50,
            timestamp=as_of,
        )
        link = self._link(
            event, {t.id: t for t in themes}, instruments_by_id, as_of, "inflation"
        )
        assert link.direction == "ambiguous"

    def test_pipeline_regression(self):
        """
        버그 재현 시나리오. 예전에는 이 지도에서 US 10Y Breakeven ·
        US 10Y Treasury · Nasdaq 100 이 전부 '예상과 반대' 로 찍혔다.
        셋 다 감성 부호를 방향으로 쓴 탓이었다.
        """
        snap = run_pipeline(Settings(scenario="inflation_shock"))
        m = next(
            x for x in snap.impact_maps if x.max_depth == max(y.max_depth for y in snap.impact_maps)
        )
        flagged = {n.label for n in m.mismatches}
        assert "US 10Y Breakeven" not in flagged
        assert "US 10Y Treasury" not in flagged
        assert "Nasdaq 100" not in flagged
        # 기사는 물가 상승을 말한다. 그 부호가 관계에 그대로 실려야 한다.
        link = next(
            e for e in m.edges
            if e.source_id.startswith("event:") and e.target_id == "theme:inflation"
        )
        assert link.direction == "positive"


class TestWeakestLink:
    """사슬은 가장 약한 고리만큼만 버틴다."""

    def test_path_strength_is_the_minimum(self, resolver, as_of):
        edges = [
            RelationshipEdge(
                id="a", source_id="theme:oil", target_id="macro:Inflation", strength=0.9
            ),
            RelationshipEdge(
                id="b", source_id="macro:Inflation", target_id="macro:Rates", strength=0.4
            ),
            RelationshipEdge(
                id="c", source_id="macro:Rates", target_id="asset:US10Y", strength=0.95
            ),
        ]
        m = build_map(["theme:oil"], resolver, edges, as_of)
        by_id = {n.id: n for n in m.nodes}
        assert by_id["theme:oil"].path_strength is None
        assert by_id["macro:Inflation"].path_strength == 0.9
        assert by_id["macro:Rates"].path_strength == 0.4
        assert by_id["asset:US10Y"].path_strength == 0.4

    def test_weak_link_withholds_the_verdict(self, resolver, as_of):
        """
        relationships.yaml 이 스스로 "조달비용과 신용위험이 상쇄한다" 며
        strength 0.45 로 적어 둔 관계를 놓고 "예상과 반대로 움직였다" 고
        말하는 것은 과장이다.
        """
        weak = [
            RelationshipEdge(
                id="a", source_id="macro:Rates", target_id="asset:XLF", strength=0.45
            )
        ]
        strong = [
            RelationshipEdge(
                id="a", source_id="macro:Rates", target_id="asset:XLF", strength=0.90
            )
        ]
        obs = {"XLF": Observation(z=-1.4)}
        quiet = build_map(["macro:Rates"], resolver, weak, as_of, observed=obs)
        loud = build_map(["macro:Rates"], resolver, strong, as_of, observed=obs)
        assert next(n for n in quiet.nodes if n.id == "asset:XLF").reaction == "unknown"
        assert next(n for n in loud.nodes if n.id == "asset:XLF").reaction == "mismatch"
