import type { AiRegime, AiDriverScore, AiGroupMomentum, AiMacroRow, AiEvidenceItem, IntelligenceSnapshot, ScenarioCheck, MarketStateHistory } from "../api/types";
import { ScenarioCheckPanel, scoreColor } from "./ScenarioCheckPanel";
import { StateHistoryStrip } from "./StateHistoryStrip";
import { strengthColor } from "./OilRegimeView";
import { AiSentimentSection } from "./AiSentimentSection";
import { DataQualityBlock, GapSection, NewsImpactSection, RadarSection, SemiConfirmationSection, StatusStrip, StockImpactSection, TransmissionSection, ValueChainSection, WhatMattersSection } from "./AiValueChainSections";

/**
 * AI 탭 — AI TRADE INTELLIGENCE.
 * 순서: AI REGIME → (AI 센티2: AI SENTIMENT · GREED & FEAR) → AI vs MARKET → WHAT IS DRIVING AI? → AI FUNDAMENTAL TRANSMISSION → AI/SEMI/INFRA/SOFTWARE LEADERSHIP → SEMICONDUCTOR FUNDAMENTAL CONFIRMATION
 *       → BREADTH → NARRATIVE × PRICE → STOCK IMPACT MAP → STOCK RADAR → NEWS → VALUE CHAIN → STOCK → EXPECTATIONS vs FUNDAMENTALS → MACRO CONFIRMATION
 *       → AI-SPECIFIC STRESS → WHAT MATTERS NOW → WHAT CHANGES THE VIEW → DETAILS / DATA QUALITY(접이식).
 * (2026-09-29 (6)) 반도체·메모리·HBM 데이터는 업사이클 판정이 아니라 Fundamental Confirmation Layer 로 들어온다.
 * 시장 온도·위험선호·변동성·신용 같은 broad-market 값은 핵심 화면에 없다 — Global Market Regime 은 맥락 한 줄, 나머지는 Diagnostics.
 * 숫자는 서버가 만들고 화면은 그리기만 한다. 확률이 아니라 증거 크기. 추천이 아니다.
 */
const STATUS: Record<string, { ko: string; color: string }> = {
  CONFIRMED: { ko: "확인됨", color: "var(--ok)" }, UNCONFIRMED: { ko: "미확인", color: "var(--warn)" }, CONTRADICTED: { ko: "반박됨", color: "var(--down)" },
};
const REGIME_COLOR: Record<string, string> = {
  confirmed_risk_on: "var(--up)", price_resilience: "var(--up)", leadership_narrowing: "var(--warn)", narrative_ahead: "var(--warn)", mixed: "var(--muted)",
  macro_dragged: "var(--info)", ai_specific_derisking: "var(--crit)", confirmed_risk_off: "var(--down)", unknown: "var(--faint)",
};
const ROLE: Record<string, { ko: string; color: string }> = {
  leader: { ko: "리더", color: "var(--up)" }, strong: { ko: "강세", color: "var(--up)" }, neutral: { ko: "중립", color: "var(--muted)" },
  lagging: { ko: "약세", color: "var(--down)" }, laggard: { ko: "후미", color: "var(--down)" }, unknown: { ko: "–", color: "var(--faint)" },
};
const MACRO: Record<string, { ko: string; mark: string; color: string }> = {
  EXPLAINS: { ko: "설명함", mark: "✓", color: "var(--ok)" }, DOES_NOT_EXPLAIN: { ko: "설명 못함", mark: "✗", color: "var(--down)" },
  NEUTRAL: { ko: "판단 없음", mark: "·", color: "var(--muted)" }, MISSING: { ko: "결측", mark: "–", color: "var(--faint)" },
};
const STRESS_COLOR: Record<string, string> = { LOW: "var(--ok)", MODERATE: "var(--warn)", HIGH: "var(--crit)", UNKNOWN: "var(--faint)" };
const TREND_KO: Record<string, string> = { widening: "넓어진다", narrowing: "좁아진다", stable: "유지", unknown: "–" };
const VERDICT_KO: Record<string, string> = { macro_driven: "MACRO-DRIVEN WEAKNESS", ai_specific: "AI-SPECIFIC WEAKNESS", mixed: "MIXED", not_weak: "NOT WEAK", unknown: "UNKNOWN" };
const sg = (v: number | null, d = 1, unit = "") => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);
const pc = (v: number | null) => (v === null ? "–" : `${v.toFixed(0)}%`);
const evText = (e: AiEvidenceItem) => e.kind === "news" ? `${e.label} ${sg(e.value, 0)}` : `${e.label} ${sg(e.value)}σ${e.window === 5 ? " (5일)" : ""}`;
const col = (v: number | null) => (v === null ? "var(--faint)" : v >= 0 ? "var(--up)" : "var(--down)");

function ScoreBar({ score, scale = 100, unit = "" }: { score: number | null; scale?: number; unit?: string }) {
  const v = score ?? 0; const w = Math.min(100, Math.abs(v) / scale * 100);
  return (
    <div className="ai-bar" aria-label={sg(score, unit ? 1 : 0, unit)}>
      <i className="ai-zero" />
      <i className="ai-fill" style={{ width: `${w / 2}%`, [v >= 0 ? "left" : "right"]: "50%", background: col(score) } as React.CSSProperties} />
      <b className="num" style={{ color: col(score) }}>{sg(score, unit ? 1 : 0, unit)}</b>
    </div>
  );
}

function DriverRow({ d, dominant }: { d: AiDriverScore; dominant: boolean }) {
  const st = STATUS[d.status] ?? STATUS.UNCONFIRMED!;
  const top = d.evidence.filter((e) => e.available).slice(0, 3);
  return (
    <div className={`ai-drv${dominant ? " on" : ""}`} data-testid="ai-driver" data-id={d.id} data-status={d.status} title={d.status_reason}>
      <div className="ai-row-head"><span className="ai-name">{d.label}<small> {d.label_ko}</small></span><span className="mono ai-st" style={{ color: st.color }}>{d.status} · {st.ko}</span></div>
      <ScoreBar score={d.score} />
      <div className="ai-ev mono">{top.map(evText).join(" · ")}{d.coverage < 1 ? <span style={{ color: "var(--faint)" }}> · 확보 {(d.coverage * 100).toFixed(0)}%</span> : null}</div>
    </div>
  );
}

function GroupRow({ g, leader }: { g: AiGroupMomentum; leader: boolean }) {
  const role = ROLE[g.role] ?? ROLE.unknown!;
  return (
    <div className={`ai-grp${leader ? " on" : ""}${g.in_basket ? "" : " ctx"}`} role="row" data-testid="ai-group" data-key={g.key} data-role={g.role} title={g.note || undefined}>
      <span className="ai-grp-name">{g.label}<small> {g.label_ko}{g.in_basket ? "" : " · 바스켓 외"}</small><span className="ai-grp-n mono">{g.available}/{g.members} · vs {g.benchmark}</span></span>
      {(["rel_1d", "rel_5d", "rel_21d"] as const).map((k, i) => (
        <span key={k} className="ai-grp-cell" data-l={["1D", "1W", "1M"][i]}><ScoreBar score={g[k]} scale={6} unit="%p" /></span>
      ))}
      <span className="num ai-grp-z" data-l="rel z 5D" style={{ color: col(g.rel_z_5d) }}>{sg(g.rel_z_5d)}σ</span>
      <span className="num ai-grp-b" data-l=">MA20" style={{ color: g.above_ma20_pct !== null && g.above_ma20_pct < 50 ? "var(--down)" : "var(--ink-2)" }}>{pc(g.above_ma20_pct)}</span>
      <span className="mono ai-grp-role" data-l="rank" style={{ color: role.color }}>{g.rank_1w ? `#${g.rank_1w} ` : ""}{role.ko}</span>
    </div>
  );
}

function MacroRowView({ r }: { r: AiMacroRow }) {
  const m = MACRO[r.status] ?? MACRO.NEUTRAL!;
  return (
    <div className={`ai-mac ${r.status}`} role="row" data-status={r.status} title={r.note}>
      <span style={{ color: m.color }} aria-hidden="true">{m.mark}</span>
      <span className="ai-mac-label">{r.label}</span>
      <span className="num" style={{ color: col(r.z) }}>{sg(r.z)}σ{r.window === 5 ? " (5일)" : ""}</span>
      <span className="mono" style={{ color: "var(--faint)" }}>{r.expected_sign > 0 ? "↑ → AI ↑" : "↑ → AI ↓"}</span>
      <span className="mono ai-mac-st" style={{ color: m.color }}>{r.status.replace(/_/g, " ")}</span>
    </div>
  );
}

/**
 * extended=false: AI 센티 — Regime → AI vs Market → Drivers → Leadership → Breadth → Narrative×Price → Macro → Stress → What Changes → Diagnostics.
 * extended=true : AI 센티2 — 그 사이에 Fundamental Transmission · Value Chain · Semiconductor Confirmation · Stock Impact · Radar · News→Stock · Expectations vs Fundamentals · What Matters Now 를 끼운다.
 */
export function AiRegimeView({ regime, snapshot, check, history, extended = false }: { regime: AiRegime; snapshot: IntelligenceSnapshot; check: ScenarioCheck; history: MarketStateHistory | null; extended?: boolean }) {
  const a = regime.ai_vs_market; const b = regime.breadth; const n = regime.narrative; const m = regime.macro; const s = regime.stress;
  const dom = regime.drivers.find((d) => d.id === regime.dominant) ?? null;
  const ordered = [...regime.drivers].sort((x, y) => (x.status === "CONFIRMED" ? 0 : 1) - (y.status === "CONFIRMED" ? 0 : 1) || Math.abs(y.score) - Math.abs(x.score));
  const groups = [...regime.leadership.groups].sort((x, y) => (x.in_basket === y.in_basket ? (x.rank_1w ?? 99) - (y.rank_1w ?? 99) : x.in_basket ? -1 : 1));
  const rc = REGIME_COLOR[regime.regime] ?? "var(--muted)";
  const quad = (key: string, title: string, sub: string) => (
    <div key={key} className={`ai-quad${n.quadrant === key ? " on" : ""}`} data-testid="ai-quadrant" data-key={key} data-on={n.quadrant === key ? "1" : "0"}>
      <b>{title}</b><small>{sub}</small>
    </div>
  );
  const bigBreadth = (label: string, v: number | null, sub?: string) => (
    <div className="ai-big" key={label}>
      <span className="ai-k mono">{label}</span>
      <b className="num" style={{ color: v === null ? "var(--faint)" : v >= 50 ? "var(--up)" : "var(--down)" }}>{pc(v)}</b>
      {sub ? <small className="mono">{sub}</small> : null}
    </div>
  );
  const rowsRet = [
    { label: "AI Basket", r1: a.basket_ret_1d, r5: a.basket_ret_5d, r21: a.basket_ret_21d, z: a.basket_z, w: a.basket_window },
    { label: "Nasdaq 100", r1: a.ndx_ret_1d, r5: a.ndx_ret_5d, r21: a.ndx_ret_21d, z: null, w: null },
    { label: "S&P 500", r1: null, r5: a.spx_ret_5d, r21: a.spx_ret_21d, z: null, w: null },
  ];
  return (
    <div className="ai" data-testid="ai-regime">
      {/* 1. AI TRADE REGIME */}
      <section className="panel span-3 ai-regime" data-testid="ai-regime-card">
        <header className="panel-head"><h2 className="panel-title">AI Trade Regime</h2><div className="panel-note mono">{new Date(regime.as_of).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "medium", timeStyle: "short" })} KST · 바스켓 {a.members_used}/{a.members_total} · 마지막 봉 {a.last_date ?? "–"}</div></header>
        <div className="panel-body">
          <div className="ai-head">
            <div className="ai-title">
              <span className="ai-k mono">AI TRADE REGIME</span>
              <span className="ai-label" style={{ color: rc }} data-testid="ai-regime-label">{regime.regime_label}</span>
              <span className="ai-sub mono" data-testid="ai-regime-subtitle">{extended && regime.regime_subtitle ? `${regime.regime_subtitle} · ${regime.regime_label_ko}` : regime.regime_label_ko}</span>
            </div>
            <div className="ai-side">
              <div className="ai-kv mono" data-testid="ai-rel-summary">
                <span className="ai-k">AI vs NASDAQ 100 (5D)</span>
                <span><b className="num" style={{ color: col(a.rel_ndx_5d) }}>{sg(a.rel_ndx_5d, 1, "%p")}</b> · 상대 z <b className="num" style={{ color: col(a.rel_ndx_z_5d) }}>{sg(a.rel_ndx_z_5d)}σ</b> · <span style={{ color: a.rel_verdict === "underperform" ? "var(--down)" : a.rel_verdict === "outperform" ? "var(--up)" : "var(--muted)" }}>{a.rel_verdict.toUpperCase()}</span></span>
              </div>
              <div className="ai-kv mono">
                <span className="ai-k">DOMINANT DRIVER</span>
                <span>{dom ? <>{dom.label} <b className="num" style={{ color: col(dom.score) }}>{sg(dom.score, 0)}</b> <span style={{ color: (STATUS[dom.status] ?? STATUS.UNCONFIRMED!).color }}>{dom.status}</span> · <span style={{ color: strengthColor(regime.signal_strength_label) }}>{regime.signal_strength_label}</span></> : "–"}</span>
              </div>
              <div className="ai-kv mono">
                <span className="ai-k">AI-SPECIFIC STRESS</span>
                <span><b style={{ color: STRESS_COLOR[s.level] }}>{s.level}</b> <span style={{ color: "var(--faint)" }}>{s.score}/{s.max_score}</span></span>
              </div>
            </div>
          </div>
          <p className="ai-headline">{regime.headline}</p>
          <p className="ai-impl"><span className="ai-k mono">IMPLICATION</span> {regime.implication}</p>
          {extended ? <StatusStrip regime={regime} /> : null}
          <p className="ai-ctx mono" data-testid="ai-context">Global market regime(맥락 입력): {regime.context.market_label} {regime.context.market_confidence.toFixed(0)}%{regime.context.thermometer !== null ? ` · 온도계 ${sg(regime.context.thermometer, 0)}` : ""} — {regime.context.note}</p>
        </div>
      </section>

      {/* 1b. AI SENTIMENT · GREED & FEAR — AI 센티2 에만. AI 테마 내부의 투자심리 + 시장 확인 강도(0~100) */}
      {extended ? <AiSentimentSection regime={regime} /> : null}

      {/* 2. AI vs MARKET */}
      <section className="panel span-2" data-testid="ai-vs-market">
        <header className="panel-head"><h2 className="panel-title">AI vs Market</h2><div className="panel-note mono">절대 수익 · Nasdaq 100 / S&P 500 대비 상대 수익(%p) · 상대 z(바스켓/벤치마크 비율 지수)</div></header>
        <div className="panel-body">
          <div className="ai-tbl" role="table" aria-label="AI 대 시장">
            <div className="ai-tr ai-th mono"><span></span><span>1D</span><span>1W</span><span>1M</span><span>z</span></div>
            {rowsRet.map((r) => (
              <div key={r.label} className="ai-tr" role="row"><span className="ai-td-l">{r.label}</span>
                {[r.r1, r.r5, r.r21].map((v, i) => <span key={i} className="num" data-l={["1D", "1W", "1M"][i]} style={{ color: col(v) }}>{sg(v, 1, "%")}</span>)}
                {r.z === null ? <span className="ai-empty"></span> : <span className="num" data-l="z" style={{ color: col(r.z) }}>{`${sg(r.z)}σ${r.w === 5 ? " (5일)" : ""}`}</span>}
              </div>
            ))}
            <div className="ai-tr ai-rel" role="row"><span className="ai-td-l">AI − Nasdaq 100</span>
              {[a.rel_ndx_1d, a.rel_ndx_5d, a.rel_ndx_21d].map((v, i) => <span key={i} className="num" data-l={["1D", "1W", "1M"][i]} style={{ color: col(v) }}>{sg(v, 1, "%p")}</span>)}
              <span className="num" data-l="z 1D / 5D" style={{ color: col(a.rel_ndx_z_5d) }}>{sg(a.rel_ndx_z_1d)}σ / {sg(a.rel_ndx_z_5d)}σ (5일)</span>
            </div>
            <div className="ai-tr ai-rel" role="row"><span className="ai-td-l">AI − S&P 500</span>
              <span className="ai-empty"></span><span className="num" data-l="1W" style={{ color: col(a.rel_spx_5d) }}>{sg(a.rel_spx_5d, 1, "%p")}</span><span className="ai-empty"></span>
              <span className="num" data-l="z 5D" style={{ color: col(a.rel_spx_z_5d) }}>{sg(a.rel_spx_z_5d)}σ (5일)</span>
            </div>
          </div>
          <p className="ai-sent">{a.sentence}</p>
        </div>
      </section>

      {/* 3. WHAT IS DRIVING AI? */}
      <section className="panel" data-testid="ai-drivers">
        <header className="panel-head"><h2 className="panel-title">What Is Driving AI?</h2><div className="panel-note mono">evidence score · −100 … +100 · 상태는 바스켓 방향과의 일치</div></header>
        <div className="panel-body ai-drivers">
          {ordered.map((d) => <DriverRow key={d.id} d={d} dominant={d.id === regime.dominant} />)}
        </div>
      </section>

      {extended ? (<>
        {/* 4. AI FUNDAMENTAL TRANSMISSION */}
        <TransmissionSection regime={regime} />
        {/* 5. AI / SEMI / INFRA / SOFTWARE LEADERSHIP */}
        <ValueChainSection regime={regime} />
        {/* 6. SEMICONDUCTOR FUNDAMENTAL CONFIRMATION */}
        <SemiConfirmationSection regime={regime} />
      </>) : null}

      {/* AI LEADERSHIP — 바스켓 6그룹 (확장 화면에서는 'AI Basket Groups') */}
      <section className="panel span-2" data-testid="ai-leadership">
        <header className="panel-head"><h2 className="panel-title">{extended ? "AI Basket Groups" : "AI Leadership"}</h2><div className="panel-note mono">그룹별 상대 모멘텀(벤치마크 대비 %p) 1D / 1W / 1M · 5일 상대 z · 20일선 상회 · 1주 순위</div></header>
        <div className="panel-body">
          <div className="ai-grps" role="table" aria-label="AI 그룹 리더십">
            <div className="ai-grp ai-th mono"><span>segment</span><span>1D</span><span>1W</span><span>1M</span><span>rel z 5D</span><span>&gt;MA20</span><span>rank</span></div>
            {groups.map((g) => <GroupRow key={g.key} g={g} leader={g.key === regime.leadership.leader_1w} />)}
          </div>
          <p className="ai-sent" data-testid="ai-rotation" data-rotation={regime.leadership.rotation}>{regime.leadership.sentence}</p>
        </div>
      </section>

      {/* 5. AI BREADTH */}
      <section className="panel" data-testid="ai-breadth">
        <header className="panel-head"><h2 className="panel-title">AI Breadth</h2><div className="panel-note mono">바스켓 {b.members}종목 · {TREND_KO[b.trend]}</div></header>
        <div className="panel-body">
          <div className="ai-bigs">
            {bigBreadth("> 5DMA", b.above_ma5_pct)}
            {bigBreadth("> 20DMA", b.above_ma20_pct, b.change_1w_pts === null ? undefined : `1주 ${sg(b.change_1w_pts, 0, "%p")} (${pc(b.above_ma20_pct_1w_ago)} →)`)}
            {bigBreadth("ADVANCING", b.advancing_pct)}
          </div>
          <div className="ai-bg">
            {Object.entries(b.by_group).map(([k, v]) => {
              const g = regime.leadership.groups.find((x) => x.key === k);
              return <div key={k} className="ai-bg-row"><span className="ai-bg-l">{g?.label_ko ?? k}</span><span className="ai-bg-bar"><i style={{ width: `${v ?? 0}%`, background: v !== null && v < 50 ? "var(--down)" : "var(--up)" }} /></span><span className="num">{pc(v)}</span></div>;
            })}
          </div>
          <p className="ai-sent" data-testid="ai-breadth-sentence" data-narrowing={b.narrowing_with_index_up ? "1" : "0"}>{b.sentence}</p>
        </div>
      </section>

      {/* 6. NARRATIVE × PRICE */}
      <section className="panel span-3" data-testid="ai-narrative">
        <header className="panel-head"><h2 className="panel-title">Narrative × Price</h2><div className="panel-note mono">AI 기사 {n.news_count}건 · 뉴스 톤 {sg(n.news_tone, 0)}{n.news_momentum !== null ? ` · 모멘텀 ${sg(n.news_momentum, 0)}` : ""} · 가격 {sg(n.price_z)}σ{n.price_window === 5 ? " (5일)" : ""}</div></header>
        <div className="panel-body ai-nar">
          <div className="ai-quads">
            {quad("confirmed", "NEWS ↑ · PRICE ↑", "Confirmed")}
            {quad("narrative_ahead", "NEWS ↑ · PRICE ↓", "Narrative Ahead / Distribution Risk")}
            {quad("price_resilience", "NEWS ↓ · PRICE ↑", "Price Resilience")}
            {quad("confirmed_risk_off", "NEWS ↓ · PRICE ↓", "Confirmed Risk-Off")}
          </div>
          <div className="ai-nar-side">
            <div className="ai-nar-label mono" style={{ color: n.quadrant === "confirmed" || n.quadrant === "price_resilience" ? "var(--up)" : n.quadrant === "unclear" ? "var(--muted)" : "var(--down)" }} data-testid="ai-quadrant-label">{n.label}</div>
            <p className="ai-sent">{n.sentence}</p>
            <div className="ai-nd">
              {n.drivers.map((d) => (
                <div key={d.key} className={`ai-nd-row${d.count === 0 ? " none" : ""}`} data-testid="ai-narrative-driver" title={d.samples.join(" / ")}>
                  <span className="ai-nd-l">{d.label}<small> {d.label_ko}</small></span>
                  <span className="ai-nd-bar">{d.tone === null ? <span className="mono" style={{ color: "var(--faint)" }}>기사 없음</span> : <ScoreBar score={d.tone} scale={60} />}</span>
                  <span className="num mono ai-nd-n">{d.count}건</span>
                </div>
              ))}
            </div>
            <div className="ai-ev mono" style={{ marginTop: 6 }}>{n.method}</div>
          </div>
        </div>
      </section>

      {extended ? (<>
        {/* 9. STOCK IMPACT MAP · 10. STOCK RADAR · 11. NEWS → VALUE CHAIN → STOCK · 12. EXPECTATIONS vs FUNDAMENTALS */}
        <StockImpactSection regime={regime} />
        <RadarSection regime={regime} />
        <NewsImpactSection regime={regime} />
        <GapSection regime={regime} />
      </>) : null}

      {/* 13. MACRO CONFIRMATION */}
      <section className="panel span-2" data-testid="ai-macro">
        <header className="panel-head"><h2 className="panel-title">Macro Confirmation</h2><div className="panel-note mono">설명 {m.explains}/{m.evaluated} · <span style={{ color: m.verdict === "ai_specific" ? "var(--crit)" : m.verdict === "macro_driven" ? "var(--info)" : "var(--muted)" }}>{VERDICT_KO[m.verdict]}</span></div></header>
        <div className="panel-body">
          <div className="ai-macs" role="table" aria-label="매크로 확인">{m.rows.map((r) => <MacroRowView key={r.key} r={r} />)}</div>
          <p className="ai-sent" data-testid="ai-macro-verdict" data-verdict={m.verdict}>{m.sentence}</p>
        </div>
      </section>

      {/* 8. AI-SPECIFIC STRESS */}
      <section className="panel" data-testid="ai-stress">
        <header className="panel-head"><h2 className="panel-title">AI-specific Stress</h2><div className="panel-note mono">{s.score}/{s.max_score}</div></header>
        <div className="panel-body">
          <div className="ai-stress-head"><b className="ai-stress-level mono" style={{ color: STRESS_COLOR[s.level] }} data-testid="ai-stress-level">{s.level}</b><span className="ai-stress-bar"><i style={{ width: `${s.max_score ? s.score / s.max_score * 100 : 0}%`, background: STRESS_COLOR[s.level] }} /></span></div>
          <div className="ai-sc">
            {s.components.map((c) => (
              <div key={c.key} className="ai-sc-row" title={c.note}><span className="ai-sc-l">{c.label}</span><span className="num">{c.display}</span><span className="mono ai-sc-p" style={{ color: c.points >= 2 ? "var(--crit)" : c.points === 1 ? "var(--warn)" : "var(--muted)" }}>{c.value === null ? "–" : `${c.points}/${c.max_points}`}</span></div>
            ))}
          </div>
          <p className="ai-sent">{s.sentence}</p>
        </div>
      </section>

      {/* 15. WHAT MATTERS NOW (확장 화면) */}
      {extended ? <WhatMattersSection regime={regime} /> : null}

      {/* 16. WHAT CHANGES THE VIEW */}
      <section className="panel span-3 ai-watch" data-testid="ai-what-changes">
        <header className="panel-head"><h2 className="panel-title">What Changes The View?</h2><div className="panel-note mono">AI-specific Risk-Off 로 판단을 바꿀 조건 · 그리고 해제 조건</div></header>
        <div className="panel-body ai-watch-cols">
          <ol className="ai-watch-list">
            {regime.triggers.map((t, i) => (
              <li key={i} data-testid="ai-trigger" data-met={t.met} className={t.met ? "met" : ""}>
                <span className="ai-watch-text">{t.text}</span>
                <span className="ai-watch-meta mono">{t.measurable ? <>{t.metric} 지금 <b className="num">{t.current}</b> · 조건 {t.condition} · {t.met ? <span style={{ color: "var(--crit)" }}>충족</span> : <span style={{ color: "var(--muted)" }}>미충족</span>}</> : <span style={{ color: "var(--faint)" }}>{t.metric} 결측 — 지금은 못 잰다</span>}</span>
              </li>
            ))}
          </ol>
          <ul className="ai-release-list">
            {regime.release.map((t, i) => (
              <li key={i} data-testid="ai-release"><span className="ai-watch-text">{t.text}</span><span className="ai-watch-meta mono">{t.metric} 지금 <b className="num">{t.current}</b> · 조건 {t.condition}</span></li>
            ))}
          </ul>
        </div>
      </section>

      {/* 10. Diagnostics */}
      <details className="panel span-3 ai-diag" data-testid="ai-diagnostics">
        <summary className="panel-head"><h2 className="panel-title">{extended ? "Details / Data Quality" : "Diagnostics"}</h2><div className="panel-note mono">{extended ? "데이터 품질 · " : ""}판정 규칙 검사 · Global market regime(시장 온도·공포/탐욕 띠) · 구성원 표 · 시나리오 서명 대조 · driver 증거 전체 — 접어 둔 내부 진단</div></summary>
        <div className="panel-body">
          {extended ? <DataQualityBlock regime={regime} /> : null}
          <div className="ai-diag-grid" style={{ marginTop: extended ? 10 : 0 }}>
            <div>
              <div className="ai-k mono">판정 규칙 — 위에서부터 먼저 걸리는 것</div>
              {regime.checks.map((c) => (
                <div key={c.key} className="ai-chk mono" data-testid="ai-check" data-passed={c.passed}><span style={{ color: c.passed ? "var(--ok)" : "var(--faint)" }}>{c.passed ? "✓" : "·"}</span> <b>{c.label}</b> <span style={{ color: "var(--muted)" }}>{c.detail}</span></div>
              ))}
              <div className="ai-k mono" style={{ marginTop: 10 }}>Global market regime — 맥락 (시장 온도 {sg(regime.context.thermometer, 0)} · {regime.context.band ?? "–"})</div>
              <StateHistoryStrip history={history} primary="band" />
              <div className="ai-k mono" style={{ marginTop: 10 }}>결측</div>
              <div className="ai-ev mono">{regime.missing.length ? regime.missing.join(" · ") : "없음"}</div>
            </div>
            <div>
              <div className="ai-k mono">driver 증거 전체</div>
              {regime.drivers.map((d) => (
                <div key={d.id} className="ai-ev mono" style={{ marginBottom: 4 }}><b>{d.label}</b> {sg(d.score, 0)} · {d.evidence.map((e) => e.available ? `${evText(e)} → ${sg(e.contribution, 2)}` : `${e.label} 결측`).join(" · ")}</div>
              ))}
              <div className="ai-k mono" style={{ marginTop: 10 }}>바스켓 구성원 ({regime.members.length})</div>
              <div className="ai-mem" role="table">
                <div className="ai-mem-row ai-th mono"><span>종목</span><span>그룹</span><span>1D</span><span>1W</span><span>1M</span><span>MA5</span><span>MA20</span></div>
                {regime.members.map((mm) => (
                  <div key={mm.id} className={`ai-mem-row${mm.available ? "" : " missing"}`} role="row" data-testid="ai-member">
                    <span>{mm.name}</span><span className="mono" style={{ color: "var(--faint)" }}>{mm.group}</span>
                    {[mm.ret_1d, mm.ret_5d, mm.ret_21d].map((v, i) => <span key={i} className="num" style={{ color: col(v) }}>{sg(v, 1, "%")}</span>)}
                    <span style={{ color: mm.above_ma5 === null ? "var(--faint)" : mm.above_ma5 ? "var(--up)" : "var(--down)" }}>{mm.above_ma5 === null ? "–" : mm.above_ma5 ? "↑" : "↓"}</span>
                    <span style={{ color: mm.above_ma20 === null ? "var(--faint)" : mm.above_ma20 ? "var(--up)" : "var(--down)" }}>{mm.above_ma20 === null ? "–" : mm.above_ma20 ? "↑" : "↓"}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="ai-k mono" style={{ marginTop: 12 }}>시나리오 서명 대조 · 실데이터 일치도 <span style={{ color: scoreColor(check.match_score) }}>{check.match_score.toFixed(0)}%</span> · 지금 판정 {snapshot.market_state.primary_label} {snapshot.market_state.confidence.toFixed(0)}%</div>
          <ScenarioCheckPanel check={check} />
          <div className="sh-note" style={{ marginTop: 8 }}>{regime.note}</div>
        </div>
      </details>
    </div>
  );
}
