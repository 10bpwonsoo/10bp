import { useState } from "react";
import type { AiRegime, AiDriverScore, AiDriverRef } from "../api/types";

/**
 * AI 센티2 — AI VS MARKET (OBSERVATION) → WHAT IS DRIVING AI? (ATTRIBUTION).
 * AI VS MARKET: 4개 핵심 판단(ABSOLUTE / RELATIVE / RELATIVE Z / MARKET READ) → compact 1D/1W/1M 표 → RELATIVE PERFORMANCE READ → 연결 문구.
 * WHAT IS DRIVING AI: EVIDENCE SCORE 범례 → DRIVER VERDICT → driver 카드(점수 · 질적 라벨 · 한 줄 의미 · 핵심 evidence · why · PRICE CHECK · 상태) → 누르면 전파 경로·전체 evidence.
 * 숫자·문장은 서버(config/ai_regime.yaml vs_market · driver_view · driver_verdict)가 만든다. 점수 계산은 바꾸지 않았다.
 */
const STATUS: Record<string, { ko: string; color: string }> = {
  CONFIRMED: { ko: "확인됨", color: "var(--ok)" }, UNCONFIRMED: { ko: "미확인", color: "var(--warn)" }, CONTRADICTED: { ko: "반박됨", color: "var(--down)" },
};
const TREND_COLOR: Record<string, string> = { RISING: "var(--up)", WEAK: "var(--down)", FLAT: "var(--muted)", OUTPERFORMING: "var(--up)", "IN LINE": "var(--muted)", UNDERPERFORMING: "var(--down)", STRONG: "var(--up)", "–": "var(--faint)" };
const sg = (v: number | null, d = 1, unit = "") => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);
const col = (v: number | null) => (v === null ? "var(--faint)" : v >= 0 ? "var(--up)" : "var(--down)");

/* ── AI VS MARKET ─────────────────────────────────────────── */
export function VsMarketSection({ regime }: { regime: AiRegime }) {
  const a = regime.ai_vs_market;
  const rows: { label: string; v: (number | null)[]; unit: string; key?: boolean }[] = [
    { label: "AI Basket", v: [a.basket_ret_1d, a.basket_ret_5d, a.basket_ret_21d], unit: "%" },
    { label: "Nasdaq 100", v: [a.ndx_ret_1d, a.ndx_ret_5d, a.ndx_ret_21d], unit: "%" },
    { label: "S&P 500", v: [null, a.spx_ret_5d, a.spx_ret_21d], unit: "%" },
    { label: "AI vs Nasdaq", v: [a.rel_ndx_1d, a.rel_ndx_5d, a.rel_ndx_21d], unit: "%p", key: true },
    { label: "AI vs S&P", v: [null, a.rel_spx_5d, null], unit: "%p" },
  ];
  const tile = (k: string, label: string, value: string, ko: string, color: string, testid: string) => (
    <div key={k} className="vm-tile" data-testid={testid}>
      <span className="ai-k mono">{label}</span>
      <b className="mono" style={{ color }}>{value}</b>
      <span className="vm-ko">{ko}</span>
    </div>
  );
  return (
    <section className="panel span-2 vm" data-testid="ai-vs-market">
      <header className="panel-head"><h2 className="panel-title">AI vs Market</h2><div className="panel-note mono">AI 가 시장과 비교해 얼마나 특이하게 움직이는가 · 절대 → 상대 → 평소 대비</div></header>
      <div className="panel-body">
        <div className="vm-top">
          <div className="vm-tiles" data-testid="ai-vm-summary">
            {tile("abs", "Absolute trend", a.absolute_trend, `${a.absolute_text} · ${a.absolute_ko}`, TREND_COLOR[a.absolute_trend] ?? "var(--ink)", "ai-vm-abs")}
            {tile("rel", "Relative trend", a.relative_trend, `${a.relative_text} · ${a.relative_ko}`, TREND_COLOR[a.relative_trend] ?? "var(--ink)", "ai-vm-rel")}
            {tile("relz", "Relative z", a.relative_z_text, a.relative_z_ko, col(a.rel_ndx_z_5d ?? a.rel_ndx_z), "ai-vm-relz")}
          </div>
          <div className="vm-tbl" role="table" aria-label="AI 대 시장 · 1D / 1W / 1M">
            <div className="vm-tr vm-th mono" aria-hidden="true"><span></span><span>1D</span><span>1W</span><span>1M</span></div>
            {rows.map((r) => (
              <div key={r.label} className={`vm-tr${r.key ? " vm-key" : ""}`} role="row" data-testid={r.key ? "ai-vm-key-row" : undefined}>
                <span className="vm-td-l">{r.label}</span>
                {r.v.map((v, i) => <span key={i} className="num" data-l={["1D", "1W", "1M"][i]} style={{ color: v === null ? "var(--faint)" : r.key ? col(v) : "var(--ink-2)" }}>{v === null ? "–" : sg(v, 1, r.unit)}</span>)}
              </div>
            ))}
            <div className="vm-z mono">상대 z {sg(a.rel_ndx_z_1d)}σ 1D / {sg(a.rel_ndx_z_5d)}σ 5D · vs S&P {sg(a.rel_spx_z_5d)}σ 5D · 바스켓 {sg(a.basket_z)}σ</div>
          </div>
        </div>
        <div className="vm-read" data-testid="ai-vm-market-read">
          <span className="ai-k mono">Market read</span>
          <b className="mono">{a.market_read_label}</b>
          <p>{a.market_read}</p>
        </div>
        <div className="vm-rel-read" data-testid="ai-vm-relative-read"><span className="ai-k mono">Relative performance read</span><p>{a.relative_read}</p></div>
        <div className="vm-link mono" data-testid="ai-vm-connector" title={a.connector_ko}><span>↓</span> {a.connector}</div>
      </div>
    </section>
  );
}

/* ── WHAT IS DRIVING AI? ──────────────────────────────────── */
function ScoreBar({ score }: { score: number }) {
  const w = Math.min(100, Math.abs(score)) / 2;
  return (
    <div className="dv-bar" aria-label={sg(score, 0)}>
      <span className="dv-bar-l mono">NEGATIVE</span>
      <div className="dv-bar-track"><i className="dv-bar-zero" /><i className="dv-bar-fill" style={{ width: `${w}%`, [score >= 0 ? "left" : "right"]: "50%", background: col(score) } as React.CSSProperties} /></div>
      <span className="dv-bar-r mono">POSITIVE</span>
    </div>
  );
}

function RefRow({ r }: { r: AiDriverRef }) {
  const st = STATUS[r.status] ?? STATUS.UNCONFIRMED!;
  return (
    <div className="dv-ref" data-testid="ai-verdict-ref" data-role={r.role} data-id={r.id}>
      <span className="ai-k mono dv-ref-role">{r.role}</span>
      <span className="dv-ref-l">{r.label}</span>
      <b className="num mono" style={{ color: col(r.score) }}>{sg(r.score, 0)}</b>
      <span className="mono dv-ref-st" style={{ color: st.color }}>{r.status}</span>
    </div>
  );
}

function DriverCard({ d, dominant }: { d: AiDriverScore; dominant: boolean }) {
  const [open, setOpen] = useState(false);
  const st = STATUS[d.status] ?? STATUS.UNCONFIRMED!;
  return (
    <div className={`dv-card${dominant ? " on" : ""}${open ? " open" : ""}`} data-testid="ai-driver" data-id={d.id} data-status={d.status} onClick={() => setOpen((o) => !o)} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") setOpen((o) => !o); }} aria-expanded={open}>
      <div className="dv-head">
        <span className="dv-name">{d.label}<small>{d.label_ko}</small></span>
        <span className="dv-score num mono" style={{ color: col(d.score) }} data-testid="ai-driver-score">{sg(d.score, 0)}</span>
        <span className="mono dv-open">{open ? "▾" : "›"}</span>
      </div>
      <div className="dv-band"><b className="mono" data-testid="ai-driver-band" style={{ color: col(d.score) }}>{d.band}</b><span>{d.band_ko}</span></div>
      <ScoreBar score={d.score} />
      <div className="dv-sec"><span className="ai-k mono">{d.id === "ai_narrative" ? "Evidence" : d.id === "ai_fundamental_stress" ? "Market condition / AI data" : "Market condition"}</span><div className="dv-ev mono">{d.top_evidence.length ? d.top_evidence.map((t) => <span key={t}>{t}</span>) : <span style={{ color: "var(--faint)" }}>증거 없음</span>}{d.coverage < 1 ? <span style={{ color: "var(--faint)" }}>확보 {(d.coverage * 100).toFixed(0)}%</span> : null}</div></div>
      {d.why ? <div className="dv-sec"><span className="ai-k mono">Why it matters</span><p className="dv-why">{d.why}</p></div> : null}
      {d.price_check.length ? <div className="dv-sec"><span className="ai-k mono">Price check</span><div className="dv-pc mono">{d.price_check.map((p) => <span key={p.label} data-testid="ai-driver-price-check"><i>{p.label}</i><b style={{ color: TREND_COLOR[p.value] ?? "var(--ink)" }}>{p.value}</b></span>)}</div></div> : null}
      <div className="dv-status" data-testid="ai-driver-status" title={d.status_meaning}><b className="mono" style={{ color: st.color }}>{d.status}</b><span>{d.status_ko || d.status_reason}</span></div>
      {d.aux_label ? <div className="dv-aux mono" data-testid="ai-driver-aux"><b>{d.aux_label}</b><span>{d.aux_ko}</span></div> : null}
      {open ? (
        <div className="dv-more" data-testid="ai-driver-more" onClick={(e) => e.stopPropagation()}>
          {d.transmission.length ? <div className="dv-sec"><span className="ai-k mono">Transmission</span><div className="dv-chain">{d.transmission.map((t, i) => <span key={i}>{i ? <em>↓</em> : null}<b>{t}</b></span>)}</div></div> : null}
          <div className="dv-sec"><span className="ai-k mono">Status meaning</span><p className="dv-why">{d.status_meaning}{d.status_reason ? ` — ${d.status_reason}` : ""}</p></div>
          <div className="dv-sec"><span className="ai-k mono">All evidence</span><div className="ai-ev mono">{d.evidence.map((e) => e.available ? `${e.label} ${e.kind === "news" ? sg(e.value, 0) : `${sg(e.value)}σ`} → ${sg(e.contribution, 2)}` : `${e.label} 결측`).join(" · ")}</div></div>
          {d.implication ? <div className="dv-sec"><span className="ai-k mono">Implication</span><p className="dv-why">{d.implication}</p></div> : null}
        </div>
      ) : null}
    </div>
  );
}

export function DriversSection({ regime }: { regime: AiRegime }) {
  const v = regime.driver_verdict;
  const ordered = [...regime.drivers].sort((x, y) => (x.status === "CONFIRMED" ? 0 : 1) - (y.status === "CONFIRMED" ? 0 : 1) || Math.abs(y.score) - Math.abs(x.score));
  const refs: AiDriverRef[] = [v.primary, v.secondary, ...v.offset, ...v.unconfirmed].filter((x): x is AiDriverRef => !!x);
  return (
    <section className="panel span-3 dv" data-testid="ai-drivers">
      <header className="panel-head"><h2 className="panel-title">What Is Driving AI?</h2><div className="panel-note mono">AI vs MARKET 의 차이를 어떤 driver 가 설명하는가 · OBSERVATION → ATTRIBUTION</div></header>
      <div className="panel-body">
        <div className="dv-legend" data-testid="ai-score-legend">
          <span className="ai-k mono">Evidence score</span>
          <div className="dv-legend-scale mono"><span><b>−100</b>{v.score_legend.neg}</span><span><b>0</b>{v.score_legend.zero}</span><span><b>+100</b>{v.score_legend.pos}</span></div>
          <p>{v.score_legend.note}</p>
        </div>
        <div className="dv-verdict" data-testid="ai-driver-verdict">
          <div className="dv-verdict-h">
            <span className="ai-k mono">Driver verdict</span>
            <span className="dv-gap mono"><b>{v.gap_label}</b> {v.gap_value}</span>
            <span className="dv-gap-q">{v.gap_question}</span>
          </div>
          <div className="dv-refs">{refs.length ? refs.map((r) => <RefRow key={r.id} r={r} />) : <span className="mono" style={{ color: "var(--faint)" }}>설명 후보 driver 없음</span>}</div>
          <p className="dv-concl" data-testid="ai-verdict-conclusion">{v.conclusion}</p>
          <div className="ai-ev mono">{v.method}</div>
        </div>
        <div className="dv-status-legend mono" data-testid="ai-status-legend">{Object.entries(v.status_meaning).map(([k, txt]) => <span key={k}><b style={{ color: (STATUS[k] ?? { color: "var(--muted)" }).color }}>{k}</b> {txt}</span>)}</div>
        <div className="dv-cards">{ordered.map((d) => <DriverCard key={d.id} d={d} dominant={d.id === regime.dominant} />)}</div>
      </div>
    </section>
  );
}
