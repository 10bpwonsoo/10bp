import { useState } from "react";
import type { CkMarketTone, CkToneComponent } from "../api/types";

/**
 * MARKET TONE SNAPSHOT (2026-10-07) — 실시간 2 의 MARKET REGIME HISTORY 와 TODAY'S MARKET DRIVERS 사이.
 * "현재 시장이 왜 이 regime 에 있는지, 가격·뉴스·주요 risk factor 가 어떤 방향인지" 를 5초 안에. 실시간 탭 온도계와 같은 source — 화면은 숫자를 만들지 않는다.
 * 데스크톱: 왼쪽 tone·1W·가격 vs 뉴스·compact 눈금 / 오른쪽 재료·REGIME CONFIRMATION / 아래 MARKET TONE READ. 모바일은 한 열.
 */
const STATE_COLOR: Record<string, string> = { STRONG_RISK_ON: "var(--lbl-risk-on)", RISK_ON: "var(--lbl-risk-on)", NEUTRAL: "var(--lbl-neutral)", RISK_OFF: "var(--lbl-risk-off)", STRONG_RISK_OFF: "var(--lbl-risk-off)", UNKNOWN: "var(--faint)" };
const CONF_COLOR: Record<string, string> = { CONFIRMED: "var(--ok)", PARTIAL: "var(--warn)", DIVERGING: "var(--crit)", UNKNOWN: "var(--faint)" };
const CONF_KO: Record<string, string> = { CONFIRMED: "일치", PARTIAL: "부분 확인", DIVERGING: "불일치", UNKNOWN: "확인 불가" };
const sg = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}`);
const stateColor = (v: number | null) => (v === null ? "var(--faint)" : v >= 10 ? "var(--up)" : v <= -10 ? "var(--down)" : "var(--muted)");

/** compact 눈금: RISK-OFF −100 … 0 … +100 RISK-ON, 종합(큰 점) + P/N(작은 점) */
function Scale({ t }: { t: CkMarketTone }) {
  const W = 320, H = 52, L = 8, Rr = 8;
  const x = (v: number) => L + ((Math.max(-100, Math.min(100, v)) + 100) / 200) * (W - L - Rr);
  const xp = t.price === null ? null : x(t.price), xn = t.news === null ? null : x(t.news);
  const close = xp !== null && xn !== null && Math.abs(xp - xn) < 36;
  const pLeft = xp !== null && xn !== null && xp <= xn; // 가까우면 왼쪽 점은 왼쪽으로, 오른쪽 점은 오른쪽으로 라벨을 민다
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-scale" role="img" aria-label={`market tone ${sg(t.composite)} · price ${sg(t.price)} · news ${sg(t.news)}`} data-testid="ck-tone-scale">
      <text x={L} y={9} className="mt-sc-lbl">RISK-OFF −100</text><text x={W / 2} y={9} className="mt-sc-lbl" textAnchor="middle">NEUTRAL 0</text><text x={W - Rr} y={9} className="mt-sc-lbl" textAnchor="end">RISK-ON +100</text>
      <line x1={L} x2={W - Rr} y1={22} y2={22} className="mt-sc-line" />
      <line x1={x(-20)} x2={x(-20)} y1={18} y2={26} className="mt-sc-tick" /><line x1={x(20)} x2={x(20)} y1={18} y2={26} className="mt-sc-tick" /><line x1={x(0)} x2={x(0)} y1={15} y2={29} className="mt-sc-zero" />
      {xp !== null ? <g data-testid="ck-tone-p"><circle cx={xp} cy={22} r={3} className="mt-sc-sub" /><text x={close ? (pLeft ? xp - 5 : xp + 5) : xp} y={48} className="mt-sc-sub-lbl" textAnchor={close ? (pLeft ? "end" : "start") : "middle"}>P {sg(t.price)}</text></g> : null}
      {xn !== null ? <g data-testid="ck-tone-n"><circle cx={xn} cy={22} r={3} className="mt-sc-sub mt-sc-news" /><text x={close ? (pLeft ? xn + 5 : xn - 5) : xn} y={48} className="mt-sc-sub-lbl" textAnchor={close ? (pLeft ? "start" : "end") : "middle"}>N {sg(t.news)}</text></g> : null}
      {t.composite !== null ? <g data-testid="ck-tone-c"><circle cx={x(t.composite)} cy={22} r={6} fill={STATE_COLOR[t.state] ?? "var(--ink)"} className="mt-sc-main" /><text x={x(t.composite)} y={37} className="mt-sc-main-lbl" textAnchor="middle">{sg(t.composite)}</text></g> : null}
    </svg>
  );
}

function Row({ c }: { c: CkToneComponent }) {
  return (
    <div className="mt-row" data-testid="ck-tone-comp" data-key={c.key} title={c.week_ago !== null ? `1주 전 ${sg(c.week_ago)} → 지금 ${sg(c.value)} (${sg(c.change_1w)})` : c.value === null ? "데이터 없음 — 0 으로 채우지 않았다" : "1주 전 값 없음"}>
      <span className="mt-row-l">{c.label}</span>
      <b className={`num mt-row-v${c.value === null ? " mt-miss" : ""}`} style={{ color: stateColor(c.value) }}>{c.value === null ? "—" : sg(c.value)}</b>
      <span className="mono mt-row-s" data-state={c.state} style={{ color: stateColor(c.value) }}>{c.state}</span>
      <span className="mt-row-m">→ {c.meaning}</span>
    </div>
  );
}

export function MarketToneCard({ t }: { t: CkMarketTone }) {
  const [more, setMore] = useState(false);
  const color = STATE_COLOR[t.state] ?? "var(--ink)";
  return (
    <section className="panel ck-card" style={{ gridArea: "tone" }} data-testid="ck-tone" data-state={t.state} data-confirmation={t.confirmation}>
      <header className="panel-head"><h2 className="panel-title">Market Tone Snapshot</h2><div className="panel-note mono">{t.subtitle}</div></header>
      <div className="panel-body mt">
        <div className="mt-left">
          <div className="mt-head">
            <div className="mt-tone">
              <span className="ck-k mono">MARKET TONE</span>
              <b className="mt-state" style={{ color }} data-testid="ck-tone-state">{t.state_label}</b>
              <span className="mt-ko">{t.state_ko}</span>
              <span className="num mt-val" style={{ color }} data-testid="ck-tone-composite">{sg(t.composite)}</span>
            </div>
            <dl className="mt-kv mono">
              <div><dt>1W AGO</dt><dd className="num" data-testid="ck-tone-1w">{sg(t.composite_week_ago)}</dd></div>
              <div><dt>CHANGE</dt><dd className="num" style={{ color: stateColor(t.change_1w) }} data-testid="ck-tone-change">{sg(t.change_1w)}</dd></div>
            </dl>
          </div>
          <p className="mt-change-read" data-testid="ck-tone-change-read">{t.change_read}{t.week_ago_basis ? <span className="mt-basis mono"> · {t.week_ago_basis}</span> : null}</p>
          <Scale t={t} />
          <div className="mt-pn">
            <div className="mt-pn-box" data-testid="ck-tone-price"><span className="ck-k mono">PRICE TONE</span><b className="num" style={{ color: stateColor(t.price) }}>{sg(t.price)}</b><span>{t.price_read}</span></div>
            <div className="mt-pn-box" data-testid="ck-tone-news"><span className="ck-k mono">NEWS TONE</span><b className="num" style={{ color: stateColor(t.news) }}>{sg(t.news)}</b><span>{t.news_read}{t.news_events ? <i className="mt-n mono"> · {t.news_events}건</i> : null}</span></div>
          </div>
          <div className="mt-gap mono" data-testid="ck-tone-gap"><b>{t.gap_label}</b><span>{t.gap_read}</span></div>
        </div>
        <div className="mt-right">
          <span className="ck-k mono">MARKET COMPONENTS <i className="mt-hint">뜨거운(위험선호) 쪽이 +</i></span>
          <div className="mt-rows" data-testid="ck-tone-comps">{t.components.map((c) => <Row key={c.key} c={c} />)}</div>
          <div className="mt-conf" data-testid="ck-tone-confirmation" data-value={t.confirmation}>
            <span className="ck-k mono">REGIME CONFIRMATION</span>
            <b className="mono" style={{ color: CONF_COLOR[t.confirmation] ?? "var(--faint)" }}>{t.confirmation}</b>
            <span className="mt-conf-ko mono">{CONF_KO[t.confirmation] ?? ""}</span>
            <span className="mt-conf-read">{t.confirmation_read}</span>
          </div>
        </div>
        <div className="mt-read" data-testid="ck-tone-read">
          <span className="ck-k mono">MARKET TONE READ</span>
          <p>{t.read}</p>
        </div>
        <div className="mt-foot">
          <button type="button" className="ck-more" onClick={() => setMore(!more)} data-testid="ck-tone-more">{more ? "View details 닫기" : "View details"}</button>
          {more ? (
            <div className="mt-details" data-testid="ck-tone-details">
              <span className="ck-k mono">WHAT CHANGED · 1W</span>
              {t.changed.length ? (
                <div className="mt-changed">{t.changed.map((c) => <div key={c.key} className="mt-chg mono" data-testid="ck-tone-changed"><span>{c.label}</span><b className="num">{sg(c.from_value)} → {sg(c.to_value)}</b><em>{c.meaning}</em></div>)}</div>
              ) : <span className="mt-muted">1주 동안 크게 바뀐 재료가 없거나 1주 전 값이 없다</span>}
              <span className="ck-k mono" style={{ marginTop: 8 }}>ALL COMPONENTS · 1W</span>
              <div className="mt-all mono">{t.components.map((c) => <span key={c.key}>{c.label} <b className="num">{c.week_ago === null ? "—" : sg(c.week_ago)} → {c.value === null ? "—" : sg(c.value)}</b></span>)}</div>
              <div className="mt-muted">온도계 밴드 {t.band_label} · 신뢰도 {t.confidence.toFixed(0)}% · 1주 전 출처 {t.week_ago_source}{t.week_ago_as_of ? ` (${t.week_ago_as_of.slice(0, 10)})` : ""}</div>
              <div className="mt-muted">{t.note}</div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
