import { useState } from "react";
import type { AiRegime, AiStockSignal, AiRadarItem, AiNewsCard } from "../api/types";
import { StockImpactSection } from "./AiValueChainSections";

/**
 * AI 센티2 — STOCK IMPACT MAP(무엇이 특이한가) · STOCK RADAR(무엇을 다시 봐야 하나) · NEWS → VALUE CHAIN → STOCK(뉴스가 어디까지 번지나).
 * 기본 화면 = 스캔(핵심만), 클릭 = 분석. 숫자·문장은 서버(config/ai_regime.yaml stock_view)가 만든다. 계산은 바꾸지 않았다.
 */
const LABEL_COLOR: Record<string, string> = {
  CONFIRMED: "var(--up)", "RELATIVE BREAKOUT": "var(--up)", "MACRO RESILIENT": "var(--ok)", "PRICE LEADING": "var(--info)", "PRICE > NEWS": "var(--info)",
  "FUNDAMENTAL LEADING": "var(--accent)", "NEWS > PRICE": "var(--warn)", DIVERGENCE: "var(--warn)", "RELATIVE BREAKDOWN": "var(--down)", "MACRO SENSITIVE": "var(--down)", "IN LINE": "var(--faint)",
};
const ST_COLOR: Record<string, string> = { CONFIRMED: "var(--up)", STRONG: "var(--up)", IMPROVING: "var(--up)", PARTIAL: "var(--warn)", MIXED: "var(--warn)", WEAK: "var(--down)", "N/A": "var(--faint)", HEADWIND: "var(--down)", TAILWIND: "var(--up)", NEUTRAL: "var(--muted)" };
const REACT_COLOR: Record<string, string> = { CONFIRMED: "var(--up)", "CONFIRMED NEGATIVE": "var(--down)", "NOT PRICED": "var(--warn)", RESILIENT: "var(--ok)", UNCLEAR: "var(--faint)" };
const sg = (v: number | null, d = 1, unit = "") => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);
const St = ({ s }: { s: string }) => <b className="mono sv-st" style={{ color: ST_COLOR[s] ?? "var(--muted)" }}>{s}</b>;

/* ── 1. AI STOCK IMPACT MAP ─────────────────────────────── */
function SignalRow({ s }: { s: AiStockSignal }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`sv-row${open ? " open" : ""}`} data-testid="ai-stock-signal" data-id={s.id} data-label={s.label} onClick={() => setOpen((o) => !o)} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") setOpen((o) => !o); }} aria-expanded={open}>
      <div className="sv-head">
        <span className="sv-name">{s.name}<small>{s.segment}{s.region !== "US" ? ` · ${s.region}` : ""}</small></span>
        <span className="num mono sv-ret" style={{ color: s.ret_5d === null ? "var(--faint)" : s.ret_5d >= 0 ? "var(--up)" : "var(--down)" }}>{sg(s.ret_5d, 1, "%")}<small>1W</small></span>
        <span className="mono sv-open">{open ? "▾" : "›"}</span>
      </div>
      <div className="sv-sig"><b className="mono" style={{ color: LABEL_COLOR[s.label] ?? "var(--muted)" }} data-testid="ai-stock-label" title={s.label_ko}>{s.label}</b><span className="mono">{s.signal}{s.signal_value ? ` · ${s.signal_value}` : ""}</span></div>
      <p className="sv-read" data-testid="ai-stock-read">{s.read}</p>
      <div className="sv-kv mono"><span><i>Fundamental</i><St s={s.fundamental} /></span><span><i>Macro</i><St s={s.macro} /></span>{s.tension ? <span className="sv-tension"><i>Key tension</i><b>{s.tension}</b></span> : null}{s.news ? <span><i>News</i><b>{s.news}</b></span> : null}</div>
      {open ? (
        <div className="sv-more" data-testid="ai-stock-more" onClick={(e) => e.stopPropagation()}>
          <div className="sv-sec"><span className="ai-k mono">What changed</span><p>{s.what_changed}</p></div>
          <div className="sv-sec"><span className="ai-k mono">Price / Relative</span><p className="mono">{s.price_relative}</p></div>
          <div className="sv-sec"><span className="ai-k mono">Fundamentals</span><p className="mono">{s.fundamentals}</p></div>
          <div className="sv-sec"><span className="ai-k mono">News &amp; Sentiment</span><p className="mono">{s.news_sentiment}</p></div>
          <div className="sv-sec"><span className="ai-k mono">Macro exposure</span><p className="mono">{s.macro_exposure}</p></div>
          <div className="sv-sec"><span className="ai-k mono">System read</span><p>{s.read} {s.label_ko}.</p></div>
          {s.watch.length ? <div className="sv-sec"><span className="ai-k mono">What to watch</span><ol className="sv-watch">{s.watch.map((w, i) => <li key={i}>{w}</li>)}</ol></div> : null}
        </div>
      ) : null}
    </div>
  );
}

export function StockImpactSection2({ regime }: { regime: AiRegime }) {
  const v = regime.stock_view; const [all, setAll] = useState(false);
  return (
    <section className="panel span-3 sv" data-testid="ai-stock-impact">
      <header className="panel-head"><h2 className="panel-title">AI Stock Impact Map</h2><div className="panel-note mono">{v.impact_subtitle} · TOP STOCK SIGNALS {v.signals.length} / {v.all_signals.length}</div></header>
      <div className="panel-body">
        <div className="sv-grid" data-testid="ai-stock-signals">{v.signals.map((s) => <SignalRow key={s.id} s={s} />)}</div>
        <div className="sv-legend mono" data-testid="ai-stock-legend">{Object.entries(v.label_legend).filter(([k]) => k !== "IN LINE").map(([k, ko]) => <span key={k}><b style={{ color: LABEL_COLOR[k] }}>{k}</b> {ko}</span>)}</div>
        <div className="ai-ev mono" style={{ marginTop: 4 }}>{v.note}</div>
        <button type="button" className="ck-more" onClick={() => setAll((x) => !x)} data-testid="ai-stock-view-all">{all ? "접기" : `View all ${v.all_signals.length} · 네 축 전체 표`}</button>
        {all ? <div className="sv-detail"><StockImpactSection regime={regime} /></div> : null}
      </div>
    </section>
  );
}

/* ── 2. STOCK RADAR ─────────────────────────────────────── */
function RadarRow({ it, bucket }: { it: AiRadarItem; bucket: string }) {
  return (
    <div className="sv-rd" data-testid="ai-radar-item" data-bucket={bucket} data-id={it.id} title={it.detail}>
      <div className="sv-rd-h"><b>{it.name}</b><small>{it.segment}</small></div>
      <div className="sv-rd-m mono"><span><i>Relative</i><b style={{ color: it.relative.startsWith("-") ? "var(--down)" : it.relative === "–" ? "var(--faint)" : "var(--up)" }}>{it.relative}</b></span><span><i>Price</i><St s={it.price} /></span><span><i>Fundamental</i><St s={it.fundamental} /></span></div>
      <div className="sv-rd-w"><span className="ai-k mono">Why watch</span><span data-testid="ai-radar-why">{it.why_watch}</span></div>
    </div>
  );
}

export function RadarSection2({ regime }: { regime: AiRegime }) {
  const v = regime.stock_view; const [all, setAll] = useState(false);
  const total = v.radar.reduce((n, b) => n + b.items.length, 0);
  return (
    <section className="panel span-2 sv" data-testid="ai-radar">
      <header className="panel-head"><h2 className="panel-title">Stock Radar</h2><div className="panel-note mono">{v.radar_subtitle}</div></header>
      <div className="panel-body">
        <div className="sv-rd-grid">
          {v.radar.map((b) => (
            <div key={b.key} className="sv-rd-b" data-testid="ai-radar-bucket" data-key={b.key}>
              <span className="ai-k mono">{b.label}</span><span className="sv-rd-desc">{b.desc}</span>
              {b.items.length ? (all ? b.items : b.items.slice(0, v.radar_default)).map((it) => <RadarRow key={it.id} it={it} bucket={b.key} />) : <div className="sv-muted">해당 없음</div>}
              {!all && b.items.length > v.radar_default ? <span className="sv-more-n mono">+{b.items.length - v.radar_default}</span> : null}
            </div>
          ))}
        </div>
        {total > v.radar.length * v.radar_default ? <button type="button" className="ck-more" onClick={() => setAll((x) => !x)} data-testid="ai-radar-view-all">{all ? "접기" : `View all ${total}`}</button> : null}
      </div>
    </section>
  );
}

/* ── 3. NEWS → VALUE CHAIN → STOCK ──────────────────────── */
function NewsRow({ n, compact }: { n: AiNewsCard; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`sv-nw${compact ? " compact" : ""}${open ? " open" : ""}`} data-testid="ai-news-card" data-reaction={n.reaction} onClick={() => setOpen((o) => !o)} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") setOpen((o) => !o); }} aria-expanded={open}>
      <div className="sv-nw-h">
        <span className="num mono sv-nw-t" style={{ color: n.tone >= 10 ? "var(--up)" : n.tone <= -10 ? "var(--down)" : "var(--muted)" }}>{sg(n.tone, 0)}<small>{n.impact}</small></span>
        <span className="sv-nw-e">{n.event}{n.cluster_size > 1 ? <small className="mono"> ×{n.cluster_size}</small> : null}<small className="mono sv-nw-c">{n.category}</small></span>
        <span className="mono sv-open">{open ? "▾" : "›"}</span>
      </div>
      {!compact || open ? (
        <div className="sv-nw-kv mono">
          <span><i>Primary impact</i><b>{n.primary.length ? n.primary.join(" / ") : "–"}</b></span>
          <span><i>Key stocks</i><b>{n.key_stocks.length ? n.key_stocks.join(" · ") : "–"}</b></span>
          <span><i>Price reaction</i><b style={{ color: REACT_COLOR[n.reaction] ?? "var(--muted)" }} data-testid="ai-news-reaction">{n.reaction}</b><em>{n.reaction_ko}</em></span>
        </div>
      ) : <div className="sv-nw-kv mono"><span><i>Primary</i><b>{n.primary[0] ?? "–"}</b></span><span><i>Reaction</i><b style={{ color: REACT_COLOR[n.reaction] ?? "var(--muted)" }}>{n.reaction}</b></span></div>}
      {open ? (
        <div className="sv-more" data-testid="ai-news-more" onClick={(e) => e.stopPropagation()}>
          <div className="sv-sec"><span className="ai-k mono">Why it matters</span><p>{n.why}</p></div>
          <div className="sv-nw-chain mono">
            <span><i>Primary</i>{n.primary.length ? n.primary.join(" / ") : "–"}</span>
            <span><i>Secondary</i>{n.secondary.length ? n.secondary.join(" / ") : "–"}</span>
            <span><i>Tertiary</i>{n.tertiary.length ? n.tertiary.join(" / ") : "–"}</span>
          </div>
          <div className="sv-sec"><span className="ai-k mono">Key stocks</span><p className="mono">{n.all_stocks.length ? n.all_stocks.join(" · ") : "–"}</p></div>
          <div className="sv-sec"><span className="ai-k mono">Current price reaction</span><p><b className="mono" style={{ color: REACT_COLOR[n.reaction] }}>{n.reaction}</b> · {n.reaction_ko}</p></div>
          <div className="sv-sec"><span className="ai-k mono">System read</span><p>{n.reaction_read}</p></div>
          <div className="sv-sec"><span className="ai-k mono">Source</span><p className="mono">{n.url ? <a className="news-link" href={n.url} target="_blank" rel="noreferrer">{n.source} ↗</a> : n.source}</p></div>
        </div>
      ) : null}
    </div>
  );
}

export function NewsSection2({ regime }: { regime: AiRegime }) {
  const v = regime.stock_view; const [more, setMore] = useState(false);
  const others = more ? v.news_others : v.news_others.slice(0, v.news_others_default);
  return (
    <section className="panel sv" data-testid="ai-news-impact">
      <header className="panel-head"><h2 className="panel-title">News → Value Chain → Stock</h2><div className="panel-note mono">{v.news_subtitle}</div></header>
      <div className="panel-body">
        <div className="sv-nw-legend mono" data-testid="ai-news-legend"><span className="ai-k">News impact</span><span><b>−100</b> {v.news_legend.neg}</span><span><b>0</b> {v.news_legend.zero}</span><span><b>+100</b> {v.news_legend.pos}</span><em>{v.news_legend.note}</em></div>
        {v.news_top.length === 0 && v.news_others.length === 0 ? <div className="sv-muted">AI 기사가 없다.</div> : (<>
          <span className="ai-k mono sv-nw-k">Top impact</span>
          <div className="sv-nw-list" data-testid="ai-news-top">{v.news_top.map((n, i) => <NewsRow key={i} n={n} />)}</div>
          {v.news_others.length ? (<>
            <span className="ai-k mono sv-nw-k">Other relevant</span>
            <div className="sv-nw-list" data-testid="ai-news-others">{others.map((n, i) => <NewsRow key={i} n={n} compact />)}</div>
            {v.news_others.length > v.news_others_default ? <button type="button" className="ck-more" onClick={() => setMore((x) => !x)} data-testid="ai-news-view-more">{more ? "접기" : `View more · ${v.news_others.length - v.news_others_default}`}</button> : null}
          </>) : null}
        </>)}
        <div className="sv-nw-rel mono" data-testid="ai-news-relation">NEWS + / PRICE + <b style={{ color: REACT_COLOR.CONFIRMED }}>CONFIRMED</b> · NEWS − / PRICE − <b style={{ color: REACT_COLOR["CONFIRMED NEGATIVE"] }}>CONFIRMED NEGATIVE</b> · NEWS + / PRICE − <b style={{ color: REACT_COLOR["NOT PRICED"] }}>NOT PRICED</b> · NEWS − / PRICE + <b style={{ color: REACT_COLOR.RESILIENT }}>RESILIENT</b></div>
      </div>
    </section>
  );
}
