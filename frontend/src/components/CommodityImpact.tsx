import type { CommodityImpactRow } from "../api/investment";
import { AGREEMENT, Empty, sig } from "../investment/fmt";

const KIND: Record<string, string> = { revenue: "매출", cost: "원가", demand: "수요", financial: "금융" };

/** Commodity → Industry → Stock (5). 종목마다 매출/원가/수요 경로가 다르다 — 뭉개지 않는다. */
export function CommodityImpact({ rows }: { rows: CommodityImpactRow[] }) {
  if (rows.length === 0) return <Empty>임계(1σ) 이상 움직인 원자재가 없습니다.</Empty>;
  return (
    <div className="ii-cards">
      {rows.map((r) => (
        <article key={r.commodity_id} className="ii-card">
          <header className="ii-card-head">
            <span className="ii-card-title">{r.label} <span className={`num ${r.z >= 0 ? "up" : "down"}`}>{sig(r.z)}</span></span>
            <span className={`num ${r.z >= 0 ? "up" : "down"}`}>{r.change_1d_display}</span>
          </header>
          <div className="ii-line"><span className="ii-k">산업</span> {r.industries.join(" · ")}</div>
          {r.rollover_suspect && <div className="ii-line" style={{ color: "var(--warn)" }}>{r.note}</div>}
          <div className="ii-links">
            {r.links.map((l) => (
              <div key={l.stock_id} className="ii-link-row" title={l.rationale}>
                <span className="ii-link-name">{l.stock_name}</span>
                <span className="mono ii-link-kind">{KIND[l.kind]} {l.direction > 0 ? "+" : "−"} {l.importance}</span>
                <span className={`num ${l.expected_effect}`}>{l.expected_effect === "up" ? "수혜" : l.expected_effect === "down" ? "피해" : "중립"}</span>
                <span className="num" style={{ color: "var(--muted)" }}>실측 {sig(l.price_reaction_z)}</span>
                <span className="mono" style={{ color: AGREEMENT[l.agreement].color, fontSize: 10 }}>{AGREEMENT[l.agreement].label}</span>
              </div>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}
