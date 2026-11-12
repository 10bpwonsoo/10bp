import type { AiRegime, Cockpit, CkLeaderRow, MarketOverview, OilRegime, RatesRegime, RsSignal } from "../api/types";
import type { SemiconductorCycle } from "../api/semiconductor";
import { KEY_COLOR, entryText, exitText, isV2, keyColor, keyText } from "./RegimeStatePanel";

/**
 * MARKET OVERVIEW · 시장 종합 (2026-11-12).
 * 새 판정 · 새 점수를 만들지 않는다 — 숫자 칸은 같은 날짜의 기존 섹션(실시간 cockpit · 금리 · 유가 · AI 센티 · 반도체 사이클)을 그대로 읽고,
 * 해석 칸은 그 섹션들을 읽은 LLM 종합(market_overview)이다. 과거 날짜는 모든 칸이 같은 저장본에서 온다(App 의 selectedDate 하나).
 * 판단(synthesis)이 먼저, 근거 숫자는 그 아래 작게. 상세는 DETAIL → 로 기존 탭.
 */
export type DetailTarget = "live" | "rates" | "oil" | "ai" | "semi";

const sg = (v: number | null | undefined, d = 1, unit = "") => (v === null || v === undefined ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);
const arrowOf = (z: number | null | undefined) => (z === null || z === undefined ? "–" : z >= 1.5 ? "↑↑" : z >= 0.5 ? "↑" : z <= -1.5 ? "↓↓" : z <= -0.5 ? "↓" : "→");
const TONE: Record<string, string> = {
  POSITIVE: "var(--ok)", IMPROVING: "var(--ok)", Bullish: "var(--ok)", Improving: "var(--ok)", Tailwind: "var(--ok)", Low: "var(--ok)", LOW: "var(--ok)",
  MIXED: "var(--warn)", NEUTRAL: "var(--muted)", Mixed: "var(--warn)", Neutral: "var(--muted)", Moderate: "var(--warn)", MODERATE: "var(--warn)", MEDIUM: "var(--warn)",
  NEGATIVE: "var(--crit)", Weak: "var(--crit)", Headwind: "var(--crit)", Elevated: "var(--crit)", ELEVATED: "var(--crit)", High: "var(--crit)", HIGH: "var(--crit)",
  STRONG: "var(--ink)", WEAK: "var(--muted)",
  CONFIRMED: "var(--ok)", STRONG_EQ: "var(--ok)", PARTIAL: "var(--warn)", CONTRADICTED: "var(--crit)", UNAVAILABLE: "var(--faint)",
};
const EQ_TONE: Record<string, string> = { STRONG: "var(--ok)", CONFIRMED: "var(--ok)", PARTIAL: "var(--warn)", MIXED: "var(--warn)", CONTRADICTED: "var(--crit)", UNAVAILABLE: "var(--faint)" };

function Sec({ n, title, ko, area, detail, onDetail, children, testid }: { n: number; title: string; ko?: string; area: string; detail?: DetailTarget; onDetail?: (t: DetailTarget) => void; children: React.ReactNode; testid: string }) {
  return (
    <section className="panel mo-sec" style={{ gridArea: area }} data-testid={testid}>
      <header className="panel-head"><h2 className="panel-title"><span className="mo-n mono">{n}</span> {title}{ko ? <em className="mo-ko"> {ko}</em> : null}</h2>
        {detail && onDetail ? <button type="button" className="mo-detail mono" onClick={() => onDetail(detail)} data-testid={`mo-detail-${detail}`}>DETAIL →</button> : null}</header>
      <div className="panel-body">{children}</div>
    </section>
  );
}
const Read = ({ k, t, testid }: { k: string; t: string | null | undefined; testid?: string }) =>
  t ? <p className="mo-read" data-testid={testid}><span className="mo-k mono">{k}</span> {t}</p> : <p className="mo-read mo-none mono" data-testid={testid}>{k} · 종합 코멘트 없음</p>;
const Kv = ({ k, v, color, sub }: { k: string; v: React.ReactNode; color?: string; sub?: React.ReactNode }) => (
  <div className="mo-kv"><span className="mo-k mono">{k}</span><b style={color ? { color } : undefined}>{v}</b>{sub ? <small>{sub}</small> : null}</div>
);
const Excluded = ({ what }: { what: string }) => <div className="mo-excl mono">{what} · EXCLUDED — 이 날짜 데이터 없음</div>;

function sigText(g: RsSignal): string {
  if (g.state === "EXCLUDED" || g.value === null) return "EXCLUDED";
  if (/상승 비율/.test(g.label)) return `${(g.value * 100).toFixed(0)}% 상승`;
  return arrowOf(g.value);
}

function Equity({ c, ov }: { c: Cockpit; ov: MarketOverview | null }) {
  const sel = c.market_now.selection;
  const ne = sel?.neutral_equity ?? null;
  const v = ov?.view?.equity_view;
  const side = (m: "us" | "kr", title: string, conf: string | undefined, line: string | undefined) => (
    <div className="mo-eq-col" data-testid={`mo-eq-${m}`}>
      <div className="mo-eq-head"><b className="mono">{title}</b>{conf ? <span className="mono" style={{ color: EQ_TONE[conf] ?? "var(--ink)" }}>{conf}</span> : null}</div>
      {line ? <p className="mo-eq-line">{line}</p> : null}
      {ne ? (
        <table className="mo-tbl mono"><tbody>
          {ne[m].signals.map((g) => <tr key={g.key} className={g.state === "EXCLUDED" ? "ex" : ""} title={g.note || undefined}><td>{g.label}</td><td className="num">{sigText(g)}</td></tr>)}
        </tbody></table>
      ) : <Excluded what="주식 신호" />}
    </div>
  );
  return (
    <>
      <div className="mo-eq">
        {side("us", "US EQUITY", sel?.us_equity_confirmation, v?.us)}
        {side("kr", "KOREA EQUITY", sel?.korea_equity_confirmation, v?.korea)}
      </div>
      {v ? <div className="mo-div" data-testid="mo-divergence"><b className="mono">{v.divergence_label}</b> {v.divergence}</div> : null}
      <div className="mo-note mono">화살표 = 위험선호 기준 신호 방향(5일 z 혼합) · 확인 상태는 실시간 탭 REGIME v2 와 같은 값</div>
    </>
  );
}

function Leadership({ c }: { c: Cockpit }) {
  const L = c.leadership;
  const detail = new Map<string, CkLeaderRow>([...L.leaders, ...L.laggards].map((r) => [r.key, r]));
  const rows = (L.all_rows.length ? L.all_rows : L.leaders).slice(0, 5);
  return (
    <ol className="mo-lead" data-testid="mo-leadership">
      {rows.map((r) => {
        const d = (detail.get(r.key) ?? r).detail;
        const stocks = (d?.key_stocks ?? []).slice(0, 3).map((s) => s.name);
        return (
          <li key={r.key}>
            <div className="mo-lead-h"><b>{r.label}</b> <span className="mono">{r.arrow}</span>
              <span className="mono mo-lead-m">1W 상대 {sg(r.rel_1w)}σ · breadth {r.breadth === null ? "–" : `${r.breadth.toFixed(0)}%`}</span></div>
            {d?.why?.[0] ? <div className="mo-lead-w">{d.why[0]}</div> : null}
            {stocks.length ? <div className="mo-lead-s mono">대표 {stocks.join(" · ")}</div> : null}
          </li>
        );
      })}
    </ol>
  );
}

export function MarketOverviewView({ cockpit: c, overview, overviewError, rates, oil, ai, semi, onDetail, archived }: {
  cockpit: Cockpit | null; overview: MarketOverview | null; overviewError?: string | null; rates: RatesRegime | null; oil: OilRegime | null; ai: AiRegime | null;
  semi: SemiconductorCycle | null; onDetail?: (t: DetailTarget) => void; archived?: boolean;
}) {
  const v = overview?.status === "ok" ? overview.view : null;
  const now = c?.market_now;
  const st = now?.state ?? null;
  const sel = now?.selection ?? null;
  const days = c?.history?.days ?? [];
  const yb10 = rates?.yield_breakdown?.tenors?.find((t) => t.tenor === "10Y") ?? null;
  const caRows = c?.cross_asset.rows ?? [];
  const sdate = overview?.snapshot_date ?? null;
  const upcoming = (rates?.events?.upcoming ?? []).filter((u) => !sdate || u.date >= sdate);
  const why = new Map((v?.catalysts ?? []).map((x) => [`${x.date}|${x.event}`, x]));
  return (
    <div className="mo" data-testid="market-overview">
      {/* 1. MARKET VIEW — 가장 먼저 읽히는 판단 */}
      <section className="panel mo-sec mo-view" style={{ gridArea: "view" }} data-testid="mo-view">
        <header className="panel-head"><h2 className="panel-title"><span className="mo-n mono">1</span> Market View <em className="mo-ko">시장 종합</em></h2>
          <div className="panel-note mono">{overview?.status === "ok" ? `${overview.source === "llm" ? "AI 종합" : "AI 종합 · 세션"}${sdate ? ` · ${sdate} Daily Snapshot` : ""}` : ""}</div></header>
        <div className="panel-body">
          {v ? (
            <>
              <span className="mo-k mono">CURRENT MARKET CALL</span>
              <p className="mo-headline" data-testid="mo-headline">{v.headline}</p>
              <span className="mo-k mono">MARKET SYNTHESIS</span>
              <p className="mo-synth" data-testid="mo-synthesis">{v.market_view}</p>
              <div className="mo-labels mono" data-testid="mo-labels">
                <span><i>REGIME</i><b style={{ color: st ? keyColor(st.official) : "var(--ink)" }}>{v.labels.regime}</b></span>
                <span><i>EQUITY</i><b style={{ color: TONE[v.labels.equity] }}>{v.labels.equity.toUpperCase()}</b></span>
                <span><i>MACRO</i><b style={{ color: TONE[v.labels.macro] }}>{v.labels.macro.toUpperCase()}</b></span>
                <span><i>RISK</i><b style={{ color: TONE[v.labels.risk] }}>{v.labels.risk.toUpperCase()}</b></span>
              </div>
            </>
          ) : (
            <p className="mo-none mono" data-testid="mo-view-none">
              MARKET VIEW 종합 코멘트 없음 — {overviewError ?? overview?.reason ?? (archived ? "이 날짜 저장본에는 종합 코멘트가 없다(NOT ARCHIVED)" : "불러오는 중")}. 아래 칸의 숫자는 같은 날짜 저장 데이터 그대로다.
            </p>
          )}
        </div>
      </section>

      {/* 2. REGIME & MARKET STATE */}
      <Sec n={2} title="Regime & Market State" area="regime" detail="live" onDetail={onDetail} testid="mo-regime">
        {now ? (
          <>
            <div className="mo-grid2">
              <Kv k="OFFICIAL" v={now.label_text} color={st ? keyColor(st.official) : undefined} />
              <Kv k="CURRENT CANDIDATE" v={st ? keyText(st.candidate) : now.raw_text} color={st ? keyColor(st.candidate) : undefined} />
              <Kv k="REGIME CONFIDENCE" v={sel ? sel.regime_confidence : "–"} />
              {isV2(st) ? <Kv k="TRANSITION" v={st.entry_regime ? `${keyText(st.entry_regime)} ${entryText(st).text}` : exitText(st).text} /> : <Kv k="TRANSITION" v={now.transition_status.replace(/_/g, " ")} />}
              <Kv k="US" v={sel?.us_equity_confirmation ?? "–"} color={EQ_TONE[sel?.us_equity_confirmation ?? ""]} />
              <Kv k="KOREA" v={sel?.korea_equity_confirmation ?? "–"} color={EQ_TONE[sel?.korea_equity_confirmation ?? ""]} />
              <Kv k="GLOBAL" v={sel?.global_equity_confirmation ?? "–"} color={EQ_TONE[sel?.global_equity_confirmation ?? ""]} />
              <Kv k="STATUS" v={now.transition_status === "TRANSITION_WATCH" ? "WATCH" : now.transition_status.replace(/_/g, " ")} />
            </div>
            {days.length ? (
              <div className="mo-strip" data-testid="mo-regime-strip" title={days.map((d) => `${d.date} ${d.display_label}`).join("\n")}>
                <span className="mo-k mono">OFFICIAL · 1M</span>
                <span className="mo-strip-c">{days.map((d) => <i key={d.date} style={{ background: KEY_COLOR[d.display_regime] ?? "var(--rule)" }} />)}</span>
              </div>
            ) : null}
            <Read k="REGIME READ" t={v?.regime_read} testid="mo-regime-read" />
          </>
        ) : <Excluded what="실시간 regime" />}
      </Sec>

      {/* 3. WHAT IS DRIVING THE MARKET */}
      <Sec n={3} title="What Is Driving the Market?" area="drivers" testid="mo-drivers">
        {v ? (
          <ul className="mo-list">
            {v.key_drivers.map((d) => (
              <li key={d.name} data-testid="mo-driver"><div className="mo-li-h"><b>{d.name}</b><span className="mono" style={{ color: TONE[d.direction] }}>{d.direction}</span><span className="mono mo-sub">{d.strength}</span></div><div className="mo-li-t">{d.read}</div></li>
            ))}
          </ul>
        ) : <Read k="KEY DRIVERS" t={null} />}
      </Sec>

      {/* 4. EQUITY MARKET */}
      <Sec n={4} title="Equity Market" ko="미국 · 한국" area="equity" detail="live" onDetail={onDetail} testid="mo-equity">
        {c ? <Equity c={c} ov={overview} /> : <Excluded what="주식시장" />}
      </Sec>

      {/* 5. RATES & INFLATION */}
      <Sec n={5} title="Rates & Inflation" area="rates" detail="rates" onDetail={onDetail} testid="mo-rates">
        {rates ? (
          <>
            <div className="mo-big mono" data-testid="mo-rates-regime">{rates.regime_label.split(" — ")[0]}</div>
            <div className="mo-grid2">
              <Kv k="US 10Y" v={rates.rate_move.level === null ? "–" : `${rates.rate_move.level.toFixed(2)}%`} sub={`5D ${sg(rates.rate_move.change_5d_bp, 0, "bp")}`} />
              <Kv k="DIRECTION" v={rates.top?.direction_en ?? rates.rate_move.direction.toUpperCase()} />
              <Kv k="CURVE" v={rates.curve_move?.shape ?? rates.curve.shape.replace(/_/g, " ").toUpperCase()} />
              <Kv k="PRIMARY DRIVER" v={rates.top?.primary?.label ?? "–"} />
              <Kv k="REAL YIELD 10Y" v={yb10?.real_bp === null || yb10?.real_bp === undefined ? "–" : `${sg(yb10.real_bp, 0, "bp")}`} sub="5D" />
              <Kv k="BREAKEVEN 10Y" v={yb10?.breakeven_bp === null || yb10?.breakeven_bp === undefined ? "–" : `${sg(yb10.breakeven_bp, 0, "bp")}`} sub="5D" />
              <Kv k="INFLATION PRESSURE" v={rates.inflation_map?.signal_ko ?? "–"} />
            </div>
            <Read k="EQUITY IMPACT" t={v?.rates_view} testid="mo-rates-impact" />
          </>
        ) : <Excluded what="금리" />}
      </Sec>

      {/* 6. OIL / MACRO / CROSS-ASSET */}
      <Sec n={6} title="Oil / Macro / Cross-Asset" area="cross" detail="oil" onDetail={onDetail} testid="mo-cross">
        {oil ? <div className="mo-big mono" data-testid="mo-oil-regime">OIL · {oil.regime_label}</div> : <Excluded what="유가" />}
        {caRows.length ? (
          <div className="mo-chips mono" data-testid="mo-cross-rows">
            {caRows.map((r) => <span key={r.key} title={r.instrument_label}><i>{r.label}</i> <b>{r.arrow}</b> <small className="num">{r.z === null ? "결측" : `${sg(r.z)}σ`}</small></span>)}
          </div>
        ) : null}
        <Read k="CROSS-ASSET READ" t={v?.cross_asset_view} testid="mo-cross-read" />
      </Sec>

      {/* 7. AI & SEMICONDUCTOR CYCLE — 두 엔진을 나란히, 아래에 연결 해석 */}
      <Sec n={7} title="AI & Semiconductor Cycle" area="aisemi" testid="mo-aisemi">
        <div className="mo-eq">
          <div className="mo-eq-col" data-testid="mo-ai">
            <div className="mo-eq-head"><b className="mono">AI THEME</b>{onDetail ? <button type="button" className="mo-detail mono" onClick={() => onDetail("ai")}>DETAIL →</button> : null}</div>
            {ai ? (
              <>
                <div className="mo-big mono">{ai.regime_label}</div>
                <table className="mo-tbl mono"><tbody>
                  {ai.status_strip.filter((x) => /Relative|Price|Breadth|Fundamental|Infra|Software/i.test(x.label)).map((x) => <tr key={x.key}><td>{x.label}</td><td>{x.value}</td></tr>)}
                </tbody></table>
              </>
            ) : <Excluded what="AI 센티" />}
          </div>
          <div className="mo-eq-col" data-testid="mo-semi">
            <div className="mo-eq-head"><b className="mono">SEMICONDUCTOR CYCLE</b>{onDetail ? <button type="button" className="mo-detail mono" onClick={() => onDetail("semi")}>DETAIL →</button> : null}</div>
            {semi ? (
              <>
                <div className="mo-big mono">{semi.regime.label}{semi.regime.composite !== null ? <small> {sg(semi.regime.composite)}</small> : null}</div>
                <table className="mo-tbl mono"><tbody>
                  {semi.regime.components.map((x) => <tr key={x.key} className={x.score === null ? "ex" : ""}><td>{x.label}</td><td className="num">{x.score === null ? "EXCLUDED" : sg(x.score, 0)}</td></tr>)}
                </tbody></table>
              </>
            ) : <Excluded what="반도체 사이클" />}
          </div>
        </div>
        <Read k="AI ↔ SEMICONDUCTOR READ" t={v?.ai_semiconductor_view} testid="mo-aisemi-read" />
      </Sec>

      {/* 8. MARKET LEADERSHIP */}
      <Sec n={8} title="Market Leadership" area="lead" detail="live" onDetail={onDetail} testid="mo-lead">
        <Read k="LEADERSHIP" t={v?.leadership_view} testid="mo-lead-read" />
        {c ? <Leadership c={c} /> : <Excluded what="리더십" />}
      </Sec>

      {/* 9. STYLE & SECTOR VIEW */}
      <Sec n={9} title="Style & Sector View" area="style" testid="mo-style">
        {v ? (
          <div className="mo-eq">
            <div className="mo-eq-col">
              <span className="mo-k mono">STYLE</span>
              <table className="mo-tbl"><tbody>{v.style_view.map((s) => <tr key={s.style} data-testid="mo-style-row"><td className="mono">{s.style}</td><td className="mono" style={{ color: TONE[s.view] }}>{s.view}</td><td>{s.read}</td></tr>)}</tbody></table>
            </div>
            <div className="mo-eq-col" data-testid="mo-sector">
              <span className="mo-k mono">SECTOR</span>
              {(["positive", "watch", "negative"] as const).map((b) => (
                <div key={b} className="mo-sector-r"><b className="mono" style={{ color: b === "positive" ? "var(--ok)" : b === "negative" ? "var(--crit)" : "var(--warn)" }}>{b.toUpperCase()}</b><span>{v.sector_view[b].length ? v.sector_view[b].join(" · ") : "–"}</span></div>
              ))}
              {v.sector_view.read ? <p className="mo-li-t">{v.sector_view.read}</p> : null}
            </div>
          </div>
        ) : <Read k="STYLE & SECTOR" t={null} />}
      </Sec>

      {/* 10. RISK MAP */}
      <Sec n={10} title="Risk Map" area="risk" testid="mo-risk">
        {v ? (
          <ul className="mo-list">{v.top_risks.map((r) => <li key={r.risk} data-testid="mo-risk-row"><div className="mo-li-h"><b>{r.risk}</b><span className="mono" style={{ color: TONE[r.level] }}>{r.level}</span></div><div className="mo-li-t">{r.read}</div></li>)}</ul>
        ) : <Read k="RISK MAP" t={null} />}
      </Sec>

      {/* 11. CATALYSTS & EVENTS — 저장된 일정(그 날짜 이후)만, 의미는 LLM */}
      <Sec n={11} title="Catalysts & Events" area="cat" detail="rates" onDetail={onDetail} testid="mo-cat">
        {upcoming.length ? (
          <ul className="mo-list">
            {upcoming.slice(0, 6).map((u) => {
              const w = why.get(`${u.date}|${u.name}`);
              return (
                <li key={`${u.date}-${u.name}`} data-testid="mo-cat-row"><div className="mo-li-h"><b className="mono">{u.date.slice(5).replace("-", "/")}</b><b>{u.name}</b>{w ? <span className="mono" style={{ color: TONE[w.sensitivity] }}>{w.sensitivity}</span> : <span className="mono mo-sub">{u.importance}</span>}</div>
                  {w ? <div className="mo-li-t">{w.why}</div> : null}</li>
              );
            })}
          </ul>
        ) : <Excluded what="예정 이벤트" />}
      </Sec>

      {/* 12. WHAT MATTERS NEXT */}
      <Sec n={12} title="What Matters Next" area="next" testid="mo-next">
        {v ? (
          <ol className="mo-next">{v.what_matters_next.map((x) => <li key={x.title} data-testid="mo-next-row"><b>{x.title}</b><span>{x.condition}</span><em>→ {x.implication}</em></li>)}</ol>
        ) : <Read k="WHAT MATTERS NEXT" t={null} />}
      </Sec>

      {/* 13. PORTFOLIO IMPLICATION — 매매 지시가 아니라 관점 */}
      <Sec n={13} title="Portfolio Implication" area="port" testid="mo-port">
        {v ? (
          <div className="mo-port">
            <Kv k="EQUITY STANCE" v={v.portfolio_implication.equity_stance} />
            <Kv k="STYLE" v={v.portfolio_implication.style} />
            <Kv k="SECTOR" v={v.portfolio_implication.sector} />
            <Kv k="RISK CONTROL" v={v.portfolio_implication.risk_control} />
            <Kv k="HEDGE / WATCH" v={v.portfolio_implication.hedge_watch} />
            <div className="mo-note mono">투자 관점(Overweight bias · Neutral · Underweight bias · Watch)이며 매매 지시가 아니다</div>
          </div>
        ) : <Read k="PORTFOLIO IMPLICATION" t={null} />}
      </Sec>
    </div>
  );
}
