"""RelationshipEngine / Impact Map 테스트 (설계서 STEP 4.7 / 요구 8)."""

from __future__ import annotations

import pytest

from marketpulse.ai.rule_extractor import extract_events
from marketpulse.config.settings import Settings
from marketpulse.engines.orchestrator import run_pipeline
from marketpulse.engines.relationship import (
    DEFAULT_MAX_DEPTH,
    MACRO_LABELS,
    NodeResolver,
    build_impact_maps,
    build_map,
    load_relationship_spec,
    predefined_edges,
    traverse,
)
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
        nodes, used, depth = traverse(["theme:oil"], edges, max_depth=2)
        assert "asset:BRENT" in nodes
        assert "macro:Inflation" in nodes
        assert depth <= 2

    def test_depth_limits_reach(self, edges):
        shallow, _, _ = traverse(["theme:oil"], edges, max_depth=1)
        deep, _, _ = traverse(["theme:oil"], edges, max_depth=4)
        assert len(deep) > len(shallow)

    def test_cycle_does_not_hang(self):
        loop = [
            RelationshipEdge(id="a", source_id="theme:x", target_id="theme:y"),
            RelationshipEdge(id="b", source_id="theme:y", target_id="theme:x"),
        ]
        nodes, _, _ = traverse(["theme:x"], loop, max_depth=10)
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
        nodes, _, _ = traverse(
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
        nodes, _, _ = traverse(["theme:oil"], edges, max_depth=DEFAULT_MAX_DEPTH)
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
