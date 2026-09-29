import { useState } from "react";
import type { CkIssuePath, CkPathCheck, CkPathStage, CkPathStatus, CkPathStock } from "../api/types";

/**
 * WHAT MATTERS NEXT · MARKET TRANSMISSION PATH — 이슈를 누르면 열리는 accordion.
 * Trigger → First-order → Asset → Theme/Industry → Stocks(DIRECT / SECONDARY / TERTIARY) 의 예상 전파와 지금 관측(단계별 CONFIRMED · PARTIAL ·
 * UNCONFIRMED · CONTRADICTED · DATA MISSING)을 나란히 둔다. 기존 MARKET → STOCK TRANSMISSION 카드가 '지금 일어나는 전파' 라면 여기는 '더 진행되면 번지는 곳'.
 * 모바일은 위→아래 한 열이고 tier 당 tier_max 까지만, 나머지는 View all.
 */
export const PATH_COLOR: Record<CkPathStatus, string> = { CONFIRMED: "var(--ok)", PARTIAL: "var(--warn)", UNCONFIRMED: "var(--muted)", CONTRADICTED: "var(--crit)", "DATA MISSING": "var(--faint)" };
const Ps = ({ s }: { s: CkPathStatus }) => <span className="mono ck-p-st" style={{ color: PATH_COLOR[s] }}>{s}</span>;
const sg = (v: number | null | undefined, d = 1, unit = "") => (v === null || v === undefined ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);

function Stage({ st, arrowBelow }: { st: CkPathStage; arrowBelow: boolean }) {
  return (
    <div className="ck-p-stage" data-testid="ck-path-stage" data-key={st.key}>
      <div className="ck-p-stage-h"><span className="ck-k mono">{st.label}</span><Ps s={st.status} /></div>
      {st.text.length ? <div className="ck-p-stage-t">{st.text.join(" · ")}</div> : null}
      {st.checks.length ? (
        <div className="ck-p-checks">
          {st.checks.map((c: CkPathCheck, i) => (
            <div key={`${c.id}-${i}`} className="ck-p-check mono"><span className="ck-p-check-l">{c.label}</span><span className="ck-p-check-e">{c.expect > 0 ? "↑" : "↓"} 기대</span><span className="num">{c.observed_text}</span><Ps s={c.status} /></div>
          ))}
        </div>
      ) : null}
      {arrowBelow ? <div className="ck-p-arrow mono" aria-hidden="true">▼</div> : null}
    </div>
  );
}

function StockRow({ s, onStock }: { s: CkPathStock; onStock?: (id: string) => void }) {
  return (
    <div className={`ck-p-stock mono${s.in_radar ? " radar" : ""}`} data-testid="ck-path-stock" onClick={s.in_radar && onStock ? (e) => { e.stopPropagation(); onStock(s.id); } : undefined} role={s.in_radar && onStock ? "button" : undefined}>
      <span className="ck-p-stock-n">{s.name}{s.in_radar ? <em className="ck-p-radar" title="STOCK RADAR 에 있는 종목">RADAR ●</em> : null}</span>
      <span className="ck-p-stock-a">{s.arrow}</span>
      <span className="num ck-p-stock-z" title={s.note}>{s.z === null ? "–" : `${sg(s.z)}σ`}</span>
      <Ps s={s.status} />
    </div>
  );
}

export function IssuePathView({ p, status, current, onStock }: { p: CkIssuePath; status: string; current: string; onStock?: (id: string) => void }) {
  const [all, setAll] = useState(false);
  const hidden = p.tiers.reduce((n, t) => n + Math.max(0, t.stocks.length - p.tier_max), 0);
  return (
    <div className="ck-path" data-testid="ck-path" onClick={(e) => e.stopPropagation()}>
      <div className="ck-p-head mono"><span><span className="ck-k">Status</span> <b>{status}</b></span><span><span className="ck-k">Current</span> <b>{current}</b></span><span className="ck-p-src">{p.source === "ai_value_chain" ? "AI 밸류체인 재사용" : "예상 경로 · config"}</span></div>
      <div className="ck-p-ex mono"><span><span className="ck-k">Expected</span> {p.expected}</span><span><span className="ck-k">Observed</span> {p.observed}</span></div>
      <div className="ck-p-flow">
        <Stage st={p.trigger} arrowBelow />
        <Stage st={p.first_order} arrowBelow />
        <Stage st={p.assets} arrowBelow />
        <Stage st={p.themes} arrowBelow={p.tiers.length > 0} />
      </div>
      {p.tiers.length ? (
        <div className="ck-p-tiers" data-testid="ck-path-tiers">
          <div className="ck-p-stage-h"><span className="ck-k mono">Stock impact</span><span className="mono ck-p-src">관련성만으로 판정하지 않는다 — 종목 z 로 확인</span></div>
          {p.tiers.map((t) => (
            <div key={t.tier} className="ck-p-tier">
              <span className="ck-k mono">{t.tier}</span>
              {(all ? t.stocks : t.stocks.slice(0, p.tier_max)).map((s) => <StockRow key={s.id} s={s} onStock={onStock} />)}
            </div>
          ))}
          {hidden > 0 && !all ? <button type="button" className="ck-more" onClick={() => setAll(true)}>View all impacted stocks (+{hidden})</button> : null}
        </div>
      ) : null}
      <div className="ck-p-concl" data-testid="ck-path-conclusion">{p.conclusion}</div>
      {p.confirm.length ? (
        <div className="ck-p-confirm" data-testid="ck-path-confirm">
          <div className="ck-p-stage-h"><span className="ck-k mono">What would confirm?</span><span className="mono num">{p.confirm_count} / {p.confirm.length}</span></div>
          {p.confirm.map((c, i) => <div key={i} className="ck-p-cf mono"><span>{c.status === "CONFIRMED" ? "☑" : "☐"}</span><span>{c.label}</span><span className="num">{c.observed_text}</span><Ps s={c.status} /></div>)}
        </div>
      ) : null}
    </div>
  );
}
