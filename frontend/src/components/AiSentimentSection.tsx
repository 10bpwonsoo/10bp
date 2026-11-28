import { useEffect, useState } from "react";
import type { AiRegime, AiSentiment, AiSentimentComponent, AiSentimentFactor, AiSentimentHistory } from "../api/types";
import { sourceLine } from "./DailyHistoryStrip";

/**
 * AI SENTIMENT · GREED & FEAR (AI 센티2 전용) — AI 투자 테마 내부의 투자심리 + 실제 시장 확인 강도(0~100).
 * 읽는 순서: 반원 게이지(현재 심리) → 5 factor bar(왜) → KEY TENSION → SUPPORT vs PRESSURE(무엇이 지지/압박) → 1M 히스토리(최근 변화) → READ(≤2문장).
 * 숫자·문장은 서버(config/ai_regime.yaml `sentiment`)가 만들고 화면은 그리기만 한다. 색은 심리 상태 구분이지 좋고 나쁨이 아니다.
 */

const BAND_COLOR: Record<string, string> = { EXTREME_FEAR: "var(--gf-xf)", FEAR: "var(--gf-f)", NEUTRAL: "var(--gf-n)", GREED: "var(--gf-g)", EXTREME_GREED: "var(--gf-xg)", UNKNOWN: "var(--faint)" };
const BAND_SHORT: Record<string, string> = { EXTREME_FEAR: "EXTREME FEAR", FEAR: "FEAR", NEUTRAL: "NEUTRAL", GREED: "GREED", EXTREME_GREED: "EXTREME GREED" };
const FACTOR_ORDER = ["fundamentals", "narrative", "price", "breadth", "macro"];
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
  const basisNote = h.basis.length && h.basis.length < s.components.length ? `${h.basis.map((k) => s.components.find((c) => c.key === k)?.label ?? k).join(" · ")} 기준` : "";
  return (
    <div className="gf-gauge" data-testid="ai-gf-gauge" data-state={s.state}>
      <svg viewBox={`0 0 ${VW} ${VH}`} role="img" aria-label={`AI SENTIMENT INDEX ${s.index === null ? "측정 불가" : `${s.index.toFixed(0)} ${s.state_label}`}`}>
        {bands.map((b, i) => (
          <path key={b.key} d={bandPath(edges[i]![0], edges[i]![1])} fill={BAND_COLOR[b.key] ?? "var(--gf-n)"} opacity={s.state === b.key ? 1 : 0.55} data-testid="ai-gf-band" data-key={b.key}>
            <title>{b.label} · {edges[i]![0]}–{edges[i]![1]}</title>
          </path>
        ))}
        {[0, 20, 40, 60, 80, 100].map((v) => { const [x, y] = pt(R_TICK, v); return <text key={v} x={x} y={y + 3} textAnchor="middle" className="gf-tick">{v}</text>; })}
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
      {basisNote ? <div className="gf-basis mono" data-testid="ai-gf-basis" title={h.note}>† 1D / 1W 는 {basisNote}</div> : null}
    </div>
  );
}

/** 5 FACTOR DECOMPOSITION — 가로 막대 하나로 점수를 읽는다. 순서: FUNDAMENTALS · NARRATIVE · PRICE · BREADTH · MACRO */
function FactorBar({ c }: { c: AiSentimentComponent }) {
  const color = BAND_COLOR[c.state] ?? "var(--faint)";
  const missing = c.inputs.filter((i) => !i.available);
  const tip = [c.desc_ko, ...c.inputs.map((i) => `${i.label} ${i.available ? `${i.display} → ${i.score!.toFixed(0)}` : `– (${i.note})`}`)].join("\n");
  return (
    <div className="gf-fb" data-testid="ai-gf-component" data-key={c.key} data-state={c.state} title={tip}>
      <span className="gf-fb-l"><b className="mono">{c.label}</b><small>{c.desc_ko}</small></span>
      <span className="gf-fb-s num" style={{ color }}>{c.score === null ? "–" : c.score.toFixed(0)}</span>
      <span className="gf-fb-st mono" style={{ color }}>{c.score === null ? "DATA MISSING" : BAND_SHORT[c.state] ?? c.state_label}</span>
      <span className="gf-fb-bar" aria-hidden="true">{c.score !== null ? <i style={{ width: `${clamp(c.score)}%`, background: color }} /> : null}</span>
      <span className="gf-fb-r">{c.read}{missing.length && c.score !== null ? <small className="mono"> · {c.inputs.length - missing.length}/{c.inputs.length} 입력</small> : null}</span>
    </div>
  );
}

function Drivers({ s }: { s: AiSentiment }) {
  const col = (title: string, arrow: string, items: AiSentimentFactor[], empty: string, testid: string) => (
    <div className="gf-drv-col" data-testid={testid}>
      <span className="ai-k mono">{title} <em>{arrow}</em></span>
      {items.length ? <ul>{items.map((f) => <li key={f.id}><span>{f.label}</span><small className="mono">{f.display || f.score.toFixed(0)}</small></li>)}</ul> : <span className="gf-empty">{empty}</span>}
    </div>
  );
  return (
    <div className="gf-drv" data-testid="ai-gf-structure">
      <span className="ai-k mono">Sentiment Drivers</span>
      <div className="gf-drv-grid">
        {col("Support", "↑", s.support, "지지 요인 없음", "ai-gf-support")}
        {col("Pressure", "↓", s.pressure, "부담 요인 없음", "ai-gf-pressure")}
        <div className="gf-net" data-testid="ai-gf-net">
          <span className="ai-k mono">Net effect</span>
          <b className="mono" style={{ color: BAND_COLOR[s.state] ?? "var(--faint)" }}>{s.state_label}{s.index !== null ? ` · ${s.index.toFixed(0)}` : ""}</b>
          <span>{s.net_effect}</span>
        </div>
      </div>
    </div>
  );
}

/** 1M SENTIMENT — 밴드 배경(연하게) 위의 스파크라인, 현재 점을 크게. 숫자 나열은 없다 */
function History({ s }: { s: AiSentiment }) {
  const h: AiSentimentHistory = s.history;
  const pts = h.points.filter((p) => p.index !== null);
  const W = 320, H = 96, PL = 4, PR = 48, PT = 6, PB = 6;
  const x = (i: number) => PL + (i / Math.max(1, h.points.length - 1)) * (W - PL - PR);
  const y = (v: number) => PT + (1 - clamp(v) / 100) * (H - PT - PB);
  const bands = [...s.bands].sort((a, b) => a.min - b.min);
  const edges = bands.map((b, i) => [b.min, i + 1 < bands.length ? bands[i + 1]!.min : 100] as const);
  const path = h.points.map((p, i) => (p.index === null ? null : `${x(i).toFixed(1)},${y(p.index).toFixed(1)}`)).filter(Boolean).join(" ");
  const lastIdx = h.points.length - 1; const last = h.points[lastIdx];
  const color = BAND_COLOR[s.state] ?? "var(--faint)";
  return (
    <div className="gf-hist" data-testid="ai-gf-history" title={h.note}>
      <span className="ai-k mono">1M Sentiment</span>
      {pts.length >= 2 ? (
        <>
          <svg viewBox={`0 0 ${W} ${H}`} className="gf-hist-svg" data-testid="ai-gf-spark" role="img" aria-label={`1M sentiment ${h.range_min?.toFixed(0)}–${h.range_max?.toFixed(0)}`}>
            {bands.map((b, i) => <rect key={b.key} x={0} y={y(edges[i]![1])} width={W - PR + 2} height={y(edges[i]![0]) - y(edges[i]![1])} fill={BAND_COLOR[b.key]} className="gf-hist-band" data-key={b.key} />)}
            {bands.map((b, i) => <text key={`t-${b.key}`} x={W - PR + 6} y={(y(edges[i]![0]) + y(edges[i]![1])) / 2 + 3} className="gf-hist-bl">{b.label.replace("EXTREME ", "X-")}</text>)}
            <polyline points={path} className="gf-hist-line" />
            {h.points.map((p, i) => (p.index === null || i === lastIdx ? null : (
              <circle key={p.date} cx={x(i)} cy={y(p.index)} r={p.source === "BACKFILLED" ? 2.2 : 1.8} className={`gf-hist-dot${p.source === "BACKFILLED" ? " gf-hist-dot-backfilled" : ""}`} data-testid="ai-gf-point" data-source={p.source}>
                <title>{`${p.date} · ${p.index.toFixed(0)} ${p.state}\n${sourceLine(p.source, p.calculated_at, p.model_version, "", p.source !== "LIVE")}${p.missing.length ? `\n결측: ${p.missing.join(", ")} (확보 구성요소로 재정규화)` : ""}`}</title>
              </circle>
            )))}
            {last && last.index !== null ? (<>
              <circle cx={x(lastIdx)} cy={y(last.index)} r={5} fill={color} className="gf-hist-now" />
              <circle cx={x(lastIdx)} cy={y(last.index)} r={2} className="gf-hist-now-in" />
            </>) : null}
          </svg>
          <div className="gf-hist-kv mono" data-testid="ai-gf-hist-kv">
            <span><i>NOW</i><b style={{ color }}>{s.index === null ? "–" : s.index.toFixed(0)}</b><em>{s.state_label}</em></span>
            <span><i>1W</i><b>{sg(h.change_1w)}</b></span>
            <span><i>1M RANGE</i><b>{h.range_min?.toFixed(0)}–{h.range_max?.toFixed(0)}</b></span>
          </div>
          {h.read ? <div className="gf-hist-read" data-testid="ai-gf-hist-read">{h.read}</div> : null}
          {h.footnote ? <div className="gf-foot mono" data-testid="ai-gf-footnote" data-mode={h.history_mode}>{h.footnote} · Recorded {h.recorded_days} · Backfilled {h.backfilled_days}</div> : null}
          <div className="gf-scale mono" aria-hidden="true"><span>FEAR ←</span><span>0</span><span className="gf-scale-line" /><span>50</span><span className="gf-scale-line" /><span>100</span><span>→ GREED</span></div>
        </>
      ) : <span className="gf-empty">{h.note || "1M 이력 없음"}</span>}
    </div>
  );
}

export function AiSentimentSection({ regime }: { regime: AiRegime }) {
  const s = regime.sentiment;
  if (!s) return null;
  const ordered = [...s.components].sort((a, b) => FACTOR_ORDER.indexOf(a.key) - FACTOR_ORDER.indexOf(b.key));
  return (
    <section className="panel span-3 gf" data-testid="ai-sentiment">
      <header className="panel-head"><h2 className="panel-title">AI Sentiment · Greed &amp; Fear</h2><div className="panel-note mono">AI 테마 내부의 투자심리 + 시장 확인 강도 · 0~100 · 확률·전망 아님</div></header>
      <div className="panel-body">
        <div className="gf-top">
          <Gauge s={s} />
          <div className="gf-right">
            <div className="gf-fbs" data-testid="ai-gf-components">
              <span className="ai-k mono">Why {s.index === null ? "–" : s.index.toFixed(0)}? · 5 factors</span>
              {ordered.map((c) => <FactorBar key={c.key} c={c} />)}
            </div>
            <div className={`gf-tension${s.secondary_key === "none" ? " muted" : ""}`} data-testid="ai-gf-secondary">
              <span className="ai-k mono">Key tension</span>
              <b className="mono">{s.secondary_label}</b>
              <span className="gf-tension-ko">{s.secondary_ko}</span>
              {s.gap_read ? <p data-testid="ai-gf-gap">{s.gap_read}</p> : null}
            </div>
          </div>
        </div>
        <div className="gf-bottom">
          <Drivers s={s} />
          <History s={s} />
          <div className="gf-read" data-testid="ai-gf-read"><span className="ai-k mono">AI Sentiment Read</span><p>{s.read}</p></div>
        </div>
      </div>
    </section>
  );
}
