import { useState } from "react";
import type { AiRegime, AiChainRow } from "../api/types";
import { SemiConfirmationSection, TransmissionSection, ValueChainSection } from "./AiValueChainSections";

/**
 * AI 센티2 — AI CHAIN VIEW. 읽는 순서: SNAPSHOT → FUNDAMENTAL × PRICE ALIGNMENT → FUNDAMENTAL TRANSMISSION(한 줄씩) → VALUE-CHAIN LEADERSHIP(상·하위 3)
 * → SEMICONDUCTOR CONFIRMATION(상태 행). 상세(1D/1W/1M/EPS 표, 화살표 matrix, HBM 계약가 세부)는 전부 펼쳐야 보인다. 계산은 서버 그대로.
 */
const ST_COLOR: Record<string, string> = {
  ACCELERATING: "var(--up)", STRONG: "var(--up)", LEADING: "var(--up)", POSITIVE: "var(--up)", IMPROVING: "var(--up)", CONFIRMED: "var(--up)",
  STABLE: "var(--muted)", NEUTRAL: "var(--muted)", MIXED: "var(--warn)", PARTIAL: "var(--warn)", DIVERGENCE: "var(--warn)", "FUNDAMENTAL-LED": "var(--accent)", "PRICE-LED": "var(--info)",
  UNCONFIRMED: "var(--faint)", "N/A": "var(--faint)", DETERIORATING: "var(--down)", WEAK: "var(--down)", LAGGING: "var(--down)",
};
const sg = (v: number | null, d = 1, unit = "") => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);
const St = ({ s, title }: { s: string; title?: string }) => <b className="mono ch-st" style={{ color: ST_COLOR[s] ?? "var(--muted)" }} title={title}>{s}</b>;

function AlignRow({ r }: { r: AiChainRow }) {
  return (
    <div className="ch-al-row" role="row" data-testid="ai-chain-row" data-key={r.key} data-view={r.view} title={`${r.segment_label} · 1주 상대 ${sg(r.rel_5d, 1, "%p")} · breadth ${r.breadth === null ? "–" : `${r.breadth.toFixed(0)}%`}`}>
      <span className="ch-al-l">{r.label}</span>
      <span className="ch-al-f"><St s={r.fund_status} /><small className="num mono">{r.fund_score === null ? "" : sg(r.fund_score, 0)}</small></span>
      <span className="ch-al-p"><St s={r.price_status} /><small className="mono">{r.rank ? `#${r.rank}` : "–"}</small></span>
      <span className="ch-al-v"><St s={r.view} title={r.view_ko} /><small>{r.view_ko}</small></span>
    </div>
  );
}

export function AiChainSections({ regime }: { regime: AiRegime }) {
  const c = regime.chain_view; const snap = c.snapshot;
  const [allRows, setAllRows] = useState(false); const [allSeg, setAllSeg] = useState(false); const [matrix, setMatrix] = useState(false); const [hbm, setHbm] = useState(false); const [fullChain, setFullChain] = useState(false);
  const rows = allRows ? c.rows : c.rows.slice(0, c.main_rows);
  const Lead = ({ r, i }: { r: AiChainRow; i: number }) => (
    <div className="ch-ld-row" data-testid="ai-chain-leader" data-key={r.key}>
      <span className="mono ch-ld-n">{i + 1}</span>
      <span className="ch-ld-l">{r.segment_label}</span>
      <St s={r.price_status} />
      <span className="ch-ld-m mono">
        <span className="num" style={{ color: r.rel_5d === null ? "var(--faint)" : r.rel_5d >= 0 ? "var(--up)" : "var(--down)" }}>{sg(r.rel_5d, 1, "%p")} <small>vs NDX</small></span>
        <span className="num" style={{ color: r.breadth !== null && r.breadth < 50 ? "var(--down)" : "var(--ink-2)" }}>Breadth {r.breadth === null ? "–" : `${r.breadth.toFixed(0)}%`}</span>
      </span>
    </div>
  );
  return (
    <>
      {/* 1. AI CHAIN SNAPSHOT + FUNDAMENTAL × PRICE ALIGNMENT */}
      <section className="panel span-3 ch" data-testid="ai-chain-snapshot">
        <header className="panel-head"><h2 className="panel-title">AI Chain Snapshot</h2><div className="panel-note mono">Fundamental → Price → Confirmation 을 한 화면에서</div></header>
        <div className="panel-body">
          <div className="ch-snap" data-testid="ai-chain-snap-tiles">
            <div><span className="ai-k mono">Fundamentals</span><b>{snap.fundamentals}</b><small>{snap.fundamentals_ko}</small></div>
            <div><span className="ai-k mono">Price leadership</span><b>{snap.price_leadership}</b><small>1주 상대 순위 상위</small></div>
            <div><span className="ai-k mono">Semi confirmation</span><b>{snap.semi_confirmation}</b><small>반도체 hard data 확인 영역</small></div>
            <div><span className="ai-k mono">Key gap</span><b>{snap.key_gap}</b><small>펀더멘털 대비 가격 확인 부족</small></div>
          </div>
          <p className="ch-snap-read" data-testid="ai-chain-snap-read">{snap.read}</p>
          <div className="ch-al" role="table" aria-label="FUNDAMENTAL × PRICE ALIGNMENT" data-testid="ai-chain-alignment">
            <div className="ch-al-h"><span className="ai-k mono">Fundamental × Price</span><span className="ch-sub">{c.subtitles.alignment}</span></div>
            <div className="ch-al-row ch-th mono" aria-hidden="true"><span>AI value chain</span><span>Fund.</span><span>Price</span><span>View</span></div>
            {rows.map((r) => <AlignRow key={r.key} r={r} />)}
            {c.rows.length > c.main_rows ? <button type="button" className="ck-more" data-testid="ai-chain-view-all" onClick={() => setAllRows((v) => !v)}>{allRows ? "접기" : `View all ${c.rows.length}`}</button> : null}
            <div className="ch-legend mono" data-testid="ai-chain-view-legend">{Object.entries(c.views).map(([k, v]) => <span key={k}><b style={{ color: ST_COLOR[k] }}>{k}</b> {v}</span>)}</div>
          </div>
        </div>
      </section>

      {/* 2. AI FUNDAMENTAL TRANSMISSION — 한 줄씩 */}
      <section className="panel ch" data-testid="ai-transmission">
        <header className="panel-head"><h2 className="panel-title">AI Fundamental Transmission</h2><div className="panel-note mono" title={c.score_tip}>{c.subtitles.transmission} <span className="ch-info" title={c.score_tip}>ⓘ</span></div></header>
        <div className="panel-body">
          <div className="ch-tr">
            {c.stages.map((s) => (
              <div key={s.key} className="ch-tr-row" data-testid="ai-chain-stage" data-status={s.status} title={s.evidence}>
                <span className="ch-tr-l">{s.label}<span className="ch-basis mono" data-testid="ai-chain-basis" title="점수에 실제로 들어간 근거 — NEWS 기사 톤 · PRICE 세그먼트 상대강도 · DATA 메모리 데이터·EPS">{s.basis.length ? s.basis.map((b) => <i key={b} data-b={b}>{b}</i>) : <i data-b="NONE">NO DATA</i>}</span></span>
                <span className="num mono" style={{ color: s.score === null ? "var(--faint)" : s.score >= 0 ? "var(--up)" : "var(--down)" }}>{s.score === null ? "—" : sg(s.score, 0)}</span>
                <St s={s.status} />
              </div>
            ))}
          </div>
          <div className="ch-basis-legend mono" data-testid="ai-chain-basis-legend"><i data-b="NEWS">NEWS</i> 기사 톤 · <i data-b="PRICE">PRICE</i> 세그먼트 주가 상대강도 · <i data-b="DATA">DATA</i> 메모리 데이터 · EPS — 결측 입력은 태그에서 빠진다</div>
          <div className="ch-read" data-testid="ai-chain-fund-read"><span className="ai-k mono">Fundamental read</span><p>{c.fundamental_read}</p></div>
          <button type="button" className="ck-more" onClick={() => setFullChain((v) => !v)} data-testid="ai-chain-full">{fullChain ? "접기" : "View evidence"}</button>
          {fullChain ? <div className="ch-detail"><TransmissionSection regime={regime} /></div> : null}
        </div>
      </section>

      {/* 3. AI VALUE-CHAIN LEADERSHIP — 상·하위 3 */}
      <section className="panel ch" data-testid="ai-value-chain">
        <header className="panel-head"><h2 className="panel-title">AI Value-Chain Leadership</h2><div className="panel-note mono">{c.subtitles.leadership}</div></header>
        <div className="panel-body">
          <div className="ch-ld-cols">
            <div><span className="ai-k mono">Leaders</span>{c.leaders.map((r, i) => <Lead key={r.key} r={r} i={i} />)}</div>
            <div><span className="ai-k mono">Laggards</span>{c.laggards.map((r, i) => <Lead key={r.key} r={r} i={i} />)}</div>
          </div>
          <div className="ch-read" data-testid="ai-chain-lead-read"><span className="ai-k mono">Leadership read</span><p>{c.leadership_read}</p></div>
          <button type="button" className="ck-more" onClick={() => setAllSeg((v) => !v)} data-testid="ai-chain-view-segments">{allSeg ? "접기" : `View all ${regime.value_chain.segments.length} · 1D / 1W / 1M / EPS`}</button>
          {allSeg ? <div className="ch-detail"><ValueChainSection regime={regime} /></div> : null}
        </div>
      </section>

      {/* 4. SEMICONDUCTOR CONFIRMATION — 상태 행 */}
      <section className="panel ch" data-testid="ai-semi-confirmation">
        <header className="panel-head"><h2 className="panel-title">Semiconductor Confirmation</h2><div className="panel-note mono">{c.subtitles.semi}</div></header>
        <div className="panel-body">
          <div className="ch-sm">
            {c.semi_areas.map((a) => (
              <div key={a.key} className="ch-sm-row" data-testid="ai-chain-semi" data-status={a.status} title={Object.entries(a.arrows).map(([k, v]) => `${c.semi_columns.find((x) => x.key === k)?.label ?? k} ${v}`).join(" · ")}>
                <span className="ch-sm-l">{a.label}</span>
                <St s={a.status} />
                <span className="ch-sm-m">{a.meaning}</span>
                {a.key_evidence.length ? <span className="ch-sm-ev mono" data-testid="ai-chain-hbm-ev">Key evidence: {a.key_evidence.join(" · ")} <button type="button" className="ch-link" onClick={() => setHbm((v) => !v)}>{hbm ? "접기" : "View HBM details"}</button></span> : null}
              </div>
            ))}
          </div>
          <button type="button" className="ck-more" onClick={() => setMatrix((v) => !v)} data-testid="ai-chain-view-matrix">{matrix ? "접기" : `View evidence matrix · ${c.semi_columns.map((x) => x.label).join(" / ")}`}</button>
          {matrix || hbm ? <div className="ch-detail"><SemiConfirmationSection regime={regime} /></div> : null}
        </div>
      </section>
    </>
  );
}
