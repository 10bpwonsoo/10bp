import { useState } from "react";
import type { Cockpit, CkArrow, CkDriver, CkCatalyst, IntelligenceSnapshot, MarketStateHistory } from "../api/types";
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

function CrossAssetCard({ c }: { c: Cockpit }) {
  const ca = c.cross_asset; const [all, setAll] = useState(false);
  return (
    <Card title="Cross-Asset Confirmation" area="cross" testid="ck-cross" note={<span>Regime Confirmation <b style={{ color: "var(--ink)" }}>{ca.confirm} / {ca.evaluated}</b> assets</span>}>
      <div className="ck-ca" role="table" aria-label="크로스에셋 확인">
        {ca.rows.map((r) => (
          <div key={r.key} className="ck-ca-row" role="row" data-testid="ck-ca-row" data-status={r.status} title={`${r.instrument} ${sg(r.z)}σ · ${r.note}`}>
            <span className="ck-ca-k mono">{r.key}</span><Arrow a={r.arrow} /><St s={r.status} />
          </div>
        ))}
      </div>
      {ca.divergences.length ? (
        <div className="ck-div" data-testid="ck-divergences">
          <span className="ck-k mono">Key Divergence</span>
          {ca.divergences.map((d) => <div key={d.title} className="ck-div-row"><b>{d.title}</b><span className="ck-div-m">→ {d.meaning}</span></div>)}
          {ca.total_divergences > ca.divergences.length ? <button className="ck-more" onClick={() => setAll(!all)}>{all ? "접기" : `View all (${ca.total_divergences})`}</button> : null}
          {all ? <div className="ck-ev mono">전체 괴리 목록은 아래 Details / Diagnostics 의 Divergence 패널에 있다.</div> : null}
        </div>
      ) : null}
    </Card>
  );
}

function LeadershipCard({ c }: { c: Cockpit }) {
  const l = c.leadership; const [pulseOpen, setPulseOpen] = useState(false);
  const Row = ({ r }: { r: (typeof l.leaders)[number] }) => (
    <div className="ck-lead-row" data-testid="ck-lead-row" title={`${r.kind} · ${r.available}/${r.instruments} 계열`}>
      <span className="ck-lead-l">{r.label}</span><Arrow a={r.arrow} />
      <span className="mono ck-lead-v">{sg(r.z_1d)}σ <small>1D</small> | vs market {sg(r.rel_1w)}σ | breadth {r.breadth === null ? "–" : `${r.breadth.toFixed(0)}%`}</span>
    </div>
  );
  return (
    <Card title="Market Leadership" area="lead" testid="ck-leadership" note="1D z · 1주 상대(vs S&P) · breadth(20일선 위)">
      <div className="ck-lead-cols">
        <div><span className="ck-k mono">Leaders</span>{l.leaders.length ? l.leaders.map((r) => <Row key={r.key} r={r} />) : <div className="sv-muted">문턱을 넘는 리더 없음</div>}</div>
        <div><span className="ck-k mono">Laggards</span>{l.laggards.length ? l.laggards.map((r) => <Row key={r.key} r={r} />) : <div className="sv-muted">문턱을 넘는 후미 없음</div>}</div>
      </div>
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

function TransmissionCard({ c }: { c: Cockpit }) {
  if (!c.transmission.length) return null;
  return (
    <Card title="Market → Stock Transmission" area="trans" testid="ck-transmission" note="DRIVER → INDUSTRY / THEME → STOCK · 가격 확인 붙임">
      <div className="ck-trans">
        {c.transmission.map((t) => (
          <div key={t.driver_key} className="ck-tr" data-testid="ck-chain">
            <div className="ck-tr-d"><b>{t.driver_label}</b></div>
            <div className="ck-tr-m mono">→ {t.mechanism}{t.industries.length ? <span className="ck-tr-i"> · {t.industries.join(" · ")}</span> : null}</div>
            <div className="ck-tr-s">
              {t.stocks.map((s) => <span key={s.id} className="ck-tr-stock" title={s.note}><span>{s.name}</span><St s={s.status} /></span>)}
              <span className="mono ck-tr-n">{t.confirmed}/{t.stocks.length} confirmed</span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function RadarCard({ c }: { c: Cockpit }) {
  if (!c.radar.length) return null;
  return (
    <Card title="Stock Radar" area="radar" testid="ck-radar" note={`${c.radar.length}종목 · 이상 거동·뉴스·테마·펀더멘털·상대강도·매크로 종합 — 수익률 순 아님`}>
      <div className="ck-radar">
        {c.radar.map((r) => (
          <div key={r.id} className="ck-rd" data-testid="ck-radar-stock" title={r.signals.join(" · ")}>
            <div className="ck-rd-h"><b>{r.name}</b><span className="num mono" style={{ color: r.change_1d === null ? "var(--faint)" : "var(--ink-2)" }}>{sg(r.change_1d, 1, "%")}</span></div>
            <div className="ck-rd-t mono">{r.tag}</div>
            <div className="ck-rd-w"><span className="ck-k mono">{r.kind === "watch" ? "Watch" : "Why"}</span> {r.why}</div>
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

function NextCard({ c }: { c: Cockpit }) {
  return (
    <Card title="What Matters Next" area="next" testid="ck-next" note="오늘 판단을 바꿀 수 있는 것 · 최대 5">
      <ol className="ck-next">
        {c.what_matters_next.map((n, k) => <li key={k} data-testid="ck-next-item" data-status={n.status}><span className="ck-next-t">{n.text}</span><span className="mono ck-next-s"><St s={n.status} /> <span style={{ color: "var(--faint)" }}>· {n.metric} {n.current}</span></span></li>)}
      </ol>
      {c.upcoming.length ? <div className="ck-up mono"><span className="ck-k">Upcoming</span> {c.upcoming.map((u) => `${u.date} ${u.label}${u.days_until !== null ? ` (D${u.days_until >= 0 ? "-" : "+"}${Math.abs(u.days_until)})` : ""}${u.verified ? "" : " (미확인)"}`).join(" · ")}</div> : null}
    </Card>
  );
}

function WatchCard({ c }: { c: Cockpit }) {
  if (!c.watchlist.length) return null;
  return (
    <Card title="Watchlist" area="watch" testid="ck-watchlist" note={`${c.watchlist.length}종목 · 변화가 있는 종목만 표식`}>
      <div className="ck-watch">
        {c.watchlist.map((w) => <div key={w.id} className="ck-watch-row"><span>{w.name}</span><span className="num mono">{sg(w.change_1d, 1, "%")}</span><span className="mono ck-watch-w">{w.watch ? `Watch: ${w.watch}` : ""}</span><span className="ck-watch-i mono">{w.indicators.map((i) => <em key={i}>{i}</em>)}</span></div>)}
      </div>
    </Card>
  );
}

export function CockpitView({ cockpit, snapshot, history, details }: { cockpit: Cockpit; snapshot: IntelligenceSnapshot; history: MarketStateHistory | null; details?: React.ReactNode }) {
  const [showDetails, setShowDetails] = useState(false);
  void snapshot; void history;
  const ds = cockpit.data_status;
  return (
    <div className={`ck${cockpit.history ? " ck-hist" : ""}`} data-testid="cockpit">
      <MarketNow c={cockpit} />
      {cockpit.history ? <RegimeHistoryCard h={cockpit.history} /> : null}
      <Drivers c={cockpit} mobileTop={3} />
      <CrossAssetCard c={cockpit} />
      <LeadershipCard c={cockpit} />
      <TransmissionCard c={cockpit} />
      <RadarCard c={cockpit} />
      <CatalystsCard c={cockpit} />
      <EarningsCard c={cockpit} />
      <NextCard c={cockpit} />
      <WatchCard c={cockpit} />
      <div className="ck-status mono" style={{ gridArea: "status" }} data-testid="ck-data-status">
        <span className="ck-k">DATA</span> {ds.line}{ds.warnings.map((w) => <span key={w} className="ck-warn">{w}</span>)}
        <button className="ck-more" onClick={() => setShowDetails(!showDetails)} data-testid="ck-details-toggle">{showDetails ? "Details / Diagnostics 닫기" : "Details / Diagnostics 열기"}</button>
      </div>
      {showDetails ? <div className="ck-details" data-testid="ck-details" style={{ gridArea: "details" }}>{details}</div> : null}
    </div>
  );
}
