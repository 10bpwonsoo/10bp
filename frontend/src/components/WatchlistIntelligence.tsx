import type { WatchlistRow } from "../api/investment";
import { Empty, pct, sig } from "../investment/fmt";

const BADGE: Record<string, { t: string; c: string }> = {
  NEW_EVENT: { t: "뉴스", c: "var(--info)" }, FLOW_INFLECTION: { t: "수급 전환", c: "var(--warn)" }, EPS_REVISION: { t: "EPS 리비전", c: "var(--ok)" },
  ANALYST_CHANGE: { t: "등급 변경", c: "var(--warn)" }, ALTERNATIVE_DATA_SIGNAL: { t: "대체데이터", c: "var(--accent)" },
  COMMODITY_IMPACT: { t: "원자재 영향", c: "var(--accent)" }, UNUSUAL_MOVE: { t: "이상 거래", c: "var(--crit)" },
  THEME_STRENGTHENING: { t: "테마 강화", c: "var(--up)" }, THEME_WEAKENING: { t: "테마 약화", c: "var(--down)" },
};

/** Watchlist Intelligence (11). 한 줄에 가격·수급·테마·매크로·대체데이터·EPS·이상 거래·해설. */
export function WatchlistIntelligence({ rows }: { rows: WatchlistRow[] }) {
  if (rows.length === 0) return <Empty>워치리스트가 비어 있습니다.</Empty>;
  return (
    <div className="rows">
      <div className="row ii-watch-row ii-head mono">
        <span>종목</span><span style={{ textAlign: "right" }}>가격</span><span style={{ textAlign: "right" }}>1D</span><span style={{ textAlign: "right" }}>1W</span>
        <span style={{ textAlign: "right" }}>거래량z</span><span style={{ textAlign: "right" }}>수급</span><span>테마</span><span>매크로</span><span>대체데이터</span><span style={{ textAlign: "right" }}>EPS 1M</span><span>배지</span>
      </div>
      {rows.map((r) => (
        <div key={r.stock_id} className="row ii-watch-row" title={r.commentary_excerpt ?? undefined}>
          <span className="row-label">{r.name}<span className="row-sub"> {r.sector}</span></span>
          <span className="num" style={{ textAlign: "right" }}>{r.price === null ? "–" : r.price.toLocaleString("ko-KR")}</span>
          <span className={`num ${(r.change_1d ?? 0) >= 0 ? "up" : "down"}`} style={{ textAlign: "right" }}>{pct(r.change_1d)}</span>
          <span className="num" style={{ textAlign: "right" }}>{pct(r.change_1w, 1)}</span>
          <span className={`num ${r.volume_z !== null && r.volume_z >= 1.5 ? "up" : ""}`} style={{ textAlign: "right" }}>{sig(r.volume_z)}</span>
          <span className="num" style={{ textAlign: "right", color: "var(--faint)" }}>{r.flow_z === null ? "없음" : sig(r.flow_z)}</span>
          <span style={{ fontSize: 11.5 }}>{r.theme ?? "–"} {r.theme_score !== null ? <span className={`num ${r.theme_score >= 0 ? "up" : "down"}`}>{r.theme_score.toFixed(0)}</span> : null}</span>
          <span style={{ fontSize: 11.5 }}>{r.macro_driver ? `${r.macro_driver} ` : "–"}{r.macro_impact !== null ? <span className="num">{r.macro_impact.toFixed(0)}</span> : null}</span>
          <span className="mono" style={{ fontSize: 10.5 }}>{r.alt_signal ?? "–"}</span>
          <span className={`num ${(r.eps_revision_1m ?? 0) >= 0 ? "up" : "down"}`} style={{ textAlign: "right" }}>{r.eps_revision_1m === null ? <span style={{ color: "var(--faint)" }}>없음</span> : pct(r.eps_revision_1m, 1)}</span>
          <span className="ii-badges">{r.badges.map((b) => <span key={b} className="ii-tag mono" style={{ color: BADGE[b]?.c ?? "var(--muted)", borderColor: BADGE[b]?.c ?? "var(--muted)" }}>{BADGE[b]?.t ?? b}</span>)}</span>
        </div>
      ))}
    </div>
  );
}
