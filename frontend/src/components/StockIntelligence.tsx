import { useState } from "react";
import type { InvestmentIntelligence, StockIntelligence as SI } from "../api/investment";
import { ScoreTooltip } from "./ScoreTooltip";
import { CONF_COLOR, Empty, pct, sig } from "../investment/fmt";

const KIND_LABEL: Record<string, string> = {
  CONFIRMED_DATA: "데이터 확인", CONFIRMED_NEWS: "뉴스 확인", ANALYST_VIEW: "애널리스트", MARKET_INFERENCE: "시장 추론",
  CLAUDE_INTERPRETATION: "Claude 해석", UNKNOWN: "근거 부족",
};
const EXP_KIND: Record<string, string> = { revenue: "매출", cost: "원가", demand: "수요", financial: "금융" };

/**
 * Stock Intelligence (10). 숫자표가 먼저가 아니다 — WHAT / WHY / WHAT CHANGED / WHAT NEXT 가 먼저,
 * 그 아래 가격·거래량·노출·대체데이터·peer·EPS·해설.
 */
export function StockIntelligence({ inv }: { inv: InvestmentIntelligence }) {
  const ids = Object.keys(inv.stocks);
  const [sel, setSel] = useState<string>(inv.watchlist[0]?.stock_id ?? ids[0] ?? "");
  const s: SI | undefined = inv.stocks[sel];
  if (!s) return <Empty>종목 데이터가 없습니다.</Empty>;
  const row = s.row;
  return (
    <div className="ii-stock">
      <div className="ii-stock-pick">
        <select className="ii-select mono" value={sel} onChange={(e) => setSel(e.target.value)} aria-label="종목 선택">
          {ids.map((id) => <option key={id} value={id}>{inv.stocks[id]?.meta.name ?? id}</option>)}
        </select>
        <span className="num" style={{ fontSize: 18 }}>{row.price === null ? "–" : row.price.toLocaleString("ko-KR")}</span>
        <span className={`num ${row.change_1d !== null && row.change_1d >= 0 ? "up" : "down"}`} style={{ fontSize: 14 }}>{pct(row.change_1d)}</span>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--faint)" }}>{s.meta.symbol} · {s.meta.sector}{row.stale ? " · 낡음" : ""}</span>
      </div>

      <div className="ii-headlines">
        <div><span className="ii-hk">WHAT IS HAPPENING?</span><span>{s.headline_what}</span></div>
        <div><span className="ii-hk">WHY?</span><span>{s.headline_why}</span></div>
        <div><span className="ii-hk">WHAT CHANGED?</span><span>{s.headline_changed}</span></div>
        <div><span className="ii-hk">WHAT MATTERS NEXT?</span><span>{s.headline_next}</span></div>
      </div>

      <div className="ii-stock-grid">
        <section>
          <div className="ii-group mono">가격 · 거래량 · 상대</div>
          <div className="ii-kv mono">
            <span>1D <b className={`num ${(row.change_1d ?? 0) >= 0 ? "up" : "down"}`}>{pct(row.change_1d)}</b></span>
            <span>1W <b className="num">{pct(row.change_1w, 1)}</b></span>
            <span>1M <b className="num">{pct(row.change_1m, 1)}</b></span>
            <span>z <b className="num">{sig(row.z)}</b></span>
            <span>거래량 z <b className="num">{sig(row.volume_z)}</b></span>
            <span>상대 z <b className="num">{sig(row.relative_z)}</b></span>
            <span>%ile <b className="num">{row.percentile === null ? "–" : `${row.percentile.toFixed(0)}%`}</b></span>
            <span>수급 <b className="num" style={{ color: "var(--faint)" }}>없음</b></span>
          </div>
          {s.anomaly && s.anomaly.label !== "NONE" && <p className="ii-note" style={{ color: "var(--warn)" }}>{s.anomaly.note}</p>}
        </section>

        <section>
          <div className="ii-group mono">원인 후보 (Why did this stock move?)</div>
          {s.explanation?.causes.map((c, i) => (
            <div key={i} className="ii-cause">
              <span className="mono ii-cause-kind" style={{ color: CONF_COLOR[c.confidence] }}>{KIND_LABEL[c.kind]} · {c.confidence}</span>
              <span>{c.text}</span>
              {c.evidence.length > 0 && <span className="ii-src mono">{c.evidence.map((e) => `${e.label} ${e.display}`).join(" · ")}</span>}
            </div>
          ))}
        </section>

        <section>
          <div className="ii-group mono">노출 — 통계(60일) vs 사업 구조</div>
          {s.exposure?.rows.map((r) => (
            <div key={r.driver_id} className="row ii-exp-row" title={r.note}>
              <span className="row-label">{r.driver_label}</span>
              <span className="num" title="60일 상관">{r.corr === null ? "–" : `${r.corr >= 0 ? "+" : ""}${r.corr.toFixed(2)}`}</span>
              <span className="num" style={{ color: "var(--faint)" }} title="60일 베타">{r.beta === null ? "–" : `β${r.beta >= 0 ? "+" : ""}${r.beta.toFixed(2)}`}</span>
              <span className="mono" style={{ fontSize: 10.5 }}>{r.fundamental ? `${EXP_KIND[r.fundamental.kind]} ${r.fundamental.direction > 0 ? "+" : "−"} ${r.fundamental.importance}` : <span style={{ color: "var(--faint)" }}>사업 노출 정의 없음</span>}</span>
              <span className="mono" style={{ fontSize: 10, color: r.sign_agreement === false ? "var(--warn)" : r.sign_agreement ? "var(--ok)" : "var(--faint)" }}>{r.sign_agreement === null ? "–" : r.sign_agreement ? "일치" : "상충"}</span>
            </div>
          ))}
        </section>

        <section>
          <div className="ii-group mono">시장 충격 → 이 종목</div>
          {s.impacts.length === 0 ? <p className="ii-note">임계 이상 영향 없음</p> : s.impacts.map((i) => (
            <div key={i.driver_id} className="row ii-exp-row">
              <span className="row-label">{i.driver_label}</span>
              <span className={`num ${i.shock_z >= 0 ? "up" : "down"}`}>{sig(i.shock_z)}</span>
              <ScoreTooltip breakdown={i.breakdown} label={`${i.driver_label} 영향`}><span className={`num ${i.direction}`}>{i.score.toFixed(0)}</span></ScoreTooltip>
              <span style={{ fontSize: 11, color: "var(--muted)", gridColumn: "4 / 6" }}>{i.rationale}</span>
            </div>
          ))}
        </section>

        <section>
          <div className="ii-group mono">대체데이터 · 글로벌 peer</div>
          {[...s.alternative, ...s.peers].map((p) => (
            <div key={p.id} className="row ii-exp-row" title={p.why}>
              <span className="row-label">{p.label}{p.quality === "MISSING" ? <span className="row-sub"> 없음</span> : null}</span>
              <span className={`num ${(p.change_1d ?? 0) >= 0 ? "up" : "down"}`}>{pct(p.change_1d)}</span>
              <span className="num" style={{ color: "var(--faint)" }}>{sig(p.z)}</span>
              <span className="num" style={{ color: "var(--faint)" }}>1M {pct(p.change_1m, 1)}</span>
              <span className="mono" style={{ fontSize: 10, color: "var(--faint)" }}>{p.group}</span>
            </div>
          ))}
          {s.lead_lag.filter((l) => l.verdict !== "insufficient").map((l) => (
            <div key={l.lead_id} className="ii-src mono" style={{ padding: "4px 0" }}>{l.label}: {l.note}</div>
          ))}
        </section>

        <section>
          <div className="ii-group mono">실적 · 애널리스트 · 괴리</div>
          {s.analyst && s.analyst.available ? (
            <div className="ii-kv mono">
              <span>EPS 1M <b className={`num ${(s.analyst.eps_revision_1m ?? 0) >= 0 ? "up" : "down"}`}>{pct(s.analyst.eps_revision_1m, 1)}</b></span>
              <span>EPS 3M <b className="num">{pct(s.analyst.eps_revision_3m, 1)}</b></span>
              <span>TP 1M <b className="num">{pct(s.analyst.tp_change_1m, 1)}</b></span>
              <span>등급 <b>{s.analyst.rating ?? "–"}{s.analyst.rating_change ? ` (${s.analyst.rating_change})` : ""}</b></span>
              <span>4분면 <b>{s.analyst.quadrant}</b></span>
            </div>
          ) : (
            <p className="ii-note">{s.analyst?.note ?? "컨센서스 없음"}</p>
          )}
          {s.divergences.map((d) => <p key={d.id} className="ii-note" style={{ color: "var(--ink-2)" }}>{d.explanation}</p>)}
        </section>

        <section style={{ gridColumn: "1 / -1" }}>
          <div className="ii-group mono">Claude 해설</div>
          {s.commentary ? <CommentaryBlock c={s.commentary} /> : <p className="ii-note">이 종목에 대한 수기 해설이 아직 없습니다. 해설은 Claude 가 데이터를 읽고 직접 쓰며(API 호출 아님) FACT / NEWS / ANALYST / INTERPRETATION / UNKNOWN 을 분리합니다.</p>}
          <div className="ii-src mono">미확보: {s.missing.join(" · ")}</div>
        </section>
      </div>
    </div>
  );
}

export function CommentaryBlock({ c }: { c: import("../api/investment").Commentary }) {
  const sec: Array<[string, string[]]> = [["FACT", c.sections.fact], ["NEWS", c.sections.news], ["ANALYST", c.sections.analyst], ["INTERPRETATION", c.sections.interpretation], ["UNKNOWN", c.sections.unknown]];
  return (
    <div className="ii-commentary">
      <div className="ii-src mono">
        {c.date} · {c.source_mode === "manual" ? "Claude 수기 (API 아님)" : c.source_mode} · 확신 <span style={{ color: CONF_COLOR[c.confidence] }}>{c.confidence}</span>{c.stale ? <span style={{ color: "var(--warn)" }}> · 오래된 해설</span> : null}
      </div>
      {sec.map(([k, lines]) => lines.length > 0 && (
        <div key={k} className="ii-cm-sec"><span className="ii-hk">{k}</span><ul>{lines.map((l, i) => <li key={i}>{l}</li>)}</ul></div>
      ))}
      {c.what_next.length > 0 && <div className="ii-cm-sec"><span className="ii-hk">WHAT NEXT</span><ul>{c.what_next.map((l, i) => <li key={i}>{l}</li>)}</ul></div>}
      {c.evidence.length > 0 && <div className="ii-src mono">근거: {c.evidence.map((e) => `${e.label} ${e.display}`).join(" · ")}</div>}
    </div>
  );
}
