import { useEffect, useState } from "react";
import type { AiRegime, AiSentiment, AiSentimentComponent, AiSentimentFactor, AiSentimentHistory } from "../api/types";

/**
 * AI SENTIMENT · GREED & FEAR (AI 센티2 전용) — AI 투자 테마 내부의 투자심리 + 실제 시장 확인 강도(0~100).
 * 일반 시장 Fear & Greed 가 아니고, 상승·매수 확률·수익률 전망도 아니다. 숫자는 서버(config/ai_regime.yaml `sentiment`)가 만들고
 * 화면은 반원 게이지 + 구성요소 분해 + SENTIMENT READ + SENTIMENT STRUCTURE + 1M 스파크라인만 그린다.
 * 색은 심리 상태를 구분할 뿐 좋고 나쁨이 아니다 — 방향색(적/청)을 쓰지 않는다.
 */

const BAND_COLOR: Record<string, string> = { EXTREME_FEAR: "var(--gf-xf)", FEAR: "var(--gf-f)", NEUTRAL: "var(--gf-n)", GREED: "var(--gf-g)", EXTREME_GREED: "var(--gf-xg)", UNKNOWN: "var(--faint)" };
const BAND_SHORT: Record<string, string> = { EXTREME_FEAR: "EXTREME FEAR", FEAR: "FEAR", NEUTRAL: "NEUTRAL", GREED: "GREED", EXTREME_GREED: "EXTREME GREED" };
const sg = (v: number | null, d = 0) => (v === null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(d)}`);
const clamp = (s: number) => Math.max(0, Math.min(100, s));

/* ── 반원 게이지 기하 — viewBox 안에서만 계산한다. 고정 픽셀·absolute 배치 없음 ── */
const VW = 400, VH = 236, CX = 200, CY = 196, R_OUT = 168, R_IN = 134, R_TICK = 184;
/** 점수 0~100 → 수학 각도(도). 0 = 왼쪽(180°), 50 = 위(90°), 100 = 오른쪽(0°) */
const ang = (s: number) => 180 - (clamp(s) / 100) * 180;
const pt = (r: number, s: number) => { const a = (ang(s) * Math.PI) / 180; return [CX + r * Math.cos(a), CY - r * Math.sin(a)] as const; };
function bandPath(s0: number, s1: number): string {
  const [ox0, oy0] = pt(R_OUT, s0); const [ox1, oy1] = pt(R_OUT, s1); const [ix1, iy1] = pt(R_IN, s1); const [ix0, iy0] = pt(R_IN, s0);
  return `M ${ox0.toFixed(2)} ${oy0.toFixed(2)} A ${R_OUT} ${R_OUT} 0 0 1 ${ox1.toFixed(2)} ${oy1.toFixed(2)} L ${ix1.toFixed(2)} ${iy1.toFixed(2)} A ${R_IN} ${R_IN} 0 0 0 ${ix0.toFixed(2)} ${iy0.toFixed(2)} Z`;
}

function Gauge({ s }: { s: AiSentiment }) {
  const bands = [...s.bands].sort((a, b) => a.min - b.min);
  const edges = bands.map((b, i) => [b.min, i + 1 < bands.length ? bands[i + 1]!.min : 100] as const);
  const score = s.index === null ? null : clamp(s.index);
  // needle: 페이지 load 때 0(왼쪽)에서 현재값으로 한 번만 움직인다 — 흔들리거나 pulse 하지 않는다
  const [deg, setDeg] = useState(-90);
  useEffect(() => { const id = requestAnimationFrame(() => setDeg(score === null ? -90 : -90 + (score / 100) * 180)); return () => cancelAnimationFrame(id); }, [score]);
  const color = BAND_COLOR[s.state] ?? "var(--faint)";
  const h = s.history;
  const basisNote = h.basis.length && h.basis.length < s.components.length ? ` (${h.basis.map((k) => s.components.find((c) => c.key === k)?.label ?? k).join(" · ")} 기준)` : "";
  return (
    <div className="gf-gauge" data-testid="ai-gf-gauge" data-state={s.state}>
      <svg viewBox={`0 0 ${VW} ${VH}`} role="img" aria-label={`AI SENTIMENT INDEX ${s.index === null ? "측정 불가" : `${s.index.toFixed(0)} ${s.state_label}`}`}>
        {/* 밴드 5개 — 왼쪽 EXTREME FEAR → 오른쪽 EXTREME GREED */}
        {bands.map((b, i) => (
          <path key={b.key} d={bandPath(edges[i]![0], edges[i]![1])} fill={BAND_COLOR[b.key] ?? "var(--gf-n)"} opacity={s.state === b.key ? 1 : 0.55} data-testid="ai-gf-band" data-key={b.key}>
            <title>{b.label} · {edges[i]![0]}–{edges[i]![1]}</title>
          </path>
        ))}
        {/* 눈금 0 · 20 · 40 · 60 · 80 · 100 — 최소만 */}
        {[0, 20, 40, 60, 80, 100].map((v) => { const [x, y] = pt(R_TICK, v); return <text key={v} x={x} y={y + 3} textAnchor="middle" className="gf-tick">{v}</text>; })}
        {/* 큰 라벨 FEAR / NEUTRAL / GREED (양끝 EXTREME 은 눈금 tooltip 과 legend 로) */}
        {[[30, "FEAR"], [50, "NEUTRAL"], [70, "GREED"]].map(([v, l]) => { const [x, y] = pt((R_OUT + R_IN) / 2, Number(v)); return <text key={String(l)} x={x} y={y + 3} textAnchor="middle" className="gf-band-l">{l}</text>; })}
        {/* 바늘 — 띠를 가로지르는 얇은 포인터 + 바깥쪽 작은 삼각형. 각도 = −90° + s/100 × 180°. 중앙 글자를 가리지 않도록 축까지 긋지 않는다 */}
        {score !== null ? (
          <g className="gf-needle" style={{ transform: `rotate(${deg}deg)`, transformOrigin: `${CX}px ${CY}px` }} data-testid="ai-gf-needle" data-deg={(-90 + (score / 100) * 180).toFixed(1)}>
            <line x1={CX} y1={CY - R_IN + 14} x2={CX} y2={CY - R_OUT - 2} />
            <polygon points={`${CX - 5},${CY - R_OUT - 12} ${CX + 5},${CY - R_OUT - 12} ${CX},${CY - R_OUT - 1}`} />
          </g>
        ) : null}
        {/* 중앙 정보 — 점수 · 상태 · 한글 · 1D/1W 까지만 */}
        <text x={CX} y={CY - 58} textAnchor="middle" className="gf-score" style={{ fill: color }} data-testid="ai-gf-index">{s.index === null ? "–" : s.index.toFixed(0)}</text>
        <text x={CX} y={CY - 34} textAnchor="middle" className="gf-state" style={{ fill: color }} data-testid="ai-gf-state">{s.state_label}</text>
        <text x={CX} y={CY - 18} textAnchor="middle" className="gf-state-ko">{s.state_ko}</text>
        <text x={CX} y={CY + 26} textAnchor="middle" className="gf-chg" data-testid="ai-gf-change">
          <tspan>1D {sg(h.change_1d)}</tspan><tspan dx="10">1W {sg(h.change_1w)}</tspan>{basisNote ? <tspan dx="4" className="gf-chg-note">†</tspan> : null}
        </text>
      </svg>
      {/* 보조 상태 — 숫자 하나의 성격 */}
      {s.secondary_key !== "none" ? (
        <div className="gf-secondary" data-testid="ai-gf-secondary"><b className="mono">{s.secondary_label}</b><span>{s.secondary_ko}</span></div>
      ) : <div className="gf-secondary muted" data-testid="ai-gf-secondary"><b className="mono">{s.secondary_label}</b><span>{s.secondary_ko}</span></div>}
      {basisNote ? <div className="gf-basis mono" data-testid="ai-gf-basis">† 1D / 1W{basisNote}</div> : null}
    </div>
  );
}

function ComponentRow({ c }: { c: AiSentimentComponent }) {
  const color = BAND_COLOR[c.state] ?? "var(--faint)";
  const missing = c.inputs.filter((i) => !i.available);
  return (
    <div className="gf-comp" data-testid="ai-gf-component" data-key={c.key} data-state={c.state} title={c.inputs.map((i) => `${i.label} ${i.available ? `${i.display} → ${i.score!.toFixed(0)}` : `– (${i.note})`}`).join("\n")}>
      <div className="gf-comp-h">
        <span className="gf-comp-l"><b className="mono">{c.label}</b><small>{c.label_ko}</small></span>
        <span className="gf-comp-s num" style={{ color }}>{c.score === null ? "–" : c.score.toFixed(0)}</span>
      </div>
      <div className="gf-track" aria-hidden="true">
        {c.score !== null ? <i className="gf-mark" style={{ left: `${clamp(c.score)}%`, background: color }} /> : null}
      </div>
      <div className="gf-comp-b">
        <b className="mono" style={{ color }}>{c.score === null ? "DATA MISSING" : BAND_SHORT[c.state] ?? c.state_label}</b>
        <span>{c.read}</span>
        {missing.length && c.score !== null ? <small className="mono">· {c.inputs.length - missing.length}/{c.inputs.length} 입력</small> : null}
      </div>
    </div>
  );
}

function Factors({ title, items, empty, testid }: { title: string; items: AiSentimentFactor[]; empty: string; testid: string }) {
  return (
    <div className="gf-fac" data-testid={testid}>
      <span className="ai-k mono">{title}</span>
      {items.length ? <ul>{items.map((f) => <li key={f.id}><span>{f.label}</span><small className="mono">{f.display || f.score.toFixed(0)}</small></li>)}</ul> : <span className="gf-fac-empty">{empty}</span>}
    </div>
  );
}

function Spark({ h }: { h: AiSentimentHistory }) {
  const pts = h.points.filter((p) => p.index !== null);
  if (pts.length < 2) return <span className="gf-fac-empty">{h.note || "1M 이력 없음"}</span>;
  const W = 160, H = 34;
  const xs = h.points.map((_, i) => (i / Math.max(1, h.points.length - 1)) * W);
  const path = h.points.map((p, i) => (p.index === null ? null : `${xs[i]!.toFixed(1)},${(H - 2 - (clamp(p.index) / 100) * (H - 4)).toFixed(1)}`)).filter(Boolean);
  const first = pts[0]!.index!; const last = pts[pts.length - 1]!.index!;
  const sample = pts.length > 6 ? [pts[0], pts[Math.floor(pts.length / 5)], pts[Math.floor((2 * pts.length) / 5)], pts[Math.floor((3 * pts.length) / 5)], pts[Math.floor((4 * pts.length) / 5)], pts[pts.length - 1]] : pts;
  return (
    <div className="gf-spark" data-testid="ai-gf-spark" title={h.note}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <line x1={0} y1={H / 2} x2={W} y2={H / 2} className="gf-spark-mid" />
        <polyline points={path.join(" ")} className="gf-spark-line" />
      </svg>
      <div className="gf-spark-v mono">{sample.map((p) => p!.index!.toFixed(0)).join(" → ")}</div>
      <div className="gf-spark-r mono">Range {h.range_min?.toFixed(0)}–{h.range_max?.toFixed(0)} · {first.toFixed(0)} → {last.toFixed(0)}</div>
    </div>
  );
}

export function AiSentimentSection({ regime }: { regime: AiRegime }) {
  const s = regime.sentiment;
  if (!s) return null;
  return (
    <section className="panel span-3 gf" data-testid="ai-sentiment">
      <header className="panel-head"><h2 className="panel-title">AI Sentiment · Greed &amp; Fear</h2><div className="panel-note mono">AI 테마 내부의 투자심리 + 시장 확인 강도 · 0~100 · Narrative + Price + Breadth + Fundamentals + Macro · 확률·전망 아님</div></header>
      <div className="panel-body">
        <div className="gf-top">
          <Gauge s={s} />
          <div className="gf-comps" data-testid="ai-gf-components">
            <span className="ai-k mono">Why {s.index === null ? "–" : s.index.toFixed(0)}? · component decomposition</span>
            {s.components.map((c) => <ComponentRow key={c.key} c={c} />)}
          </div>
        </div>
        <div className="gf-bottom">
          <div className="gf-read" data-testid="ai-gf-read"><span className="ai-k mono">AI Sentiment Read</span><p>{s.read}</p></div>
          <div className="gf-struct" data-testid="ai-gf-structure">
            <span className="ai-k mono">Sentiment Structure</span>
            <div className="gf-struct-cols">
              <Factors title="Support" items={s.support} empty="지지 요인 없음" testid="ai-gf-support" />
              <Factors title="Pressure" items={s.pressure} empty="부담 요인 없음" testid="ai-gf-pressure" />
            </div>
          </div>
          <div className="gf-hist"><span className="ai-k mono">1M Sentiment</span><Spark h={s.history} /></div>
        </div>
        <div className="gf-legend mono" aria-label="색 범례">
          {[...s.bands].sort((a, b) => a.min - b.min).map((b) => <span key={b.key}><i style={{ background: BAND_COLOR[b.key] }} />{b.label}</span>)}
          <span className="gf-legend-note">색은 심리 상태 구분 — 투자 매력도가 아니다</span>
        </div>
      </div>
    </section>
  );
}
