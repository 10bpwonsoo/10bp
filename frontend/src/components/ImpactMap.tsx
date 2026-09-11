import { useMemo, useState } from "react";
import type { ImpactMap as ImpactMapData, NodeType, RelationshipNode } from "../api/types";
import { Pending } from "./Panel";

/**
 * 요구 8 의 [IMPACT MAP].
 *
 *   Event → Theme → Macro Factor → Asset → Sector
 *
 * 노드를 종류별 열에 세우고 관계를 곡선으로 잇는다. 층위가 눈으로 읽혀야
 * "무엇이 무엇을 통해 무엇에 닿는지" 를 따라갈 수 있다.
 *
 * 사전 정의 관계는 실선, LLM 이 제안한 관계는 점선이다. 불확실한 시장
 * 관계를 확정 사실처럼 그리지 않기 위한 구분이다.
 */
const COLUMNS: NodeType[] = ["EVENT", "THEME", "MACRO_FACTOR", "SECTOR", "ASSET"];
const COLUMN_LABEL: Record<NodeType, string> = {
  EVENT: "사건",
  THEME: "테마",
  MACRO_FACTOR: "매크로",
  SECTOR: "업종",
  ASSET: "자산",
};

const NODE_W = 112;
const NODE_H = 26;
const COL_GAP = 54;
const ROW_GAP = 9;
const PAD_X = 10;
const PAD_TOP = 24;

interface Placed {
  node: RelationshipNode;
  x: number;
  y: number;
}

export function ImpactMapPanel({ maps }: { maps: ImpactMapData[] }) {
  const [index, setIndex] = useState(0);
  const map = maps[Math.min(index, Math.max(0, maps.length - 1))];

  const layout = useMemo(() => {
    if (!map) return null;
    const byColumn = COLUMNS.map((t) => map.nodes.filter((n) => n.type === t));
    const used = byColumn.filter((col) => col.length > 0);
    const usedTypes = COLUMNS.filter((_, i) => byColumn[i]!.length > 0);

    const placed = new Map<string, Placed>();
    used.forEach((col, ci) => {
      col.forEach((node, ri) => {
        placed.set(node.id, {
          node,
          x: PAD_X + ci * (NODE_W + COL_GAP),
          y: PAD_TOP + ri * (NODE_H + ROW_GAP),
        });
      });
    });

    const width = PAD_X * 2 + used.length * NODE_W + Math.max(0, used.length - 1) * COL_GAP;
    const rows = Math.max(...used.map((c) => c.length), 1);
    const height = PAD_TOP + rows * (NODE_H + ROW_GAP) + 6;
    return { placed, width, height, usedTypes, used };
  }, [map]);

  if (!map || !layout) {
    return (
      <Pending stage="P3">
        표시할 영향 경로가 없습니다. 테마가 식별된 기사가 있어야 사건에서
        출발하는 경로를 그릴 수 있습니다.
      </Pending>
    );
  }

  const { placed, width, height, usedTypes, used } = layout;
  const rootEvent = map.nodes.find((n) => n.type === "EVENT");
  const hasProposed = map.edges.some((e) => e.origin === "llm_proposed");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
      {maps.length > 1 && (
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }} role="group" aria-label="영향 경로">
          {maps.map((m, i) => {
            const label = m.nodes.find((n) => n.type === "EVENT")?.label ?? `경로 ${i + 1}`;
            const on = i === index;
            return (
              <button
                key={m.root_event_id ?? i}
                type="button"
                onClick={() => setIndex(i)}
                aria-pressed={on}
                title={label}
                className="mono"
                style={{
                  fontSize: 10.5,
                  padding: "2px 8px",
                  borderRadius: "var(--radius)",
                  border: `1px solid ${on ? "var(--accent)" : "var(--rule)"}`,
                  background: on ? "var(--accent-wash)" : "transparent",
                  color: on ? "var(--accent)" : "var(--muted)",
                  maxWidth: 190,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      {rootEvent && (
        <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.45 }}>
          {rootEvent.label}
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{ display: "block", width: "100%", minWidth: Math.min(width, 560), height: "auto" }}
          role="img"
          aria-label={`영향 경로 그래프. 노드 ${map.nodes.length}개, 관계 ${map.edges.length}개, 깊이 ${map.max_depth}.`}
        >
          {usedTypes.map((t, ci) => (
            <text
              key={t}
              x={PAD_X + ci * (NODE_W + COL_GAP) + NODE_W / 2}
              y={12}
              textAnchor="middle"
              fontSize="8.5"
              fill="var(--faint)"
              fontFamily="var(--font-mono)"
              letterSpacing="0.08em"
            >
              {COLUMN_LABEL[t]}
            </text>
          ))}

          {map.edges.map((e) => {
            const a = placed.get(e.source_id);
            const b = placed.get(e.target_id);
            if (!a || !b) return null;
            const x1 = a.x + NODE_W;
            const y1 = a.y + NODE_H / 2;
            const x2 = b.x;
            const y2 = b.y + NODE_H / 2;
            const mid = (x1 + x2) / 2;
            const color = e.direction === "negative" ? "var(--down)" : "var(--up)";
            return (
              <path
                key={e.id}
                d={`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`}
                fill="none"
                stroke={color}
                strokeWidth={0.6 + e.strength * 1.4}
                strokeOpacity={0.25 + e.confidence * 0.45}
                strokeDasharray={e.origin === "predefined" ? undefined : "3 3"}
              >
                <title>
                  {`${e.direction === "negative" ? "역방향" : "정방향"} · 강도 ${e.strength.toFixed(2)} · 신뢰 ${e.confidence.toFixed(2)} · ${e.lag}\n${e.reason}${e.origin === "predefined" ? "" : "\n(LLM 제안 관계 — 사전 정의가 아님)"}`}
                </title>
              </path>
            );
          })}

          {used.flat().map((node) => {
            const p = placed.get(node.id)!;
            const isEvent = node.type === "EVENT";
            return (
              <g key={node.id}>
                <rect
                  x={p.x}
                  y={p.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={2}
                  fill={isEvent ? "var(--accent-wash)" : "var(--surface-2)"}
                  stroke={isEvent ? "var(--accent)" : "var(--rule)"}
                  strokeWidth={1}
                />
                <text
                  x={p.x + NODE_W / 2}
                  y={p.y + NODE_H / 2 + 3.4}
                  textAnchor="middle"
                  fontSize="9.5"
                  fill="var(--ink-2)"
                >
                  {node.label.length > 15 ? node.label.slice(0, 14) + "…" : node.label}
                  <title>{node.ref_id ? `${node.label} (${node.ref_id})` : node.label}</title>
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div
        className="mono"
        style={{ fontSize: 10, color: "var(--faint)", display: "flex", gap: 14, flexWrap: "wrap" }}
      >
        <span>깊이 {map.max_depth} · 노드 {map.nodes.length} · 관계 {map.edges.length}</span>
        <span style={{ color: "var(--up)" }}>정방향</span>
        <span style={{ color: "var(--down)" }}>역방향</span>
        <span>{hasProposed ? "점선 = LLM 제안 관계" : "전부 사전 정의 관계 (실선)"}</span>
      </div>
    </div>
  );
}
