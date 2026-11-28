import type { AnalystSnapshot } from "../api/investment";
import { Empty, pct } from "../investment/fmt";

const QUAD: Record<string, string> = {
  PRICE_UP_EPS_UP: "가격↑ EPS↑ (확인)", PRICE_DOWN_EPS_UP: "가격↓ EPS↑ (괴리)", PRICE_UP_EPS_DOWN: "가격↑ EPS↓ (괴리)",
  PRICE_DOWN_EPS_DOWN: "가격↓ EPS↓ (확인)", UNKNOWN: "판정 불가",
};

/** Analyst Revision Monitor (8). 공개 API 가 없어 CSV·MOCK 만 — 없는 것은 없다고 적는다. */
export function AnalystRevision({ rows }: { rows: AnalystSnapshot[] }) {
  const avail = rows.filter((r) => r.available);
  if (avail.length === 0) {
    return (
      <Empty>
        컨센서스 데이터가 없습니다. Yahoo 컨센서스 엔드포인트는 401, FnGuide·네이버는 이 환경에서 차단됩니다.
        <span className="mono"> data/replay/analyst/&lt;STOCK_ID&gt;.csv</span> (date,broker,rating,target_price,eps_fy1) 를 넣으면 읽습니다. 출처가 불확실한 값을 억지로 채우지 않았습니다.
      </Empty>
    );
  }
  const quads = ["PRICE_UP_EPS_UP", "PRICE_DOWN_EPS_UP", "PRICE_UP_EPS_DOWN", "PRICE_DOWN_EPS_DOWN"];
  return (
    <div className="rows">
      <div className="ii-quad">
        {quads.map((q) => (
          <div key={q} className="ii-quad-cell">
            <div className="mono ii-k">{QUAD[q]}</div>
            <div>{avail.filter((r) => r.quadrant === q).map((r) => <span key={r.stock_id} className="ii-chip">{r.stock_name}</span>)}</div>
          </div>
        ))}
      </div>
      <div className="row ii-an-row ii-head mono">
        <span>종목</span><span style={{ textAlign: "right" }}>EPS 1W</span><span style={{ textAlign: "right" }}>EPS 1M</span><span style={{ textAlign: "right" }}>EPS 3M</span><span style={{ textAlign: "right" }}>TP 1M</span><span>등급</span>
      </div>
      {avail.map((r) => (
        <div key={r.stock_id} className="row ii-an-row" title={`${r.note} · ${r.source ?? ""}`}>
          <span className="row-label">{r.stock_name}<span className="row-sub"> {r.brokers}사</span></span>
          <span className={`num ${r.eps_revision_1w !== null && r.eps_revision_1w >= 0 ? "up" : "down"}`} style={{ textAlign: "right" }}>{pct(r.eps_revision_1w, 1)}</span>
          <span className={`num ${r.eps_revision_1m !== null && r.eps_revision_1m >= 0 ? "up" : "down"}`} style={{ textAlign: "right" }}>{pct(r.eps_revision_1m, 1)}</span>
          <span className={`num ${r.eps_revision_3m !== null && r.eps_revision_3m >= 0 ? "up" : "down"}`} style={{ textAlign: "right" }}>{pct(r.eps_revision_3m, 1)}</span>
          <span className={`num ${r.tp_change_1m !== null && r.tp_change_1m >= 0 ? "up" : "down"}`} style={{ textAlign: "right" }}>{pct(r.tp_change_1m, 1)}</span>
          <span className="mono" style={{ fontSize: 11 }}>{r.rating ?? "–"}{r.rating_change ? <span style={{ color: "var(--warn)" }}> {r.rating_change}</span> : null}</span>
        </div>
      ))}
      <div className="ii-src mono" style={{ padding: "6px var(--pad)" }}>미확보 {rows.length - avail.length}종목 — 공개 소스 없음</div>
    </div>
  );
}
