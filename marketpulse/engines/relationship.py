"""
RelationshipEngine — Impact Map (설계서 STEP 4.7 / 요구 8).

    Event → Theme → Macro Factor → Asset → Sector

사전 정의 관계는 relationships.yaml 에 있고 전부 origin="predefined" 다.
LLM 이 제안한 관계는 여기 섞이지 않고 origin="llm_proposed",
status="candidate" 로 따로 들어와 화면에서 점선으로 그려진다. 불확실한
시장 관계를 확정 사실처럼 제시하지 않기 위한 구분이다 (요구 8, 15-11).

순수 함수다. 그래프 순회에 I/O 가 없다.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.market import Instrument
from ..models.news import NewsEvent
from ..models.relationship import (
    ImpactMap,
    NodeType,
    RelationshipEdge,
    RelationshipNode,
)
from ..models.theme import Theme

ENGINE_VERSION = "0.1.0"

#: 한 맵의 최대 깊이.
#: 요구 8 의 예시 연쇄(사건 → 유가 → 인플레이션 → 금리 → 성장주 → 나스닥)가
#: 6단이라 그것을 담을 수 있어야 한다. 더 깊이 가면 "모든 것이 모든 것에
#: 연결된" 그림이 되어 아무것도 말하지 못한다.
DEFAULT_MAX_DEPTH = 5
#: 동시에 그릴 맵의 수. 화면에 들어가는 만큼만.
DEFAULT_MAP_LIMIT = 3

_PREFIX_TO_TYPE = {
    "event": NodeType.EVENT,
    "theme": NodeType.THEME,
    "macro": NodeType.MACRO_FACTOR,
    "asset": NodeType.ASSET,
    "sector": NodeType.SECTOR,
}

#: 매크로 factor 의 한국어 라벨. 화면에 영문 식별자가 그대로 나가지 않게 한다.
MACRO_LABELS: dict[str, str] = {
    "Growth": "성장",
    "Inflation": "인플레이션",
    "Rates": "금리",
    "USD": "달러",
    "Liquidity": "유동성",
    "RiskAppetite": "위험선호",
    "Credit": "신용",
    "Volatility": "변동성",
    "China": "중국",
    "KoreaFlow": "한국 수급",
    "KoreaBreadth": "한국 시장폭",
}


@lru_cache(maxsize=4)
def load_relationship_spec(config_dir: Path | None = None) -> dict:
    d = config_dir or CONFIG_DIR
    with (d / "relationships.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def reset_relationship_cache() -> None:
    load_relationship_spec.cache_clear()


def predefined_edges(config_dir: Path | None = None) -> list[RelationshipEdge]:
    """YAML 의 관계를 RelationshipEdge 로 읽는다. 전부 predefined 다."""
    spec = load_relationship_spec(config_dir)
    out: list[RelationshipEdge] = []
    for i, e in enumerate(spec.get("edges", [])):
        out.append(
            RelationshipEdge(
                id=f"pre-{i:03d}",
                source_id=e["source"],
                target_id=e["target"],
                direction=e.get("direction", "positive"),
                strength=float(e.get("strength", 0.5)),
                confidence=float(e.get("confidence", 0.5)),
                lag=e.get("lag", "immediate"),
                reason=e.get("reason", ""),
                origin="predefined",
                status="active",
            )
        )
    return out


def _sector_labels(config_dir: Path | None = None) -> dict[str, str]:
    spec = load_relationship_spec(config_dir)
    return {s["id"]: s["label"] for s in spec.get("sectors", [])}


class NodeResolver:
    """노드 id 를 사람이 읽는 라벨로 바꾼다. 라벨은 레지스트리에서 온다."""

    def __init__(
        self,
        themes_by_id: Mapping[str, Theme],
        instruments_by_id: Mapping[str, Instrument],
        events_by_id: Mapping[str, NewsEvent] | None = None,
        *,
        config_dir: Path | None = None,
    ) -> None:
        self.themes = themes_by_id
        self.instruments = instruments_by_id
        self.events = events_by_id or {}
        self.sectors = _sector_labels(config_dir)

    def resolve(self, node_id: str) -> RelationshipNode | None:
        kind, _, ref = node_id.partition(":")
        ntype = _PREFIX_TO_TYPE.get(kind)
        if ntype is None or not ref:
            return None

        if ntype is NodeType.THEME:
            theme = self.themes.get(ref)
            label = theme.name if theme else ref
        elif ntype is NodeType.MACRO_FACTOR:
            label = MACRO_LABELS.get(ref, ref)
        elif ntype is NodeType.ASSET:
            ins = self.instruments.get(ref)
            label = ins.name if ins else ref
        elif ntype is NodeType.SECTOR:
            label = self.sectors.get(ref, ref)
        else:  # EVENT
            event = self.events.get(ref)
            label = event.event if event else ref

        return RelationshipNode(id=node_id, type=ntype, label=label, ref_id=ref)


def traverse(
    roots: Sequence[str],
    edges: Sequence[RelationshipEdge],
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> tuple[list[str], list[RelationshipEdge], int]:
    """
    roots 에서 시작해 나가는 방향으로 BFS.

    Returns: (도달한 노드 id, 사용된 edge, 실제 깊이)

    같은 노드를 두 번 확장하지 않는다. 사이클이 있어도 멈춘다.
    """
    adjacency: dict[str, list[RelationshipEdge]] = {}
    for e in edges:
        adjacency.setdefault(e.source_id, []).append(e)

    seen: set[str] = set(roots)
    order: list[str] = list(roots)
    used: list[RelationshipEdge] = []
    frontier = list(roots)
    depth = 0

    while frontier and depth < max_depth:
        nxt: list[str] = []
        for node in frontier:
            for edge in adjacency.get(node, []):
                used.append(edge)
                if edge.target_id in seen:
                    continue
                seen.add(edge.target_id)
                order.append(edge.target_id)
                nxt.append(edge.target_id)
        if not nxt:
            break
        frontier = nxt
        depth += 1

    return order, used, depth


def build_map(
    roots: Sequence[str],
    resolver: NodeResolver,
    edges: Sequence[RelationshipEdge],
    as_of: datetime,
    *,
    root_event_id: str | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> ImpactMap | None:
    """한 뿌리에서 뻗어나가는 영향 경로를 그린다."""
    node_ids, used, depth = traverse(roots, edges, max_depth=max_depth)
    nodes = [n for n in (resolver.resolve(i) for i in node_ids) if n is not None]
    if len(nodes) < 2:
        # 뿌리 하나뿐이면 그릴 관계가 없다. 빈 그래프를 만들지 않는다.
        return None

    known = {n.id for n in nodes}
    kept = [e for e in used if e.source_id in known and e.target_id in known]
    # 같은 edge 가 여러 경로로 두 번 담길 수 있다.
    unique = list({e.id: e for e in kept}.values())

    return ImpactMap(
        as_of=as_of,
        root_event_id=root_event_id,
        nodes=nodes,
        edges=unique,
        max_depth=depth,
    )


def build_impact_maps(
    events: Sequence[NewsEvent],
    themes_by_id: Mapping[str, Theme],
    instruments_by_id: Mapping[str, Instrument],
    as_of: datetime,
    *,
    proposed_edges: Iterable[RelationshipEdge] = (),
    max_depth: int = DEFAULT_MAX_DEPTH,
    limit: int = DEFAULT_MAP_LIMIT,
    config_dir: Path | None = None,
) -> list[ImpactMap]:
    """
    영향도가 높은 이벤트부터 영향 경로를 그린다.

    테마가 붙지 않은 기사는 건너뛴다. 어디로 뻗어나갈지 알 수 없기 때문이다.
    이벤트가 하나도 쓸 만하지 않으면 테마 단독 맵으로 대체한다 — 뉴스가
    없다고 관계 그래프까지 사라지면 안 된다.
    """
    base = predefined_edges(config_dir)
    proposed = list(proposed_edges)
    edges = base + proposed

    events_by_id = {e.id: e for e in events}
    resolver = NodeResolver(
        themes_by_id, instruments_by_id, events_by_id, config_dir=config_dir
    )

    ranked = sorted(
        (e for e in events if e.themes), key=lambda e: -e.impact_score
    )

    maps: list[ImpactMap] = []
    for event in ranked:
        if len(maps) >= limit:
            break
        # 이벤트를 뿌리로 두고, 그 이벤트가 건드린 테마로 첫 가지를 뻗는다.
        event_node = f"event:{event.id}"
        links = [
            RelationshipEdge(
                id=f"evt-{event.id}-{theme_id}",
                source_id=event_node,
                target_id=f"theme:{theme_id}",
                direction=(
                    "positive"
                    if event.theme_sentiment.get(theme_id, event.sentiment) >= 0
                    else "negative"
                ),
                strength=min(1.0, event.impact_score / 100.0),
                confidence=event.confidence,
                lag="immediate",
                reason=f"기사에서 {theme_id} 테마가 식별되었다",
                origin="predefined" if event.extractor == "rule" else "llm_proposed",
                status="active" if event.extractor == "rule" else "candidate",
            )
            for theme_id in event.themes
            if theme_id in themes_by_id
        ]
        if not links:
            continue
        m = build_map(
            [event_node],
            resolver,
            edges + links,
            as_of,
            root_event_id=event.id,
            max_depth=max_depth,
        )
        if m is not None:
            maps.append(m)

    if maps:
        return maps

    # 뉴스가 없거나 테마가 붙지 않았다. 테마 단독으로라도 그린다.
    for theme_id in themes_by_id:
        node = f"theme:{theme_id}"
        if not any(e.source_id == node for e in edges):
            continue
        m = build_map([node], resolver, edges, as_of, max_depth=max_depth)
        if m is not None:
            maps.append(m)
        if len(maps) >= limit:
            break
    return maps
