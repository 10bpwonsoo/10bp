import { useState } from "react";
import type { Cockpit, CkArrow, CkDriver, CkCatalyst, CkRadarStock, CkLeaderRow, CkWatchRow, AnalystView, AnalystViews, IntelligenceSnapshot, MarketStateHistory } from "../api/types";
import { useAnalystViews } from "../api/useAnalystViews";
import { IssuePathView } from "./IssuePath";
import { COLOR_LEGEND, MATCH_COLOR, STATUS_KO, STATUS_KO_SHORT, glossaryFor } from "./ko";
import { LABEL_KO } from "./StateHistoryStrip";
import { RegimeHistoryCard } from "./RegimeHistoryCard";

/**
 * 실시간 메인 탭 — decision cockpit.
 * MARKET NOW → MARKET REGIME HISTORY · 1M(실시간 2 전용 히스토리 층) → TODAY'S MARKET DRIVERS → CROSS-ASSET CONFIRMATION(+KEY DIVERGENCES) → MARKET LEADERSHIP(+THEME PULSE)
 * → MARKET → STOCK TRANSMISSION → STOCK RADAR → LIVE CATALYSTS(고정 높이·내부 스크롤) → EARNINGS PULSE(있을 때만)
 * → WHAT MATTERS NEXT → WATCHLIST → DATA STATUS. 숫자는 서버가 고르고 화면은 그리기만 한다. 비어 있는 카드는 숨긴다.
 * 색은 Critical/Warning · Positive confirmation · Neutral · Missing 에만 쓴다 — 금리처럼 자산마다 뜻이 다른 값은 화살표·상태 글자가 먼저다.
 */
const LABEL_COLOR: Record<string, string> = {
  RISK_ON: "var(--lbl-risk-on)", RISK_OFF: "var(--lbl-risk-off)", GROWTH_SHOCK: "var(--lbl-growth)", INFLATION_SHOCK: "var(--lbl-inflation)",
  LIQUIDITY_STRESS: "var(--lbl-liquidity)", POLICY_DRIVEN: "var(--lbl-policy)", GEOPOLITICAL_RISK: "var(--lbl-geopolitical)", NEUTRAL: "var(--lbl-neutral)",
};
const CONV_COLOR: Record<string, string> = { HIGH: "var(--ok)", MEDIUM: "var(--warn)", LOW: "var(--muted)" };
const STATUS_COLOR: Record<string, string> = {
  CONFIRM: "var(--ok)", CONFIRMED: "var(--ok)", CONFIRMING: "var(--ok)", DIVERGE: "var(--warn)", HEADWIND: "var(--warn)", WATCH: "var(--warn)", UNCONFIRMED: "var(--muted)",
  FLAT: "var(--muted)", NEUTRAL: "var(--faint)", MISSING: "var(--faint)", "NO DATA": "var(--faint)", CONTRADICTED: "var(--crit)", REVERSING: "var(--crit)",
  CRITICAL: "var(--crit)", HIGH: "var(--warn)", MEDIUM: "var(--muted)", LOW: "var(--faint)",
};
const sg = (v: number | null | undefined, d = 1, unit = "") => (v === null || v === undefined ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);
const Arrow = ({ a }: { a: CkArrow }) => <span className="ck-arrow mono">{a}</span>;
const St = ({ s }: { s: string }) => <span className="mono ck-st" style={{ color: STATUS_COLOR[s] ?? "var(--muted)" }}>{s}</span>;

function Card({ title, note, area, children, testid, accent }: { title: string; note?: React.ReactNode; area: string; children: React.ReactNode; testid?: string; accent?: boolean }) {
  return (
    <section className={`panel ck-card${accent ? " ck-accent" : ""}`} style={{ gridArea: area }} data-testid={testid}>
      <header className="panel-head"><h2 className="panel-title">{title}</h2>{note ? <div className="panel-note mono">{note}</div> : null}</header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

function MarketNow({ c }: { c: Cockpit }) {
  const n = c.market_now; const col = LABEL_COLOR[n.label] ?? "var(--ink)";
  const last = new Date(n.last_update).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "medium", timeStyle: "short" });
  return (
    <Card title="Market Now" area="now" testid="ck-now" accent>
      <div className="ck-now-label" style={{ color: col }} data-testid="ck-now-label">{n.label_text}</div>
      <div className="ck-now-meta mono">
        <span>Conviction <b style={{ color: CONV_COLOR[n.conviction] }}>{n.conviction}</b> <small>{n.confidence.toFixed(0)}%</small></span>
        <span>Persistence <b>{n.persistence_days}D</b></span>
        <span>Change <b>{n.change_text}</b></span>
      </div>
      <div className="ck-kv" data-testid="ck-key-variables">
        {n.key_variables.map((k) => (
          <div key={k.id} className="ck-kv-row"><span className="ck-kv-l">{k.label}</span><span className="num">{sg(k.z)}σ</span><Arrow a={k.arrow} /><span className="mono ck-kv-c">{k.change_display}</span></div>
        ))}
      </div>
      <p className="ck-sentence" data-testid="ck-sentence">"{n.sentence}"</p>
      {n.interpretation ? <p className="ck-interp"><span className="ck-k mono">MARKET INTERPRETATION</span> {n.interpretation}</p> : null}
      {n.spark.length ? (
        <div className="ck-spark" title={n.spark.map((p) => `${p.date} ${LABEL_KO[p.label] ?? p.label}`).join("\n")} data-testid="ck-spark">
          <span className="ck-k mono">Regime persistence</span>
          <span className="ck-spark-strip">{n.spark.map((p) => <i key={p.date} style={{ background: LABEL_COLOR[p.label] ?? "var(--rule)" }} />)}</span>
          <span className="mono ck-spark-t">{n.persistence_days}D {n.label_text.split(" / ")[0]}</span>
        </div>
      ) : null}
      <div className="ck-foot mono">Last update {last} KST · Data coverage {n.coverage}{n.latency ? ` · Latency ${n.latency}` : ""}</div>
    </Card>
  );
}

function DriverCard({ d, i }: { d: CkDriver; i: number }) {
  const ev = d.evidence.filter((e) => e.available).slice(0, 4);
  return (
    <div className="ck-drv" data-testid="ck-driver" data-key={d.key}>
      <div className="ck-drv-head"><span className="ck-drv-n mono">{["①", "②", "③", "④", "⑤"][i] ?? i + 1}</span><b className="ck-drv-title">{d.label}</b><Arrow a={d.arrow} />
        <span className="mono ck-drv-tags">{d.confirmed_by_regime ? <em title="판정의 크로스에셋 확인 자산을 포함">CONFIRMED</em> : null}{d.persistent ? <em title="1주 전에도 같은 방향">PERSISTENT</em> : null}{d.source === "alternative" ? <em>ALT DATA</em> : null}</span></div>
      <div className="ck-drv-ev mono">
        {ev.map((e) => <span key={e.id} className={e.context ? "ctx" : ""} title={e.context ? "참고 값 — 점수에 안 들어간다" : e.display}>{e.label} <b className="num">{sg(e.z)}σ</b></span>)}
      </div>
      <div className="ck-drv-why"><span className="ck-k mono">Why it matters</span> {d.why}</div>
    </div>
  );
}

function Drivers({ c, mobileTop }: { c: Cockpit; mobileTop: number }) {
  const [all, setAll] = useState(false);
  const list = c.drivers;
  return (
    <Card title="Today's Market Drivers" area="drivers" testid="ck-drivers" note={`상위 ${list.length} · 강도×확보 + 확인 + 지속 + 뉴스 촉매 × 영향도 — |z| 순이 아니다`}>
      <div className="ck-drvs">{list.map((d, i) => <div key={d.key} className={i >= mobileTop && !all ? "ck-m-hide" : ""}><DriverCard d={d} i={i} /></div>)}</div>
      {list.length > mobileTop ? <button className="ck-more ck-m-only" onClick={() => setAll(!all)}>{all ? "접기" : `나머지 ${list.length - mobileTop}개 보기`}</button> : null}
    </Card>
  );
}

/** 영어 상태값 + 한글 의미. 데스크톱은 두 줄, 모바일은 `CONFIRM · 판단 지지` 한 줄(CSS 로 전환). */
export function StatusKo({ s, ko }: { s: string; ko?: string }) {
  return (
    <span className="ck-sk" data-status={s}>
      <span className="mono ck-st" style={{ color: MATCH_COLOR[s] ?? "var(--muted)" }}>{s}</span>
      <span className="ck-sk-ko">{ko ?? STATUS_KO[s] ?? ""}</span>
      <span className="ck-sk-short">· {STATUS_KO_SHORT[s] ?? ""}</span>
    </span>
  );
}

const GROUP_ORDER: ("RISK" | "MACRO" | "COMMODITY")[] = ["RISK", "MACRO", "COMMODITY"];
const GROUP_LABEL: Record<string, string> = { RISK: "RISK", MACRO: "MACRO", COMMODITY: "COMMODITY / SAFE HAVEN" };

function CrossAssetCard({ c }: { c: Cockpit }) {
  const ca = c.cross_asset; const [all, setAll] = useState(false);
  const shown = all ? ca.divergences : ca.divergences.slice(0, 2);
  return (
    <Card title="Cross-Asset Confirmation" area="cross" testid="ck-cross" note={<span>Regime Confirmation <b className="num">{ca.confirm} / {ca.evaluated}</b> assets</span>}>
      <p className="ck-sub" data-testid="ck-cross-purpose">현재 시장 판단이 주식·금리·신용·달러 등 다른 시장에서도 같은 방향으로 확인되는지 점검합니다.</p>
      <div className="ck-ca-top">
        <div><span className="ck-k mono">Current market view</span><b className="ck-ca-view" style={{ color: LABEL_COLOR[c.market_now.label] ?? "var(--ink)" }} data-testid="ck-cross-view">{ca.current_view}</b></div>
        <div><span className="ck-k mono">Regime confirmation</span><b className="num mono ck-ca-n">{ca.confirm} / {ca.evaluated} assets</b><span className="ck-ca-ct" data-testid="ck-cross-confirm-text">{ca.confirm_text}</span></div>
      </div>
      {ca.market_read ? <div className="ck-read" data-testid="ck-market-read"><span className="ck-k mono">Market read</span><p>{ca.market_read}</p></div> : null}
      <div className="ck-ca-groups">
        {GROUP_ORDER.map((g) => {
          const rows = ca.rows.filter((r) => r.group === g);
          if (!rows.length) return null;
          return (
            <div key={g} className="ck-ca-group" data-testid="ck-ca-group" data-group={g}>
              <span className="ck-k mono ck-ca-gl">{GROUP_LABEL[g]}</span>
              {rows.map((r) => (
                <div key={r.key} className="ck-ca-row2" data-testid="ck-ca-row" data-status={r.status}>
                  <div className="ck-ca-l"><b className="mono">{r.key}</b><span className="ck-ca-inst" title={glossaryFor(r.instrument_label)}>{r.instrument_label}</span></div>
                  <div className="ck-ca-v num mono">{r.z === null ? "–" : `${sg(r.z)}σ`} <Arrow a={r.arrow} /></div>
                  <div className="ck-ca-s"><StatusKo s={r.status} ko={r.meaning} /></div>
                </div>
              ))}
            </div>
          );
        })}
      </div>
      {ca.divergences.length ? (
        <div className="ck-div" data-testid="ck-divergences">
          <div className="ck-div-h"><span className="ck-k mono">Key divergence</span><span className="ck-sub-i">보통 같이 움직이던 두 신호가 지금 갈리는 곳 — 현상 → 왜 중요한가 → 근거</span></div>
          {shown.map((d, k) => (
            <div key={k} className="ck-div-row" data-testid="ck-divergence">
              <div className="ck-div-t"><b>{d.title}</b><span className="num mono ck-div-sev" title="괴리 심각도 0~100 (확률 아님)">{d.severity.toFixed(0)}</span></div>
              {d.phenomenon ? <div className="ck-div-ph">{d.phenomenon}</div> : null}
              <div className="ck-div-why"><span className="ck-k mono">Why it matters</span> {d.why || d.meaning}</div>
              {d.reference.length ? <div className="ck-div-ref mono"><span className="ck-k">Reference</span> {d.reference.map((r) => <span key={r}>{r}</span>)}</div> : null}
            </div>
          ))}
          {ca.total_divergences > 2 ? <button type="button" className="ck-more" onClick={() => setAll(!all)}>{all ? "접기" : `View all (${ca.total_divergences})`}</button> : null}
        </div>
      ) : null}
      <div className="ck-legend mono">{COLOR_LEGEND}</div>
    </Card>
  );
}

const STANCE_KO2: Record<string, string> = { constructive: "긍정적", cautious: "신중", neutral: "중립", mixed: "혼재" };

function LeadershipDetailView({ r, onStock }: { r: CkLeaderRow; onStock?: (id: string) => void }) {
  const d = r.detail!;
  return (
    <div className="ck-ld" data-testid="ck-lead-detail" onClick={(e) => e.stopPropagation()}>
      <div className="ck-ld-col">
        <div className="ck-ld-sec" data-testid="ck-ld-why"><span className="ck-k mono">Why leading?</span><span className="ck-sub-i">시장 데이터로 본 이유 — 수익률 반복이 아니라 무엇이 확인되는가</span>
          <ol className="ck-ld-why">{d.why.map((w, i) => <li key={i}>{w}</li>)}</ol></div>
        <div className="ck-ld-sec" data-testid="ck-ld-conf"><span className="ck-k mono">Market confirmation</span><span className="ck-sub-i">가격만 보지 않는다 — 상대강도 · breadth · 뉴스 · 펀더멘털 · driver</span>
          {d.confirmation.map((c) => <div key={c.key} className="ck-ld-cf"><span className="ck-ld-cf-l mono">{c.label}</span><span className="num mono">{c.value}</span><StatusKo s={c.status} ko={c.meaning} /></div>)}</div>
        <div className="ck-ld-sec ck-ld-sys" data-testid="ck-ld-system"><span className="ck-k mono">System view <em>INTERNAL · 내부 데이터 해석</em></span>
          <p>{d.system_view}</p>
          <div className="ck-ld-3 mono"><span><i className="ck-k">Driver</i>{d.driver}</span><span><i className="ck-k">Quality</i><b>{d.quality}</b> <small>{d.quality_ko}{d.quality_detail ? ` · ${d.quality_detail}` : ""}</small></span><span><i className="ck-k">Risk</i>{d.risk}</span></div></div>
      </div>
      <div className="ck-ld-col">
        {d.street.length ? (
          <div className="ck-ld-sec ck-ld-street" data-testid="ck-ld-street"><span className="ck-k mono">Street view <em>EXTERNAL · 외부 리서치 / 시장 전문가</em></span>
            {d.street.map((v, i) => (
              <div key={i} className="ck-ld-sv">
                <div className="ck-ld-sv-h mono"><b>{v.institution}{v.analyst ? ` · ${v.analyst}` : " Research"}</b><span>{v.published_date.slice(5).replace("-", "/")} · {v.freshness} · {STANCE_KO2[v.stance] ?? v.stance}</span></div>
                {v.quote ? <div className="ck-ld-sv-q">“{v.quote}”</div> : null}
                <div className="ck-ld-sv-s">{v.summary}</div>
                <div className="ck-ld-sv-f mono">{v.key_variables.length ? <span>{v.key_variables.join(" · ")}</span> : null}<a className="news-link" href={v.source_url} target="_blank" rel="noreferrer">{v.source_title || "출처"}</a></div>
              </div>
            ))}
            {d.street_read ? <div className="ck-ld-read"><span className="ck-k mono">System read</span> {d.street_read}</div> : null}
          </div>
        ) : null}
        {d.key_stocks.length ? (
          <div className="ck-ld-sec" data-testid="ck-ld-stocks"><span className="ck-k mono">Key stocks</span><span className="ck-sub-i">구성종목 목록이 아니라 지금 leadership 을 설명하는 종목</span>
            {d.key_stocks.map((k) => (
              <div key={k.id} className={`ck-ld-ks${k.in_radar ? " radar" : ""}`} data-testid="ck-ld-stock" onClick={k.in_radar && onStock ? () => onStock(k.id) : undefined} role={k.in_radar && onStock ? "button" : undefined}>
                <span className="ck-ld-ks-n"><b>{k.name}</b>{k.in_radar ? <em className="ck-p-radar" title="STOCK RADAR 에 있는 종목 — 누르면 radar 로">RADAR ●</em> : null}</span>
                <span className="mono ck-ld-ks-r">{k.role}{k.role && k.note ? " · " : ""}{k.note}</span>
                <span className="num mono">{k.z === null ? "–" : `${sg(k.z)}σ`}</span>
              </div>
            ))}</div>
        ) : null}
        {d.watch.length ? <div className="ck-ld-sec" data-testid="ck-ld-watch"><span className="ck-k mono">What to watch</span><span className="ck-sub-i">이 leadership 이 유지되거나 약해질 조건</span><ol className="ck-ld-why">{d.watch.map((w, i) => <li key={i}>{w}</li>)}</ol></div> : null}
      </div>
    </div>
  );
}

function LeadRow({ r, open, setOpen }: { r: CkLeaderRow; open: string | null; setOpen: (k: string | null) => void }) {
  const isOpen = open === r.key;
  return (
    <div className={`ck-lead-row${r.detail ? " has-detail" : ""}${isOpen ? " open" : ""}`} data-testid="ck-lead-row" data-key={r.key} title={`${r.kind} · ${r.available}/${r.instruments} 계열`} onClick={r.detail ? () => setOpen(isOpen ? null : r.key) : undefined} role={r.detail ? "button" : undefined} tabIndex={r.detail ? 0 : undefined} onKeyDown={(e) => { if (r.detail && e.key === "Enter") setOpen(isOpen ? null : r.key); }}>
      <div className="ck-lead-h"><span className="ck-lead-l">{r.label}</span><Arrow a={r.arrow} />{r.detail ? <span className="ck-nx-open mono">{isOpen ? "▾" : "›"}</span> : null}</div>
      <span className="mono ck-lead-v">{sg(r.z_1d)}σ <small>1D</small> | vs market {sg(r.rel_1w)}σ | breadth {r.breadth === null ? "–" : `${r.breadth.toFixed(0)}%`}</span>
      {r.system_view ? <span className="ck-lead-sv" data-testid="ck-lead-system-view"><span className="ck-k mono">System view</span> {r.system_view}</span> : null}
    </div>
  );
}

function LeadershipCard({ c, onStock }: { c: Cockpit; onStock?: (id: string) => void }) {
  const l = c.leadership; const [pulseOpen, setPulseOpen] = useState(false); const [open, setOpen] = useState<string | null>(null);
  return (
    <Card title="Market Leadership" area="lead" testid="ck-leadership" note="1D z · 1주 상대(vs S&P) · breadth(20일선 위) · 테마를 누르면 Leadership detail">
      <p className="ck-sub">무엇이 강한가에 더해 왜 강한가 · 무엇이 확인하는가 · 지속 가능한가 · 어떤 종목으로 이어지는가를 봅니다. 하루 수익률 순이 아니라 상대강도 · breadth · 지속성 · 확인 여부로 고릅니다.</p>
      {l.read ? <div className="ck-read" data-testid="ck-lead-read"><span className="ck-k mono">Leadership read</span><p>{l.read}</p></div> : null}
      <div className="ck-lead-cols">
        <div><span className="ck-k mono">Leaders</span>{l.leaders.length ? l.leaders.map((r) => <LeadRow key={r.key} r={r} open={open} setOpen={setOpen} />) : <div className="sv-muted">문턱을 넘는 리더 없음</div>}</div>
        <div><span className="ck-k mono">Laggards</span>{l.laggards.length ? l.laggards.map((r) => <LeadRow key={r.key} r={r} open={open} setOpen={setOpen} />) : <div className="sv-muted">문턱을 넘는 후미 없음</div>}</div>
      </div>
      {(() => { const r = [...l.leaders, ...l.laggards].find((x) => x.key === open); return r && r.detail ? (
        <div className="ck-ld-wrap" data-testid="ck-lead-detail-wrap">
          <div className="ck-ld-head"><b>{r.label}</b><span className="mono ck-sub-i">Leadership detail · {sg(r.z_1d)}σ 1D | vs market {sg(r.rel_1w)}σ | breadth {r.breadth === null ? "–" : `${r.breadth.toFixed(0)}%`}</span><button type="button" className="ck-more" onClick={() => setOpen(null)}>닫기</button></div>
          <LeadershipDetailView r={r} onStock={onStock} />
        </div>) : null; })()}
      {l.pulse.length ? (
        <details className="ck-pulse" open={pulseOpen} onToggle={(e) => setPulseOpen((e.target as HTMLDetailsElement).open)} data-testid="ck-pulse">
          <summary className="ck-k mono">Theme Pulse · {l.pulse.length} themes <span style={{ color: "var(--faint)" }}>— PRICE / NEWS / REL</span></summary>
          <div className="ck-pulse-tbl">
            <div className="ck-pulse-row ck-th mono"><span></span><span>PRICE</span><span>NEWS</span><span>REL</span></div>
            {l.pulse.map((p) => <div key={p.theme_id} className="ck-pulse-row" title={`점수 ${sg(p.theme_score, 0)} · 뉴스 ${sg(p.news_sentiment, 0)} · 가격 ${sg(p.price_momentum, 0)} · 1주 상대 ${sg(p.rel_1w)}σ ${p.why}`}><span>{p.name}</span><Arrow a={p.price} /><Arrow a={p.news} /><Arrow a={p.rel} /></div>)}
          </div>
        </details>
      ) : null}
    </Card>
  );
}

const STRENGTH_COLOR: Record<string, string> = { STRONG: "var(--ok)", PARTIAL: "var(--warn)", LIMITED: "var(--muted)", UNCONFIRMED: "var(--faint)" };

function TransmissionCard({ c, focus }: { c: Cockpit; focus?: string | null }) {
  if (!c.transmission.length) return null;
  return (
    <Card title="Market → Stock Transmission" area="trans" testid="ck-transmission" note="DRIVER → INDUSTRY / THEME → STOCK · 가격 확인 붙임">
      <p className="ck-sub">지금 시장 충격이 실제 종목 가격까지 어디까지 번졌는지 — 영향을 줄 수 있다가 아니라 실제로 얼마나 전파됐고 어디서는 아직 아닌지.</p>
      <div className="ck-trans">
        {c.transmission.map((t) => (
          <div key={t.driver_key} id={`ck-tr-${t.driver_key}`} className={`ck-tr${focus === t.driver_key ? " focus" : ""}`} data-testid="ck-chain" data-key={t.driver_key}>
            <div className="ck-tr-d"><b>{t.driver_label}</b></div>
            <div className="ck-tr-m mono">→ {t.mechanism}{t.industries.length ? <span className="ck-tr-i"> · {t.industries.join(" · ")}</span> : null}</div>
            <div className="ck-tr-s">
              {t.stocks.map((s) => <span key={s.id} className="ck-tr-stock" title={`${s.industry ? s.industry + " · " : ""}${s.note}`}><span>{s.name}</span><St s={s.status} /></span>)}
            </div>
            <div className="ck-tr-str" data-testid="ck-chain-strength">
              <span className="mono ck-tr-n">{t.confirmed} / {t.evaluated || t.stocks.length} confirmed</span>
              <span className="ck-sk"><span className="mono ck-st" style={{ color: STRENGTH_COLOR[t.strength] }}>{t.strength}</span><span className="ck-sk-ko" style={{ display: "inline" }}>{t.strength_ko}</span></span>
            </div>
            {t.read ? <div className="ck-tr-read" data-testid="ck-chain-read"><span className="ck-k mono">Transmission read</span><p>{t.read}</p></div> : null}
          </div>
        ))}
      </div>
    </Card>
  );
}

const STANCE_KO: Record<string, string> = { constructive: "긍정적", cautious: "신중", neutral: "중립", mixed: "혼재" };
/** SYSTEM vs ANALYST — 결론을 내지 않는다. 방향이 갈리면 그 사실만 라벨로 적는다. */
function systemVsAnalyst(r: CkRadarStock, v: AnalystView): string {
  const ax = (k: string) => r.system_axes.find((a) => a.key === k)?.arrow ?? "?";
  const up = (a: string) => a === "↑" || a === "↑↑"; const dn = (a: string) => a === "↓" || a === "↓↓";
  const m = ax("market"); const f = ax("fundamental");
  if (v.stance === "constructive" && dn(m)) return "FUNDAMENTAL / PRICE GAP";
  if (v.stance === "cautious" && up(m)) return "ANALYST CAUTION vs PRICE";
  if (v.stance === "constructive" && dn(f)) return "ANALYST vs SYSTEM FUNDAMENTAL";
  if (v.stance === "cautious" && up(f)) return "ANALYST vs SYSTEM FUNDAMENTAL";
  if (v.stance === "mixed") return "MIXED";
  return "ALIGNED";
}

function AnalystLine({ r, v, issues, onIssue }: { r: CkRadarStock; v: AnalystView | undefined; issues: { id: string; text: string }[]; onIssue?: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  if (!v && !issues.length) return null;
  const gap = v ? systemVsAnalyst(r, v) : "";
  const stale = v ? v.age_days > 7 : false;
  return (
    <div className="ck-rd-x">
      {v ? (
        <div className="ck-rd-av" data-testid="ck-analyst-view" onClick={(e) => { e.stopPropagation(); setOpen(!open); }} role="button" tabIndex={0}>
          <div className="ck-rd-av-h mono"><span className="ck-k">Analyst view · <b style={{ color: stale ? "var(--warn)" : "var(--ok)" }}>{v.freshness}</b></span><span className="ck-rd-av-who">{v.analyst} · {v.broker} · {v.published_date.slice(5).replace("-", "/")}</span></div>
          <div className="ck-rd-av-s">{v.summary}</div>
          {open ? (
            <div className="ck-rd-av-d" onClick={(e) => e.stopPropagation()} data-testid="ck-analyst-detail">
              <div className="mono ck-rd-av-grid"><span><i className="ck-k">Analyst</i> {v.analyst}</span><span><i className="ck-k">Broker</i> {v.broker}</span><span><i className="ck-k">Date</i> {v.published_date} ({v.freshness})</span>{v.rating ? <span><i className="ck-k">Rating</i> {v.rating}</span> : null}{v.target_change ? <span><i className="ck-k">Target</i> {v.target_change}</span> : null}</div>
              <div><span className="ck-k mono">Key view</span> {v.key_view || v.summary}</div>
              {v.key_variables.length ? <div className="mono"><span className="ck-k">Key variable</span> {v.key_variables.join(" · ")}</div> : null}
              <div className="ck-rd-sys mono" data-testid="ck-system-vs-analyst">
                <span><i className="ck-k">System</i> {r.system_axes.length ? r.system_axes.map((a) => `${a.label} ${a.arrow}`).join(" · ") : "–"}</span>
                <span><i className="ck-k">Analyst</i> {STANCE_KO[v.stance] ?? v.stance}{v.key_variables[0] ? ` — ${v.key_variables[0]}` : ""}</span>
                <span><i className="ck-k">System vs Analyst</i> <b>{gap}</b> <small>(어느 쪽이 맞다는 결론이 아니다)</small></span>
              </div>
              <div className="mono"><span className="ck-k">Source</span> <a className="news-link" href={v.source_url} target="_blank" rel="noreferrer">{v.source_title || v.source_url}</a> · {v.retrieved_by === "manual" ? "수기 확인" : "웹검색"}</div>
            </div>
          ) : null}
        </div>
      ) : null}
      {issues.length ? (
        <div className="ck-rd-iss mono" data-testid="ck-radar-issues"><span className="ck-k">Related market issues</span> {issues.map((i) => <button key={i.id} type="button" className="ck-rd-iss-b" onClick={(e) => { e.stopPropagation(); onIssue?.(i.id); }}>{i.text}</button>)}</div>
      ) : null}
    </div>
  );
}

function RadarCard({ c, views, onIssue, focus }: { c: Cockpit; views: AnalystViews | null; onIssue?: (id: string) => void; focus?: string | null }) {
  if (!c.radar.length) return null;
  const byId = new Map((views?.views ?? []).map((v) => [v.stock_id, v]));
  const issueText = new Map(c.what_matters_next.map((n) => [n.id, n.text]));
  const n = byId.size;
  return (
    <Card title="Stock Radar" area="radar" testid="ck-radar" note={`${c.radar.length}종목 · 이상 거동·뉴스·테마·펀더멘털·상대강도·매크로 종합 — 수익률 순 아님${views ? ` · Analyst view ${n}/${views.requested.length}${views.pending.length ? " (검색 중)" : ""}` : ""}`}>
      <div className="ck-radar">
        {c.radar.map((r) => (
          <div key={r.id} id={`ck-rd-${r.id}`} className={`ck-rd${focus === r.id ? " focus" : ""}`} data-testid="ck-radar-stock" title={r.signals.join(" · ")}>
            <div className="ck-rd-h"><b>{r.name}</b><span className="num mono" style={{ color: r.change_1d === null ? "var(--faint)" : "var(--ink-2)" }}>{sg(r.change_1d, 1, "%")}</span></div>
            <div className="ck-rd-t mono">{r.tag}</div>
            <div className="ck-rd-w"><span className="ck-k mono">{r.kind === "watch" ? "Watch" : "Why"}</span> {r.why}</div>
            {r.system_axes.length ? <div className="ck-rd-sa mono"><span className="ck-k">System</span> {r.system_axes.map((a) => <span key={a.key} title={a.detail}>{a.label} <b>{a.arrow}</b></span>)}</div> : null}
            <AnalystLine r={r} v={byId.get(r.id)} issues={r.related_issues.map((i) => ({ id: i, text: issueText.get(i) ?? i }))} onIssue={onIssue} />
          </div>
        ))}
      </div>
    </Card>
  );
}

function CatalystRow({ i }: { i: CkCatalyst }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`ck-cat${open ? " open" : ""}`} data-testid="ck-catalyst" data-level={i.level} onClick={() => setOpen(!open)} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") setOpen(!open); }}>
      <div className="ck-cat-h mono"><span style={{ color: STATUS_COLOR[i.level] }}>{i.level}</span><span>{i.time}</span><span className="ck-cat-tag">{i.tag}</span>{i.cluster_size > 1 ? <span className="ck-cat-cl">{i.cluster_size} articles</span> : null}</div>
      <div className={`ck-cat-t${open ? "" : " clamp"}`}>{i.headline}</div>
      <div className="ck-cat-i mono">{i.impact ? <>Impact: {i.impact}</> : null}{i.confidence ? <> · Confidence: <span style={{ color: STATUS_COLOR[i.confidence] }}>{i.confidence}</span></> : null}</div>
      {open ? (
        <div className="ck-cat-x" onClick={(e) => e.stopPropagation()}>
          {i.why ? <div><span className="ck-k mono">Why it matters</span> {i.why}</div> : null}
          {i.related_assets.length ? <div><span className="ck-k mono">Related assets</span> {i.related_assets.join(" · ")}</div> : null}
          {i.related_stocks.length ? <div><span className="ck-k mono">Related stocks</span> {i.related_stocks.join(" · ")}</div> : null}
          {i.price_confirmation ? <div><span className="ck-k mono">Price confirmation</span> {i.price_confirmation}</div> : null}
          {i.cluster_titles.length ? <div><span className="ck-k mono">Also</span> {i.cluster_titles.map((t, k) => <div key={k} className="ck-cat-also">· {t}</div>)}</div> : null}
          {i.url ? <a className="news-link" href={i.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{i.source || "원문"}</a> : null}
        </div>
      ) : null}
    </div>
  );
}

function CatalystsCard({ c }: { c: Cockpit }) {
  if (!c.catalysts.length) return null;
  const compact = c.catalysts.length <= 3;
  return (
    <Card title="Live Catalysts" area="cat" testid="ck-catalysts" note={`${c.catalysts.length}건 · 중요도 순 · 같은 사건은 묶음 · 클릭해 펼침`}>
      <div className={`ck-cats${compact ? " compact" : ""}`} data-testid="ck-catalyst-list">{c.catalysts.map((i) => <CatalystRow key={i.id} i={i} />)}</div>
    </Card>
  );
}

function EarningsCard({ c }: { c: Cockpit }) {
  if (!c.earnings || !c.earnings.rows.length) return null;
  return (
    <Card title="Earnings Pulse" area="earn" testid="ck-earnings" note={c.earnings.note}>
      <div className="ck-earn">{c.earnings.rows.map((r, k) => <div key={k} className="ck-earn-row mono"><span>{r.name}</span><span>{r.arrow} {r.value}</span></div>)}</div>
    </Card>
  );
}

function NextCard({ c, open, setOpen, onStock }: { c: Cockpit; open: string | null; setOpen: (id: string | null) => void; onStock?: (id: string) => void }) {
  return (
    <Card title="What Matters Next" area="next" testid="ck-next" note="오늘 판단을 바꿀 수 있는 것 · 최대 5">
      <p className="ck-sub" data-testid="ck-next-purpose">현재 시장 판단을 강화하거나 뒤집을 수 있는 다음 핵심 변수를 보여줍니다. 항목을 누르면 그 변화가 자산 → 산업 → 종목으로 어떻게 전파될 수 있는지 볼 수 있습니다.</p>
      <ol className="ck-next">
        {c.what_matters_next.map((n, k) => {
          const isOpen = open === n.id;
          return (
            <li key={n.id || k} id={`ck-next-${n.id}`} data-testid="ck-next-item" data-status={n.status} className={`${n.path ? "has-path" : ""}${isOpen ? " open" : ""}`} onClick={n.path ? () => setOpen(isOpen ? null : n.id) : undefined} role={n.path ? "button" : undefined} tabIndex={n.path ? 0 : undefined} onKeyDown={(e) => { if (n.path && e.key === "Enter") setOpen(isOpen ? null : n.id); }}>
              <div className="ck-nx-h">
                <span className="ck-next-t">{n.text.replace(/가 고점을 갱신하는가$/, "가 다시 상승하는가?").replace(/는가$/, "는가?")}</span>
                <StatusKo s={n.status} />
              </div>
              <div className="ck-nx-cur mono" data-testid="ck-next-horizons">
                <span className="ck-k">Current · {n.metric}</span>
                {n.horizons.length ? n.horizons.map((h) => <span key={h.key} className="ck-nx-hz"><i>{h.key}</i> <b className="num">{h.z === null ? "–" : `${sg(h.z)}σ`}</b> {h.arrow !== "?" ? h.arrow : ""}</span>) : <span className="num">{n.current}</span>}
                {n.horizon_read ? <span className="ck-nx-read">{n.horizon_read}</span> : null}
              </div>
              {n.why_next ? <div className="ck-nx-why"><span className="ck-k mono">Why it matters</span> {n.why_next}</div> : null}
              {n.path && !isOpen ? <span className="ck-nx-open mono">View transmission ›</span> : null}
              {n.path && isOpen ? <IssuePathView p={n.path} status={n.status} current={n.horizons.map((h) => `${h.key} ${h.z === null ? "–" : `${sg(h.z)}σ`}`).join(" / ") || n.current} title={n.text} onStock={onStock} /> : null}
            </li>
          );
        })}
      </ol>
      {c.upcoming.length ? <div className="ck-up mono"><span className="ck-k">Upcoming</span> {c.upcoming.map((u) => `${u.date} ${u.label}${u.days_until !== null ? ` (D${u.days_until >= 0 ? "-" : "+"}${Math.abs(u.days_until)})` : ""}${u.verified ? "" : " (미확인)"}`).join(" · ")}</div> : null}
    </Card>
  );
}

function WatchRowView({ w, views, onIssue, onChain }: { w: CkWatchRow; views: AnalystViews | null; onIssue?: (id: string) => void; onChain?: (key: string) => void }) {
  const [open, setOpen] = useState(false);
  const av = views?.views.find((v) => v.stock_id === w.id);
  const hasMore = !!(w.commentary || av || w.eps_revision !== null);
  return (
    <div className={`ck-wl${open ? " open" : ""}`} data-testid="ck-watch-row" data-priority={w.priority} onClick={hasMore ? () => setOpen(!open) : undefined} role={hasMore ? "button" : undefined} tabIndex={hasMore ? 0 : undefined}>
      <div className="ck-wl-h"><b>{w.name}</b><span className="num mono" style={{ color: w.change_1d === null ? "var(--faint)" : "var(--ink-2)" }}>{sg(w.change_1d, 1, "%")}</span></div>
      {w.theme ? <div className="ck-wl-t mono">{w.theme}{w.priority === "HIGH" ? <em className="ck-wl-pr" title="선정 우선순위 — 점수는 보이지 않는다">HIGH</em> : null}</div> : null}
      <div className="ck-wl-b" data-testid="ck-watch-why"><span className="ck-k mono">Why watch</span><span>{w.why}</span></div>
      {w.key_drivers.length ? <div className="ck-wl-b" data-testid="ck-watch-drivers"><span className="ck-k mono">Key driver</span><span className="mono">{w.key_drivers.join(" · ")}</span></div> : null}
      {w.trigger ? <div className="ck-wl-b" data-testid="ck-watch-trigger"><span className="ck-k mono">Trigger</span><span>{w.trigger}</span></div> : null}
      <div className="ck-wl-tags mono" data-testid="ck-watch-tags">
        {w.reasons.map((r) => <em key={r}>{r}</em>)}
        {w.transmission.map((l) => <button key={l.key} type="button" className="ck-wl-link" title="MARKET → STOCK TRANSMISSION 의 이 체인으로" onClick={(e) => { e.stopPropagation(); onChain?.(l.key); }}>TRANSMISSION ● <span>{l.label}</span></button>)}
        {w.issues.map((l) => <button key={l.key} type="button" className="ck-wl-link" title="WHAT MATTERS NEXT 의 이 이슈로" onClick={(e) => { e.stopPropagation(); onIssue?.(l.key); }}>RELATED ISSUE <span>{l.label}</span></button>)}
        {hasMore ? <span className="ck-nx-open">{open ? "▾" : "›"}</span> : null}
      </div>
      {open ? (
        <div className="ck-wl-x" data-testid="ck-watch-extra" onClick={(e) => e.stopPropagation()}>
          {w.commentary ? <div><span className="ck-k mono">Commentary</span> {w.commentary}</div> : null}
          {w.eps_revision !== null ? <div className="mono"><span className="ck-k">EPS revision 1M</span> {sg(w.eps_revision, 1, "%")}</div> : null}
          {av ? <div><span className="ck-k mono">Analyst view · {av.freshness}</span> {av.analyst} · {av.broker} — {av.summary}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

function WatchCard({ c, views, onIssue, onChain }: { c: Cockpit; views: AnalystViews | null; onIssue?: (id: string) => void; onChain?: (key: string) => void }) {
  if (!c.watchlist.length) return null;
  return (
    <Card title="Watchlist" area="watch" testid="ck-watchlist" note={`${c.watchlist.length}종목 · 오늘 다시 확인할 종목과 기다리는 trigger`}>
      <p className="ck-sub" data-testid="ck-watch-purpose">현재 뉴스·테마·매크로·상대강도·펀더멘털에서 의미 있는 변화가 감지된 종목만 표시합니다. Stock Radar 가 "왜 오늘 움직였는가" 라면 여기는 "다음에 무엇이 나타나면 다시 봐야 하는가" 입니다.</p>
      <div className="ck-watch">{c.watchlist.map((w) => <WatchRowView key={w.id} w={w} views={views} onIssue={onIssue} onChain={onChain} />)}</div>
    </Card>
  );
}

export function CockpitView({ cockpit, snapshot, history, details, scenario, analystViews }: { cockpit: Cockpit; snapshot: IntelligenceSnapshot; history: MarketStateHistory | null; details?: React.ReactNode; scenario?: string; analystViews?: AnalystViews | null }) {
  const [showDetails, setShowDetails] = useState(false);
  const [openIssue, setOpenIssue] = useState<string | null>(null);
  const [focusStock, setFocusStock] = useState<string | null>(null);
  const [focusChain, setFocusChain] = useState<string | null>(null);
  const goChain = (key: string) => { setFocusChain(key); const el = typeof document !== "undefined" ? document.getElementById(`ck-tr-${key}`) : null; el?.scrollIntoView?.({ behavior: "smooth", block: "center" }); };
  // ANALYST VIEW 는 radar 종목만, 비동기 — radar 가 먼저 뜨고 이 층은 나중에 채워진다. 테스트·정적 배포본은 prop 으로 넣을 수 있다.
  const fetched = useAnalystViews(scenario, cockpit.radar.map((r) => r.id), analystViews === undefined);
  const views = analystViews === undefined ? fetched : analystViews;
  const goIssue = (id: string) => { setOpenIssue(id); const el = typeof document !== "undefined" ? document.getElementById(`ck-next-${id}`) : null; el?.scrollIntoView?.({ behavior: "smooth", block: "center" }); };
  const goStock = (id: string) => { setFocusStock(id); const el = typeof document !== "undefined" ? document.getElementById(`ck-rd-${id}`) : null; el?.scrollIntoView?.({ behavior: "smooth", block: "center" }); };
  void snapshot; void history;
  const ds = cockpit.data_status;
  return (
    <div className={`ck${cockpit.history ? " ck-hist" : ""}`} data-testid="cockpit">
      <MarketNow c={cockpit} />
      {cockpit.history ? <RegimeHistoryCard h={cockpit.history} /> : null}
      <Drivers c={cockpit} mobileTop={3} />
      <CrossAssetCard c={cockpit} />
      <LeadershipCard c={cockpit} onStock={goStock} />
      <TransmissionCard c={cockpit} focus={focusChain} />
      <RadarCard c={cockpit} views={views} onIssue={goIssue} focus={focusStock} />
      <CatalystsCard c={cockpit} />
      <EarningsCard c={cockpit} />
      <NextCard c={cockpit} open={openIssue} setOpen={setOpenIssue} onStock={goStock} />
      <WatchCard c={cockpit} views={views} onIssue={goIssue} onChain={goChain} />
      <div className="ck-status mono" style={{ gridArea: "status" }} data-testid="ck-data-status">
        <span className="ck-k">DATA</span> {ds.line}{ds.warnings.map((w) => <span key={w} className="ck-warn">{w}</span>)}
        <button className="ck-more" onClick={() => setShowDetails(!showDetails)} data-testid="ck-details-toggle">{showDetails ? "Details / Diagnostics 닫기" : "Details / Diagnostics 열기"}</button>
      </div>
      {showDetails ? <div className="ck-details" data-testid="ck-details" style={{ gridArea: "details" }}>{details}</div> : null}
    </div>
  );
}
