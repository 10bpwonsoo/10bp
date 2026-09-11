import { useMemo, useState } from "react";
import type {
  ImpactMap as ImpactMapData,
  NodeType,
  Reaction,
  RelationshipEdge,
  RelationshipNode,
} from "../api/types";
import { Pending } from "./Panel";

/**
 * 요구 8 의 [IMPACT MAP].
 *
 *   사건 → 1단계 → 2단계 → … → n단계
 *
 * 열은 노드의 **종류**가 아니라 사건으로부터의 **전파 단계**다. 종류로
 * 세우면 사건 1개 대 자산 13개가 되어 왼쪽이 비고, 매크로에서 테마로
 * 돌아가는 관계가 뒤로 가는 선을 만든다. 단계로 세우면 열 분포가 고르고
 * 왼쪽에서 오른쪽이 곧 인과 순서가 된다.
 *
 * 노드 색은 **실측 반응**이다. 관계 그래프만 그리면 이 지도는 가설만
 * 보여준다. 이 제품의 1번 질문은 "뉴스의 내러티브와 실제 가격·수급이
 * 일치하는가" 이므로, 예상 부호 옆에 실측을 같이 두어야 지도가 그 질문에
 * 답한다. 예상과 반대로 움직인 노드에는 경고가 붙는다.
 *
 * 두 색 체계를 섞지 않는다.
 *   · 노드 면색 = 가격 방향 (한국 관례: 상승 적, 하락 청)
 *   · 관계 부호 = 선이 아니라 ⊖ 표식
 *   · 관계 출처 = 실선(사전 정의) / 점선(LLM 제안)
 */

const TYPE_TAG: Record<NodeType, string> = {
  EVENT: "사건",
  THEME: "테마",
  MACRO_FACTOR: "매크로",
  SECTOR: "업종",
  ASSET: "자산",
};
const TYPE_MARK: Record<NodeType, string> = {
  EVENT: "◆",
  THEME: "테",
  MACRO_FACTOR: "매",
  SECTOR: "업",
  ASSET: "자",
};

const NODE_W = 148;
const NODE_H = 26;
const COL_GAP = 40;
const ROW_GAP = 8;
const PAD_X = 10;
const PAD_TOP = 26;

/** 점도표의 1σ 당 픽셀. 단계 간격보다 작아야 막대가 옆 칸을 침범하지 않는다. */
const SIGMA_PX = 22;
const DOT_ROW_H = 21;
const DOT_LABEL_W = 146;
const DOT_COL_GAP = 56;

type View = "map" | "list";

interface Placed {
  node: RelationshipNode;
  x: number;
  y: number;
}

/** 실측 z 를 노드 면색으로. 없으면 기본 면색 그대로 둔다 — 0 으로 채우지 않는다. */
function tint(z: number | null): string {
  if (z === null) return "var(--surface-2)";
  const p = Math.min(1, Math.abs(z) / 2.2);
  const token = z >= 0 ? "--up" : "--down";
  return `color-mix(in oklab, var(${token}) ${Math.round(12 + p * 44)}%, var(--surface-2))`;
}
function zColor(z: number | null): string {
  if (z === null) return "var(--faint)";
  return z >= 0 ? "var(--up)" : "var(--down)";
}
function zText(z: number | null): string {
  if (z === null) return "–";
  return `${z > 0 ? "+" : ""}${z.toFixed(1)}σ`;
}
function signText(n: RelationshipNode): string {
  if (n.sign_conflict) return "예상 ?";
  if (n.expected_sign === 0) return "";
  return n.expected_sign > 0 ? "예상 +" : "예상 −";
}
const REACTION_LABEL: Record<Reaction, string> = {
  confirmed: "예상대로 움직였다",
  mismatch: "예상과 반대로 움직였다",
  muted: "유의미하게 움직이지 않았다",
  unknown: "판정할 수 없다",
};
const REL_LABEL: Record<RelationshipEdge["direction"], string> = {
  positive: "정",
  negative: "역",
  ambiguous: "?",
};

function tooltip(n: RelationshipNode, edge: RelationshipEdge | undefined): string {
  const bits = [`${TYPE_TAG[n.type]} · ${n.label}`];
  if (n.hop > 0) bits.push(`${n.hop}단계`);
  const s = signText(n);
  if (s) bits.push(n.sign_conflict ? "경로마다 부호가 다르다" : s);
  if (n.observed_z !== null) {
    bits.push(`실측 ${zText(n.observed_z)}${n.observed_display ? ` (${n.observed_display})` : ""}`);
    bits.push(REACTION_LABEL[n.reaction]);
  }
  if (n.path_strength !== null) {
    // 판정을 믿을지 말지의 근거다. 사슬은 가장 약한 고리만큼만 버틴다.
    bits.push(`경로 최약 고리 ${n.path_strength.toFixed(2)}`);
  }
  if (edge?.reason) bits.push(`← ${edge.reason}`);
  return bits.join("\n");
}

/** 뿌리까지의 대표 경로. 마우스를 올린 노드의 인과 사슬만 남긴다. */
function ancestry(nodeId: string, byId: Map<string, RelationshipNode>, byEdge: Map<string, RelationshipEdge>) {
  const nodes = new Set<string>([nodeId]);
  const edges = new Set<string>();
  let cur = byId.get(nodeId);
  while (cur?.via_edge_id) {
    const e = byEdge.get(cur.via_edge_id);
    if (!e || nodes.has(e.source_id)) break;
    edges.add(e.id);
    nodes.add(e.source_id);
    cur = byId.get(e.source_id);
  }
  return { nodes, edges };
}

export function ImpactMapPanel({ maps }: { maps: ImpactMapData[] }) {
  const [index, setIndex] = useState(0);
  const [view, setView] = useState<View>("map");
  const [focus, setFocus] = useState<string | null>(null);
  const map = maps[Math.min(index, Math.max(0, maps.length - 1))];

  const byId = useMemo(
    () => new Map((map?.nodes ?? []).map((n) => [n.id, n])),
    [map]
  );
  const byEdge = useMemo(
    () => new Map((map?.edges ?? []).map((e) => [e.id, e])),
    [map]
  );

  const layout = useMemo(() => {
    if (!map || map.nodes.length === 0) return null;
    const maxHop = Math.max(...map.nodes.map((n) => n.hop));
    const columns: RelationshipNode[][] = [];
    for (let h = 0; h <= maxHop; h += 1) {
      // 열 안에서는 실측이 큰 것부터. WHAT'S MOVING 과 같은 규칙이다.
      columns.push(
        map.nodes
          .filter((n) => n.hop === h)
          .sort((a, b) => (b.observed_z ?? -99) - (a.observed_z ?? -99))
      );
    }
    const placed = new Map<string, Placed>();
    columns.forEach((col, ci) =>
      col.forEach((node, ri) =>
        placed.set(node.id, {
          node,
          x: PAD_X + ci * (NODE_W + COL_GAP),
          y: PAD_TOP + ri * (NODE_H + ROW_GAP),
        })
      )
    );
    const rows = Math.max(...columns.map((c) => c.length), 1);
    return {
      placed,
      columns,
      width: PAD_X * 2 + columns.length * NODE_W + (columns.length - 1) * COL_GAP,
      height: PAD_TOP + rows * (NODE_H + ROW_GAP) + 6,
    };
  }, [map]);

  /** 점도표에 올릴 것 — 가격이 있는 노드만. 테마·업종은 값이 없다. */
  const measured = useMemo(() => {
    if (!map) return [];
    return map.nodes
      .filter((n) => n.observed_z !== null)
      .sort((a, b) => a.hop - b.hop || Math.abs(b.observed_z!) - Math.abs(a.observed_z!));
  }, [map]);

  /** 목록 보기용 트리. 대표 관계(via_edge_id)를 따라 만든다. */
  const tree = useMemo(() => {
    if (!map) return [];
    const children = new Map<string, RelationshipNode[]>();
    const roots: RelationshipNode[] = [];
    for (const n of map.nodes) {
      const e = n.via_edge_id ? byEdge.get(n.via_edge_id) : undefined;
      if (!e) {
        roots.push(n);
        continue;
      }
      const list = children.get(e.source_id) ?? [];
      list.push(n);
      children.set(e.source_id, list);
    }
    const out: { node: RelationshipNode; depth: number; last: boolean }[] = [];
    const walk = (n: RelationshipNode, depth: number, last: boolean) => {
      out.push({ node: n, depth, last });
      const kids = (children.get(n.id) ?? []).sort(
        (a, b) => (b.observed_z ?? -99) - (a.observed_z ?? -99)
      );
      kids.forEach((k, i) => walk(k, depth + 1, i === kids.length - 1));
    };
    roots.forEach((r) => walk(r, 0, true));
    return out;
  }, [map, byEdge]);

  if (!map || !layout) {
    return (
      <Pending stage="P3">
        표시할 영향 경로가 없습니다. 테마가 식별된 기사가 있어야 사건에서
        출발하는 경로를 그릴 수 있습니다.
      </Pending>
    );
  }

  const rootEvent = map.nodes.find((n) => n.type === "EVENT");
  const hasProposed = map.edges.some((e) => e.origin === "llm_proposed");
  const mismatches = map.nodes.filter((n) => n.reaction === "mismatch");
  const conflicts = map.nodes.filter((n) => n.sign_conflict);
  const lit = focus ? ancestry(focus, byId, byEdge) : null;
  const dim = (on: boolean) => (lit && !on ? 0.28 : 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {maps.length > 1 && (
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }} role="group" aria-label="영향 경로">
            {maps.map((m, i) => {
              const label = m.nodes.find((n) => n.type === "EVENT")?.label ?? `경로 ${i + 1}`;
              return (
                <Toggle
                  key={m.root_event_id ?? i}
                  on={i === index}
                  title={label}
                  onClick={() => {
                    setIndex(i);
                    setFocus(null);
                  }}
                  wide
                >
                  {label}
                </Toggle>
              );
            })}
          </div>
        )}
        <div style={{ display: "flex", gap: 5, marginLeft: "auto" }} role="group" aria-label="보기">
          <Toggle on={view === "map"} onClick={() => setView("map")}>
            지도
          </Toggle>
          <Toggle on={view === "list"} onClick={() => setView("list")}>
            목록
          </Toggle>
        </div>
      </div>

      {rootEvent && (
        <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.45 }}>
          {rootEvent.label}
        </div>
      )}

      <div className="impact-split">
      {view === "map" ? (
        <div style={{ overflowX: "auto" }} onMouseLeave={() => setFocus(null)}>
          <svg
            width={layout.width}
            height={layout.height}
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            role="img"
            aria-label={`영향 경로. 노드 ${map.nodes.length}개, 관계 ${map.edges.length}개, ${map.max_depth}단계까지 전파.`}
            style={{ display: "block", margin: "0 auto" }}
          >
            {layout.columns.map((_, ci) => (
              <text
                key={ci}
                className="mono"
                x={PAD_X + ci * (NODE_W + COL_GAP) + NODE_W / 2}
                y={14}
                fontSize={9}
                textAnchor="middle"
                fill="var(--faint)"
              >
                {ci === 0 ? "사건" : `${ci}단계`}
              </text>
            ))}

            {map.edges.map((e) => {
              const a = layout.placed.get(e.source_id);
              const b = layout.placed.get(e.target_id);
              if (!a || !b) return null;
              const forward = b.x > a.x;
              const x1 = forward ? a.x + NODE_W : a.x;
              const x2 = forward ? b.x : b.x + NODE_W;
              const y1 = a.y + NODE_H / 2;
              const y2 = b.y + NODE_H / 2;
              const mx = (x1 + x2) / 2;
              const on = !lit || lit.edges.has(e.id);
              return (
                <g key={e.id} opacity={dim(on)}>
                  <path
                    d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
                    fill="none"
                    stroke={on && lit ? "var(--accent)" : "var(--rule-hi, var(--surface-3))"}
                    strokeWidth={0.5 + e.strength * 1.1}
                    strokeDasharray={
                      e.origin !== "predefined" ? "3 3" : e.direction === "ambiguous" ? "1 4" : undefined
                    }
                  >
                    <title>{e.reason}</title>
                  </path>
                  {e.direction === "negative" && (
                    <g>
                      <circle
                        cx={x2 - 9}
                        cy={y2}
                        r={4}
                        fill="var(--bg)"
                        stroke="var(--muted)"
                        strokeWidth={1}
                      />
                      <line
                        x1={x2 - 11}
                        y1={y2}
                        x2={x2 - 7}
                        y2={y2}
                        stroke="var(--muted)"
                        strokeWidth={1.2}
                      />
                      <title>역방향 관계 — 원인이 오르면 이쪽은 내린다</title>
                    </g>
                  )}
                </g>
              );
            })}

            {[...layout.placed.values()].map(({ node, x, y }) => {
              const on = !lit || lit.nodes.has(node.id);
              const edge = node.via_edge_id ? byEdge.get(node.via_edge_id) : undefined;
              return (
                <g
                  key={node.id}
                  opacity={dim(on)}
                  onMouseEnter={() => setFocus(node.id)}
                  style={{ cursor: "default" }}
                >
                  <title>{tooltip(node, edge)}</title>
                  <rect
                    x={x}
                    y={y}
                    width={NODE_W}
                    height={NODE_H}
                    rx={2}
                    fill={tint(node.observed_z)}
                    stroke={
                      node.hop === 0
                        ? "var(--accent)"
                        : node.reaction === "mismatch"
                          ? "var(--crit)"
                          : "var(--rule)"
                    }
                    strokeWidth={node.hop === 0 || node.reaction === "mismatch" ? 1.3 : 1}
                  />
                  <text
                    className="mono"
                    x={x + 6}
                    y={y + NODE_H / 2 + 3.4}
                    fontSize={8.5}
                    fill="var(--faint)"
                  >
                    {TYPE_MARK[node.type]}
                  </text>
                  <text
                    x={x + (node.type === "EVENT" ? 18 : 20)}
                    y={y + NODE_H / 2 + 3.6}
                    fontSize={10.5}
                    fill="var(--ink)"
                  >
                    {clip(
                      // 헤드라인 전문은 지도 바로 위에 따로 있다. 상자 안에서는
                      // 첫 구절만 쓴다 — 중간에서 자르면 "…미…" 처럼 읽힌다.
                      node.type === "EVENT" ? node.label.split("…")[0]! : node.label,
                      node.observed_z === null ? 18 : 15
                    )}
                  </text>
                  {node.observed_z !== null && (
                    <text
                      className="num"
                      x={x + NODE_W - 6}
                      y={y + NODE_H / 2 + 3.4}
                      fontSize={9.5}
                      textAnchor="end"
                      fill={zColor(node.observed_z)}
                    >
                      {zText(node.observed_z)}
                    </text>
                  )}
                  {node.reaction === "mismatch" && (
                    <circle cx={x + NODE_W - 3} cy={y + 3} r={3.2} fill="var(--crit)" />
                  )}
                  {node.sign_conflict && (
                    <circle cx={x + NODE_W - 3} cy={y + 3} r={3.2} fill="var(--warn)" />
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      ) : (
        <div className="impact-list" onMouseLeave={() => setFocus(null)}>
          {tree.map(({ node, depth, last }) => {
            const on = !lit || lit.nodes.has(node.id);
            const edge = node.via_edge_id ? byEdge.get(node.via_edge_id) : undefined;
            return (
              <div
                key={node.id}
                className="impact-row"
                style={{ paddingLeft: 4 + depth * 16, opacity: dim(on) }}
                title={tooltip(node, edge)}
                onMouseEnter={() => setFocus(node.id)}
              >
                <span className="mono impact-guide">{depth === 0 ? "" : last ? "└─" : "├─"}</span>
                <span className="mono impact-kind">{TYPE_TAG[node.type]}</span>
                <span className="impact-label">{node.label}</span>
                {edge && (
                  <span
                    className={`mono impact-rel${edge.direction !== "positive" ? " neg" : ""}`}
                  >
                    {REL_LABEL[edge.direction]}·{edge.strength.toFixed(2)}
                  </span>
                )}
                <span className="mono impact-exp">{signText(node)}</span>
                <span
                  className="num impact-z"
                  style={{ color: zColor(node.observed_z) }}
                >
                  {zText(node.observed_z)}
                  {node.reaction === "mismatch" ? " ▲" : ""}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {measured.length > 0 && <ReactionPlot nodes={measured} maxHop={layout.columns.length - 1} />}
      </div>

      <div
        className="mono"
        style={{
          display: "flex",
          gap: 14,
          flexWrap: "wrap",
          fontSize: 9.5,
          color: "var(--faint)",
          borderTop: "1px solid var(--rule-soft)",
          paddingTop: 8,
        }}
      >
        <span>
          {map.max_depth}단계 · 노드 {map.nodes.length} · 관계 {map.edges.length}
        </span>
        <span style={{ color: "var(--up)" }}>상승</span>
        <span style={{ color: "var(--down)" }}>하락</span>
        <span>⊖ 역방향 관계</span>
        {map.edges.some((e) => e.direction === "ambiguous") && (
          <span>점점선 = 기사에서 방향을 읽지 못함</span>
        )}
        {mismatches.length > 0 && (
          <span style={{ color: "var(--crit)" }}>● 예상과 반대 {mismatches.length}건</span>
        )}
        {conflicts.length > 0 && (
          <span style={{ color: "var(--warn)" }}>● 경로 부호 상충 {conflicts.length}건</span>
        )}
        <span>{hasProposed ? "점선 = LLM 제안 관계" : "전부 사전 정의 관계 (실선)"}</span>
      </div>
    </div>
  );
}

/**
 * 확산 점도표 — 단계가 깊어질수록 충격이 살아남는가.
 *
 * 지도는 경로를 보여주고 이것은 크기를 보여준다. 둘은 같은 필드를 쓴다.
 * 가격이 있는 노드만 올린다. 테마 점수는 뉴스·가격·수급의 합성값이라
 * '실측 가격 반응' 칸에 넣으면 내러티브를 내러티브로 검증하게 된다.
 */
function ReactionPlot({ nodes, maxHop }: { nodes: RelationshipNode[]; maxHop: number }) {
  const width = DOT_LABEL_W + (maxHop + 1) * DOT_COL_GAP + 44;
  const height = 24 + nodes.length * DOT_ROW_H + 6;
  return (
    <div className="impact-plot">
      <div
        className="mono"
        style={{ fontSize: 9.5, color: "var(--faint)", letterSpacing: ".1em", marginBottom: 4 }}
      >
        단계별 실측 반응
      </div>
      <div style={{ overflowX: "auto" }}>
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="전파 단계별 실측 반응. 가로는 단계, 막대는 z-score."
          style={{ display: "block" }}
        >
          {Array.from({ length: maxHop + 1 }, (_, h) => {
            const x = DOT_LABEL_W + h * DOT_COL_GAP;
            return (
              <g key={h}>
                <text
                  className="mono"
                  x={x}
                  y={12}
                  fontSize={9}
                  textAnchor="middle"
                  fill="var(--faint)"
                >
                  {h === 0 ? "사건" : `${h}단계`}
                </text>
                <line
                  x1={x}
                  y1={18}
                  x2={x}
                  y2={height - 4}
                  stroke="var(--rule-soft)"
                  strokeDasharray="2 5"
                />
              </g>
            );
          })}
          {nodes.map((n, i) => {
            const y = 24 + i * DOT_ROW_H + DOT_ROW_H / 2;
            const x = DOT_LABEL_W + n.hop * DOT_COL_GAP;
            const z = n.observed_z ?? 0;
            const end = x + z * SIGMA_PX;
            return (
              <g key={n.id}>
                <title>{tooltip(n, undefined)}</title>
                <text x={4} y={y + 3.4} fontSize={10.5} fill="var(--ink-2)">
                  {clip(n.label, 15)}
                </text>
                <text
                  className="mono"
                  x={DOT_LABEL_W - 16}
                  y={y + 3.4}
                  fontSize={9}
                  textAnchor="end"
                  fill={n.reaction === "mismatch" ? "var(--crit)" : "var(--faint)"}
                >
                  {signText(n)}
                </text>
                {n.reaction === "mismatch" && (
                  <circle cx={DOT_LABEL_W - 8} cy={y} r={3} fill="var(--crit)" />
                )}
                <line x1={x} y1={y} x2={end} y2={y} stroke={zColor(z)} strokeWidth={2} />
                <circle cx={end} cy={y} r={3.4} fill={zColor(z)} />
                <text
                  className="num"
                  x={end + (z >= 0 ? 7 : -7)}
                  y={y + 3.4}
                  fontSize={9}
                  textAnchor={z >= 0 ? "start" : "end"}
                  fill="var(--muted)"
                >
                  {zText(z)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function Toggle({
  on,
  onClick,
  title,
  wide,
  children,
}: {
  on: boolean;
  onClick: () => void;
  title?: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      title={title}
      className="mono"
      style={{
        fontSize: 10.5,
        padding: "2px 8px",
        borderRadius: "var(--radius)",
        border: `1px solid ${on ? "var(--accent)" : "var(--rule)"}`,
        background: on ? "var(--accent-wash)" : "transparent",
        color: on ? "var(--accent)" : "var(--muted)",
        maxWidth: wide ? 190 : undefined,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </button>
  );
}

function clip(s: string, max: number): string {
  if (s.length <= max) return s;
  // 헤드라인은 이미 "…" 로 끝나는 경우가 있다. "… 미…" 처럼 두 번 찍지 않는다.
  const head = s.slice(0, max - 1).replace(/[\s…·,]+$/u, "");
  return `${head}…`;
}
