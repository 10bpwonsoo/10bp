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

from dataclasses import dataclass
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
from .scoring import load_scoring

ENGINE_VERSION = "0.3.0"


@dataclass(frozen=True)
class Observation:
    """노드 하나의 실측 반응. 가격이 있는 노드에만 존재한다."""

    z: float | None
    display: str | None = None

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
) -> tuple[list[str], list[RelationshipEdge], int, dict[str, int]]:
    """
    roots 에서 시작해 나가는 방향으로 BFS.

    Returns: (도달한 노드 id, 사용된 edge, 실제 깊이, 노드별 최단 홉)

    같은 노드를 두 번 확장하지 않는다. 사이클이 있어도 멈춘다.
    BFS 이므로 hop 은 최단 거리다 — 한 노드가 여러 경로로 닿아도 화면에서
    자리가 흔들리지 않게 하나로 고정된다.
    """
    adjacency: dict[str, list[RelationshipEdge]] = {}
    for e in edges:
        adjacency.setdefault(e.source_id, []).append(e)

    seen: set[str] = set(roots)
    order: list[str] = list(roots)
    used: list[RelationshipEdge] = []
    hops: dict[str, int] = {r: 0 for r in roots}
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
                hops[edge.target_id] = depth + 1
                nxt.append(edge.target_id)
        if not nxt:
            break
        frontier = nxt
        depth += 1

    return order, used, depth, hops


_SIGN = {"positive": 1, "negative": -1, "ambiguous": 0}


def _reaction_floors(config_dir: Path | None = None) -> tuple[float, float]:
    """(판정에 필요한 최소 |z|, 최소 고리 강도)"""
    cfg = load_scoring(config_dir).get("relationship", {})
    return (
        float(cfg.get("reaction_min_abs_z", 0.5)),
        float(cfg.get("reaction_min_link_strength", 0.5)),
    )


def annotate_nodes(
    nodes: Sequence[RelationshipNode],
    edges: Sequence[RelationshipEdge],
    hops: Mapping[str, int],
    observed: Mapping[str, Observation] | None = None,
    *,
    config_dir: Path | None = None,
) -> list[RelationshipNode]:
    """
    각 노드에 전파 단계 · 예상 부호 · 실측 반응을 붙인다.

    예상 부호는 **대표 경로 하나**의 관계 부호 곱이다. 대표 경로는 한 단계
    앞 노드에서 들어오는 관계 중 strength 가 가장 큰 것으로 고른다. 임의로
    고르지 않는 이유는 결정론이 필요해서다 — 같은 입력이면 같은 화면이어야
    한다 (요구 14).

    다른 경로가 반대 부호를 주면 sign_conflict 를 세운다. 그럴 때
    "예상과 어긋났다" 고 단정하지 않는다. 관계가 상충하는 것이지 시장이
    틀린 것이 아니다 (개발 규칙 11).
    """
    z_floor, link_floor = _reaction_floors(config_dir)
    obs = observed or {}
    by_target: dict[str, list[RelationshipEdge]] = {}
    for e in edges:
        by_target.setdefault(e.target_id, []).append(e)

    signs: dict[str, int] = {n.id: 0 for n in nodes if hops.get(n.id, 0) == 0}
    weakest: dict[str, float] = {n.id: 1.0 for n in nodes if hops.get(n.id, 0) == 0}
    out: list[RelationshipNode] = []
    # 홉 순서대로 처리해야 부모 부호가 먼저 정해진다.
    for node in sorted(nodes, key=lambda n: hops.get(n.id, 0)):
        h = hops.get(node.id, 0)
        expected = 0
        conflict = False
        via: str | None = None
        link = 1.0

        if h > 0:
            parents = [
                e for e in by_target.get(node.id, []) if hops.get(e.source_id, -1) == h - 1
            ]
            if parents:
                best = max(parents, key=lambda e: (e.strength, e.id))
                via = best.id

                def carried(edge: RelationshipEdge) -> int:
                    # 뿌리에는 부호가 없다. 첫 관계의 부호가 곧 예상이다.
                    # 그러나 중간 노드의 0 은 "모른다" 는 뜻이므로 그대로
                    # 전파되어야 한다. 모르는 것을 아는 것처럼 그리면 그
                    # 아래 연쇄가 전부 거짓이 된다 (요구 15-11).
                    upstream = 1 if hops.get(edge.source_id, 0) == 0 else signs.get(edge.source_id, 0)
                    return upstream * _SIGN.get(edge.direction, 0)

                expected = carried(best)
                candidates = {carried(e) for e in parents}
                conflict = len({c for c in candidates if c != 0}) > 1
                # 사슬은 가장 약한 고리만큼만 버틴다.
                link = min(weakest.get(best.source_id, 1.0), best.strength)
        signs[node.id] = expected
        weakest[node.id] = link

        o = obs.get(node.ref_id or "")
        z = o.z if o else None
        reaction = "unknown"
        if z is not None and expected != 0 and not conflict and link >= link_floor:
            if abs(z) < z_floor:
                reaction = "muted"
            elif (z > 0) == (expected > 0):
                reaction = "confirmed"
            else:
                reaction = "mismatch"

        out.append(
            node.model_copy(
                update={
                    "hop": h,
                    "expected_sign": expected,
                    "sign_conflict": conflict,
                    "via_edge_id": via,
                    "path_strength": None if h == 0 else round(link, 4),
                    "observed_z": z,
                    "observed_display": o.display if o else None,
                    "reaction": reaction,
                }
            )
        )
    # 원래 순서(BFS 등장 순)를 유지한다. 화면 정렬은 UI 가 정한다.
    order = {n.id: i for i, n in enumerate(nodes)}
    out.sort(key=lambda n: order[n.id])
    return out


def build_map(
    roots: Sequence[str],
    resolver: NodeResolver,
    edges: Sequence[RelationshipEdge],
    as_of: datetime,
    *,
    root_event_id: str | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    observed: Mapping[str, Observation] | None = None,
    config_dir: Path | None = None,
) -> ImpactMap | None:
    """한 뿌리에서 뻗어나가는 영향 경로를 그린다."""
    node_ids, used, depth, hops = traverse(roots, edges, max_depth=max_depth)
    nodes = [n for n in (resolver.resolve(i) for i in node_ids) if n is not None]
    if len(nodes) < 2:
        # 뿌리 하나뿐이면 그릴 관계가 없다. 빈 그래프를 만들지 않는다.
        return None

    known = {n.id for n in nodes}
    kept = [e for e in used if e.source_id in known and e.target_id in known]
    # 같은 edge 가 여러 경로로 두 번 담길 수 있다.
    unique = list({e.id: e for e in kept}.values())
    nodes = annotate_nodes(nodes, unique, hops, observed, config_dir=config_dir)

    return ImpactMap(
        as_of=as_of,
        root_event_id=root_event_id,
        nodes=nodes,
        edges=unique,
        max_depth=depth,
    )


#: 뉴스가 말하는 테마 방향 → 관계 부호.
#: 감성이 아니라 방향을 쓴다. 감성 부호를 방향으로 쓰면 "수입 물가 부담
#: 확대 우려" 가 '물가가 내린다' 로 읽히고, 그 아래 금리·업종·자산까지
#: 부호가 전부 뒤집힌다. 호재냐 악재냐와 오르냐 내리냐는 다른 축이다.
_DIRECTION_TO_SIGN: dict[str, str] = {
    "up": "positive",
    "down": "negative",
    "neutral": "ambiguous",
}


def _event_theme_link(
    event: NewsEvent, event_node: str, theme_id: str
) -> RelationshipEdge:
    """사건에서 테마로 뻗는 첫 가지."""
    heading = event.theme_direction.get(theme_id, "neutral")
    sign = _DIRECTION_TO_SIGN.get(heading, "ambiguous")
    if heading == "neutral":
        # 방향을 못 읽었다. ambiguous 는 아래 연쇄의 예상 부호를 0 으로
        # 만들어 "예상과 반대" 판정을 막는다. 모르는 것을 아는 것처럼
        # 그리지 않는다 (요구 15-11).
        reason = f"기사에서 {theme_id} 테마가 식별되었으나 방향은 읽지 못했다"
    else:
        arrow = "상승" if heading == "up" else "하락"
        reason = f"기사는 {theme_id} 테마의 {arrow} 을 말한다"

    return RelationshipEdge(
        id=f"evt-{event.id}-{theme_id}",
        source_id=event_node,
        target_id=f"theme:{theme_id}",
        direction=sign,
        strength=min(1.0, event.impact_score / 100.0),
        confidence=event.confidence,
        lag="immediate",
        reason=reason,
        origin="predefined" if event.extractor == "rule" else "llm_proposed",
        status="active" if event.extractor == "rule" else "candidate",
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
    observed: Mapping[str, Observation] | None = None,
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
            _event_theme_link(event, event_node, theme_id)
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
            observed=observed,
            config_dir=config_dir,
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
        m = build_map(
            [node],
            resolver,
            edges,
            as_of,
            max_depth=max_depth,
            observed=observed,
            config_dir=config_dir,
        )
        if m is not None:
            maps.append(m)
        if len(maps) >= limit:
            break
    return maps
