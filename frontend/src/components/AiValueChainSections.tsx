import type { AiRegime, AiStockImpactRow, AiArrow } from "../api/types";

/**
 * AI 탭 확장 층 — 전파 체인 · 밸류체인 리더십 · 반도체 펀더멘털 확인 · 종목 영향도 · 레이더 · 뉴스→종목 · 기대 vs 펀더멘털 · What Matters Now.
 * 반도체 데이터는 업사이클 판정이 아니라 'Fundamental Confirmation Layer' 다. 단일 점수·추천·확률 없음. 값이 없으면 '?'·N/A 로 남긴다.
 */
const ARROW_COLOR: Record<string, string> = { "↑↑": "var(--up)", "↑": "var(--up)", "→": "var(--muted)", "↓": "var(--down)", "↓↓": "var(--down)", "?": "var(--faint)" };
const STATUS_COLOR: Record<string, string> = {
  ACCELERATING: "var(--up)", STRONG: "var(--up)", LEADING: "var(--up)", POSITIVE: "var(--up)", IMPROVING: "var(--up)", CONFIRMED: "var(--up)", CONFIRMING: "var(--ok)",
  STABLE: "var(--muted)", NEUTRAL: "var(--muted)", WATCH: "var(--warn)", MIXED: "var(--warn)", PARTIAL: "var(--warn)", UNCONFIRMED: "var(--faint)", "N/A": "var(--faint)", "NO DATA": "var(--faint)",
  DETERIORATING: "var(--down)", WEAK: "var(--down)", NEGATIVE: "var(--down)", "NEGATIVE PRESSURE": "var(--down)",
};
const TONE_COLOR: Record<string, string> = { good: "var(--up)", warn: "var(--warn)", bad: "var(--down)", muted: "var(--muted)" };
const sg = (v: number | null, d = 1, unit = "") => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);
const pc = (v: number | null) => (v === null ? "–" : `${v.toFixed(0)}%`);
export const Arrow = ({ a, title }: { a: AiArrow; title?: string }) => <span className="ai-arrow mono" style={{ color: ARROW_COLOR[a] ?? "var(--faint)" }} title={title}>{a}</span>;
const St = ({ s }: { s: string }) => <span className="mono" style={{ color: STATUS_COLOR[s] ?? "var(--muted)" }}>{s}</span>;

/** 1. REGIME 카드 안에 붙는 상태 띠 — ENGLISH CATEGORY / ENGLISH STATUS / 한 줄 한국어 의미 — 그 아래 AI REGIME READ(2~3문장) + KEY TENSION */
export function StatusStrip({ regime }: { regime: AiRegime }) {
  const t = regime.sentiment;
  return (
    <div className="ai-strip-wrap" data-testid="ai-status-strip">
      <div className="ai-strip">
        {regime.status_strip.map((s) => (
          <div key={s.key} className="ai-strip-item" title={s.detail} data-key={s.key}>
            <span className="ai-k mono">{s.label}</span>
            <b className="mono" style={{ color: TONE_COLOR[s.tone] }}>{s.value}</b>
            <span className="ai-strip-m" data-testid="ai-strip-meaning">{s.meaning || s.detail}</span>
          </div>
        ))}
      </div>
      <div className="ai-rread" data-testid="ai-regime-read"><span className="ai-k mono">AI Regime Read</span><p>{regime.regime_read || regime.summary}</p></div>
      {t && t.secondary_key !== "none" ? (
        <div className="ai-tension" data-testid="ai-key-tension"><span className="ai-k mono">Key tension</span><b className="mono">{t.secondary_label}</b><span>{t.secondary_ko}</span></div>
      ) : null}
    </div>
  );
}

/** Details 안으로 내린 장문 — FUNDAMENTAL CONFIRMATION 문장 · SUMMARY · Global market regime 맥락. 지우지 않고 접어 둔다 */
export function RegimeLongText({ regime }: { regime: AiRegime }) {
  const fc = regime.fundamental_confirmation;
  return (
    <div className="ai-longtext" data-testid="ai-regime-longtext">
      <p className="ai-fc" data-testid="ai-fundamental-confirmation"><span className="ai-k mono">FUNDAMENTAL CONFIRMATION</span> <b className="mono" style={{ color: STATUS_COLOR[fc.level] }}>{fc.level}</b> <span>{fc.sentence}</span></p>
      <p className="ai-summary" data-testid="ai-summary"><span className="ai-k mono">SUMMARY</span> {regime.summary}</p>
    </div>
  );
}

/** 4. AI FUNDAMENTAL TRANSMISSION */
export function TransmissionSection({ regime }: { regime: AiRegime }) {
  const t = regime.transmission;
  return (
    <section className="panel span-3" data-testid="ai-transmission">
      <header className="panel-head"><h2 className="panel-title">AI Fundamental Transmission</h2><div className="panel-note mono">AI Narrative → Capex → GPU → HBM → Memory → Foundry/Packaging → Equipment → DC Infra → EPS · 증거 점수 −100…+100</div></header>
      <div className="panel-body">
        <div className="ai-chain">
          {t.stages.map((s, i) => (
            <div key={s.key} className="ai-stage" data-testid="ai-stage" data-status={s.status} title={s.evidence}>
              <span className="ai-stage-l">{s.label}</span>
              <St s={s.status} />
              <span className="num mono ai-stage-s" style={{ color: s.score === null ? "var(--faint)" : s.score >= 0 ? "var(--up)" : "var(--down)" }}>{s.score === null ? "–" : sg(s.score, 0)}</span>
              {i < t.stages.length - 1 ? <span className="ai-stage-arrow" aria-hidden="true">↓</span> : null}
            </div>
          ))}
        </div>
        <p className="ai-sent" data-testid="ai-transmission-sentence">{t.sentence}</p>
      </div>
    </section>
  );
}

/** 5. AI / SEMI / INFRA / SOFTWARE LEADERSHIP — 밸류체인 10 세그먼트 */
export function ValueChainSection({ regime }: { regime: AiRegime }) {
  const v = regime.value_chain; const lab = Object.fromEntries(v.segments.map((s) => [s.key, s.label]));
  const rows = [...v.segments].sort((a, b) => (a.rank_1w ?? 99) - (b.rank_1w ?? 99));
  return (
    <section className="panel span-2" data-testid="ai-value-chain">
      <header className="panel-head"><h2 className="panel-title">AI / Semi / Infra / Software Leadership</h2><div className="panel-note mono">밸류체인 10 세그먼트 · 1D/1W/1M · Nasdaq 대비 상대 · breadth · EPS · 1주 상대 %p 순위</div></header>
      <div className="panel-body">
        <div className="ai-vc" role="table" aria-label="밸류체인 리더십">
          <div className="ai-vc-row ai-th mono"><span>segment</span><span>1D</span><span>1W</span><span>1M</span><span>REL</span><span>&gt;MA20</span><span>EPS</span><span>rank</span></div>
          {rows.map((s) => (
            <div key={s.key} className={`ai-vc-row${s.role === "leading" ? " lead" : s.role === "lagging" ? " lag" : ""}`} role="row" data-testid="ai-segment" data-key={s.key} data-role={s.role} title={`${s.exposure} exposure · ${s.available}/${s.members} 종목 · ${s.eps_note} · 매크로 ${s.macro_score === null ? "–" : sg(s.macro_score)}`}>
              <span className="ai-vc-name">{s.label}<small> {s.label_ko}</small></span>
              <span className="num" data-l="1D" style={{ color: s.ret_1d === null ? "var(--faint)" : s.ret_1d >= 0 ? "var(--up)" : "var(--down)" }}>{sg(s.ret_1d, 1, "%")}</span>
              <span className="num" data-l="1W"><Arrow a={s.arrow_1w} /> {sg(s.ret_5d, 1, "%")}</span>
              <span className="num" data-l="1M" style={{ color: s.ret_21d === null ? "var(--faint)" : s.ret_21d >= 0 ? "var(--up)" : "var(--down)" }}>{sg(s.ret_21d, 1, "%")}</span>
              <span className="num" data-l="REL 1W"><Arrow a={s.arrow_rel} /> {sg(s.rel_5d, 1, "%p")}</span>
              <span className="num" data-l=">MA20" style={{ color: s.above_ma20_pct !== null && s.above_ma20_pct < 50 ? "var(--down)" : "var(--ink-2)" }}>{pc(s.above_ma20_pct)}</span>
              <span className="num" data-l="EPS"><Arrow a={s.arrow_eps} title={s.eps_note} /> {s.eps === null ? "N/A" : sg(s.eps, 1, "%")}</span>
              <span className="mono ai-vc-rank" data-l="rank" style={{ color: s.role === "leading" ? "var(--up)" : s.role === "lagging" ? "var(--down)" : "var(--muted)" }}>{s.rank_1w ? `#${s.rank_1w}` : "–"}</span>
            </div>
          ))}
        </div>
        <div className="ai-lead-lists">
          <div><span className="ai-k mono">CURRENT LEADERSHIP (1W REL)</span><ol className="ai-lead-ol" data-testid="ai-leadership-list">{v.leadership.map((k) => <li key={k}>{lab[k] ?? k}</li>)}</ol></div>
          <div><span className="ai-k mono">LAGGING</span><ul className="ai-lead-ul" data-testid="ai-lagging-list">{v.lagging.length ? v.lagging.map((k) => <li key={k}>{lab[k] ?? k}</li>) : <li className="sv-muted">없음</li>}</ul></div>
        </div>
        <p className="ai-sent">{v.sentence}</p>
      </div>
    </section>
  );
}

/** 6. SEMICONDUCTOR FUNDAMENTAL CONFIRMATION + MEMORY / HBM FUNDAMENTALS */
export function SemiConfirmationSection({ regime }: { regime: AiRegime }) {
  const s = regime.semi_confirmation;
  return (
    <section className="panel" data-testid="ai-semi-confirmation">
      <header className="panel-head"><h2 className="panel-title">Semiconductor Fundamental Confirmation</h2><div className="panel-note mono">AI 내러티브가 반도체 산업으로 전달되는지 — 업사이클 판정 아님</div></header>
      <div className="panel-body">
        <div className="ai-areas" role="table" aria-label="반도체 확인">
          <div className="ai-area ai-th mono"><span>영역</span><span>가격</span><span>상대</span><span>brd</span><span>뉴스</span><span>EPS</span><span>status</span></div>
          {s.areas.map((a) => (
            <div key={a.key} className="ai-area" role="row" data-testid="ai-semi-area" data-status={a.status} title={a.detail}>
              <span className="ai-area-l">{a.label}</span>
              <Arrow a={a.price_momentum} /><Arrow a={a.relative_strength} /><Arrow a={a.breadth} /><Arrow a={a.news_evidence} /><Arrow a={a.eps} />
              <St s={a.status} />
            </div>
          ))}
        </div>
        <p className="ai-sent">{s.sentence}</p>
        <div className="ai-k mono" style={{ marginTop: 10 }}>MEMORY / HBM FUNDAMENTALS <span style={{ color: "var(--faint)" }}>— 확인 데이터. HBM 계약가는 구조적 증거(일간 점수 제외)</span></div>
        <div className="ai-mem-tbl" role="table" aria-label="메모리 펀더멘털">
          <div className="ai-mem-tr ai-th mono"><span>계열</span><span>현재</span><span>1W</span><span>1M</span><span>z</span><span>신선도</span><span>status</span></div>
          {s.memory.map((m) => (
            <div key={m.id} className={`ai-mem-tr${m.status === "N/A" ? " na" : ""}`} role="row" data-testid="ai-memory-row" data-status={m.status} title={m.note}>
              <span className="ai-mem-l">{m.label}{m.structural ? <small className="mono" style={{ color: "var(--faint)" }}> 분기</small> : null}</span>
              <span className="num" data-l="현재">{m.value === null ? "–" : m.value >= 1000 ? m.value.toLocaleString("en-US", { maximumFractionDigits: 0 }) : m.value.toFixed(m.value >= 100 ? 1 : 2)}</span>
              <span className="num" data-l={m.structural ? "앵커 변화" : "1W"} style={{ color: m.change_1w === null ? "var(--faint)" : m.change_1w >= 0 ? "var(--up)" : "var(--down)" }}>{m.structural ? (m.change_1d === null ? "–" : `앵커 ${sg(m.change_1d, 1, "%")}`) : sg(m.change_1w, 1, "%")}</span>
              <span className="num" data-l="1M" style={{ color: m.change_1m === null ? "var(--faint)" : m.change_1m >= 0 ? "var(--up)" : "var(--down)" }}>{m.structural ? "–" : sg(m.change_1m, 1, "%")}</span>
              <span className="num mono" data-l="z" style={{ color: "var(--faint)" }}>{m.z === null ? "N/A" : sg(m.z)}</span>
              <span className="mono" data-l="신선도" style={{ color: (m.freshness_days ?? 0) > 5 && !m.structural ? "var(--warn)" : "var(--faint)" }}>{m.freshness_days === null ? "–" : `${m.freshness_days}D`}{m.observations ? ` · 봉 ${m.observations}` : ""}</span>
              <span data-l="status"><St s={m.status} /></span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/** 9. STOCK IMPACT MAP — 네 축(THEME/FUNDAMENTAL/MARKET/MACRO), 단일 점수 없음 */
export function StockImpactSection({ regime }: { regime: AiRegime }) {
  const rows = regime.stocks.filter((r) => r.available);
  const missing = regime.stocks.filter((r) => !r.available);
  return (
    <section className="panel span-3" data-testid="ai-stock-impact">
      <header className="panel-head"><h2 className="panel-title">AI Stock Impact Map</h2><div className="panel-note mono">{rows.length}종목 · THEME(AI 수요·뉴스) / FUNDAMENTAL(Capex·반도체·EPS) / MARKET(가격·상대·breadth) / MACRO(금리·달러·위험선호) — 추천·목표수익률 아님</div></header>
      <div className="panel-body">
        <div className="ai-sim" role="table" aria-label="종목 영향도">
          <div className="ai-sim-row ai-th mono"><span>종목</span><span>segment</span><span>exposure</span><span>THEME</span><span>FUND</span><span>MKT</span><span>MACRO</span><span>1W rel</span><span>EPS</span><span>overall</span><span>interpretation</span></div>
          {rows.map((r) => <StockRow key={r.id} r={r} />)}
        </div>
        {missing.length ? <div className="ai-ev mono" style={{ marginTop: 6 }}>계열 없음: {missing.map((m) => m.name).join(", ")}</div> : null}
      </div>
    </section>
  );
}
function StockRow({ r }: { r: AiStockImpactRow }) {
  const ax = Object.fromEntries(r.axes.map((a) => [a.key, a]));
  return (
    <div className="ai-sim-row" role="row" data-testid="ai-stock" data-id={r.id} data-overall={r.overall} title={`${r.confirmation} · AI 수요 ${r.ai_demand} · 반도체 ${r.semiconductor} · 상대강도 ${r.relative_strength} · 뉴스 ${r.news_flow} · EPS ${r.eps_revision} · 금리 민감 ${r.rates_sensitivity}`}>
      <span className="ai-sim-name">{r.name}<small className="mono"> {r.id}{r.region !== "US" ? ` · ${r.region}` : ""}</small></span>
      <span className="ai-sim-seg mono">{r.segments.join(" · ")}</span>
      <span className="mono ai-sim-exp" data-l="exposure">{r.theme_exposure}</span>
      {(["theme", "fundamental", "market", "macro"] as const).map((k) => <span key={k} className="ai-sim-ax" data-l={k === "fundamental" ? "FUND" : k === "market" ? "MKT" : k.toUpperCase()}><Arrow a={ax[k]?.arrow ?? "?"} title={ax[k]?.detail} /></span>)}
      <span className="num" data-l="1W rel" style={{ color: r.rel_5d === null ? "var(--faint)" : r.rel_5d >= 0 ? "var(--up)" : "var(--down)" }}>{sg(r.rel_5d, 1, "%p")}</span>
      <span className="mono" data-l="EPS" style={{ color: r.eps_revision === "N/A" ? "var(--faint)" : "var(--ink-2)" }}>{r.eps_revision}</span>
      <span className="ai-sim-ov" data-l="overall"><St s={r.overall} /></span>
      <span className="ai-sim-int">{r.interpretation}</span>
    </div>
  );
}

/** 10. STOCK RADAR — 의미 있는 변화가 있는 종목만, 이유와 함께 */
export function RadarSection({ regime }: { regime: AiRegime }) {
  return (
    <section className="panel span-2" data-testid="ai-radar">
      <header className="panel-head"><h2 className="panel-title">Stock Radar</h2><div className="panel-note mono">자동 추출 · 버킷당 최대 4 · 이유 없는 나열 없음</div></header>
      <div className="panel-body ai-radar">
        {regime.radar.map((b) => (
          <div key={b.key} className="ai-radar-b" data-testid="ai-radar-bucket" data-key={b.key}>
            <span className="ai-k mono">{b.label}</span>
            {b.items.length ? b.items.map((i) => <div key={i.id} className="ai-radar-i" data-testid="ai-radar-item"><b>{i.name}</b><span className="mono ai-radar-r">{i.reason}</span></div>) : <div className="sv-muted">해당 없음</div>}
          </div>
        ))}
      </div>
    </section>
  );
}

/** 11. NEWS → INDUSTRY DRIVER → VALUE CHAIN → STOCK */
export function NewsImpactSection({ regime }: { regime: AiRegime }) {
  return (
    <section className="panel" data-testid="ai-news-impact">
      <header className="panel-head"><h2 className="panel-title">News → Value Chain → Stock</h2><div className="panel-note mono">AI 기사 상위 {regime.news_impact.length} · 뉴스만으로 판단하지 않는다</div></header>
      <div className="panel-body ai-ni">
        {regime.news_impact.length === 0 ? <div className="sv-muted">AI 기사가 없다.</div> : regime.news_impact.map((n, i) => (
          <div key={i} className="ai-ni-row" data-testid="ai-news-row">
            <div className="ai-ni-head"><span className="num mono" style={{ color: n.tone >= 0 ? "var(--up)" : "var(--down)" }}>{sg(n.tone, 0)}</span>{n.url ? <a className="news-link" href={n.url} target="_blank" rel="noreferrer">{n.event}</a> : <span>{n.event}</span>}</div>
            <div className="ai-ni-chain mono">
              <span>{n.drivers.length ? n.drivers.join(" · ") : "driver 미분류"}</span>
              {n.primary.length ? <><span className="ai-ni-arrow">→</span><span>1차 {n.primary.join(", ")} <b>{n.primary_stocks.join(" / ")}</b></span></> : null}
              {n.secondary.length ? <><span className="ai-ni-arrow">→</span><span>2차 {n.secondary.join(", ")} <b>{n.secondary_stocks.join(" / ")}</b></span></> : null}
              {n.infrastructure.length ? <><span className="ai-ni-arrow">→</span><span>인프라 {n.infrastructure.join(", ")} <b>{n.infrastructure_stocks.join(" / ")}</b></span></> : null}
            </div>
            <div className="mono ai-ni-conf" style={{ color: n.confirmation.startsWith("CONFIRMED —") ? "var(--up)" : n.confirmation.startsWith("CONFIRMED NEGATIVE") ? "var(--down)" : "var(--warn)" }}>{n.confirmation}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/** 12. EXPECTATIONS vs FUNDAMENTALS */
export function GapSection({ regime }: { regime: AiRegime }) {
  const rows = [...regime.expectation_gap].sort((a, b) => (b.gap ?? -999) - (a.gap ?? -999));
  return (
    <section className="panel span-3" data-testid="ai-gap">
      <header className="panel-head"><h2 className="panel-title">Expectations vs Fundamentals</h2><div className="panel-note mono">세그먼트별 0~100 · Market Pricing(상대 z·1개월·breadth) vs Fundamental(driver 톤·메모리 데이터·EPS) · 매수/매도 신호 아님 — 추가 검토 우선순위</div></header>
      <div className="panel-body">
        <div className="ai-gap-grid">
          {rows.map((g) => (
            <div key={g.key} className="ai-gap-row" data-testid="ai-gap-row" title={g.note}>
              <span className="ai-gap-l">{g.label}</span>
              <span className="ai-gap-bars">
                {/* 어느 줄이 시장 기대(가격 반영)이고 어느 줄이 펀더멘털인지 줄마다 이름·숫자를 붙인다 */}
                <span className="ai-gap-line" data-k="market" title="Market Pricing — 상대 z · 1개월 수익 · breadth 로 만든 0~100">
                  <em className="mono" style={{ color: "var(--accent)" }}>시장 기대</em>
                  <i className="ai-gap-bar"><b style={{ width: `${g.market_pricing ?? 0}%`, background: "var(--accent)" }} /></i>
                  <b className="num mono" style={{ color: "var(--accent)" }}>{g.market_pricing === null ? "–" : g.market_pricing.toFixed(0)}</b>
                </span>
                <span className="ai-gap-line" data-k="fund" title="Fundamental — driver 뉴스 톤 · 메모리 데이터 · EPS 로 만든 0~100">
                  <em className="mono" style={{ color: "var(--muted)" }}>펀더멘털</em>
                  <i className="ai-gap-bar"><b style={{ width: `${g.fundamental ?? 0}%`, background: "var(--muted)" }} /></i>
                  <b className="num mono" style={{ color: "var(--ink-2)" }}>{g.fundamental === null ? "–" : g.fundamental.toFixed(0)}</b>
                </span>
              </span>
              <span className="num mono ai-gap-g" style={{ color: g.gap === null ? "var(--faint)" : g.gap >= 15 ? "var(--warn)" : g.gap <= -15 ? "var(--info)" : "var(--muted)" }}><small>gap</small> {g.gap === null ? "–" : sg(g.gap, 0)}</span>
              <span className="ai-gap-n">{g.note}</span>
            </div>
          ))}
        </div>
        <div className="ai-ev mono" style={{ marginTop: 6 }}><span style={{ color: "var(--accent)" }}>■</span> 시장 기대 = Market Pricing(가격: 상대 z · 1개월 · breadth) <span style={{ color: "var(--muted)" }}>■</span> 펀더멘털 = Fundamental(뉴스 driver 톤 · 메모리 데이터 · EPS) · gap = 시장 기대 − 펀더멘털, + 는 기대가 앞섬, − 는 가격 반영이 제한적</div>
      </div>
    </section>
  );
}

/** 15. WHAT MATTERS NOW */
export function WhatMattersSection({ regime }: { regime: AiRegime }) {
  return (
    <section className="panel span-3" data-testid="ai-what-matters">
      <header className="panel-head"><h2 className="panel-title">What Matters Now</h2><div className="panel-note mono">지금 AI 판단에 가장 중요한 변수 · 최대 5 · 자동 선정</div></header>
      <div className="panel-body">
        <ol className="ai-wm">
          {regime.what_matters.map((m) => (
            <li key={m.key} data-testid="ai-matters-item" data-status={m.status}>
              <span className="ai-wm-t">{m.text}</span>
              <span className="mono ai-wm-s"><St s={m.status} /> <span style={{ color: "var(--faint)" }}>· {m.metric} 지금 <b className="num">{m.current}</b> · {m.detail}</span></span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/** DETAILS / DATA QUALITY 안의 데이터 품질 요약 */
export function DataQualityBlock({ regime }: { regime: AiRegime }) {
  const na = regime.semi_confirmation.memory.filter((m) => m.status === "N/A");
  const epsNa = regime.stocks.filter((r) => r.eps_revision === "N/A").length;
  return (
    <div data-testid="ai-data-quality">
      <div className="ai-k mono">데이터 품질</div>
      <div className="ai-ev mono">
        바스켓 계열 {regime.ai_vs_market.members_used}/{regime.ai_vs_market.members_total} · 종목 영향도 {regime.stocks.filter((r) => r.available).length}/{regime.stocks.length} 종목 계열 확보 · EPS 컨센서스 없음 {epsNa}/{regime.stocks.length} 종목(공개 API 없음 — data/replay/analyst CSV)
        {na.length ? ` · 메모리 데이터 변화율 없음: ${na.map((m) => `${m.label}(봉 ${m.observations})`).join(", ")}` : ""}
        {regime.missing.length ? ` · ${regime.missing.join(" · ")}` : ""}
      </div>
    </div>
  );
}
