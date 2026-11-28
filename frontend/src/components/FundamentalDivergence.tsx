import type { StockDivergence } from "../api/investment";
import { Empty } from "../investment/fmt";

const KIND: Record<string, string> = {
  PRICE_DOWN_EPS_UP: "가격↓ / EPS↑", PRICE_UP_EPS_DOWN: "가격↑ / EPS↓", PRICE_DOWN_FOREIGN_BUY: "가격↓ / 외국인 매수",
  PRICE_UP_FOREIGN_SELL: "가격↑ / 외국인 매도", PRICE_DOWN_COMMODITY_TAILWIND: "가격↓ / 원자재 순풍",
  PRICE_UP_INDUSTRY_DOWN: "가격↑ / 산업 데이터↓", PRICE_DOWN_TP_UP: "가격↓ / 목표가↑", PRICE_UP_TP_DOWN: "가격↑ / 목표가↓",
  SECTOR_UP_STOCK_DOWN: "업종↑ / 종목↓", SECTOR_DOWN_STOCK_UP: "업종↓ / 종목↑",
};

/** Price vs Fundamental Divergence (9). 기존 Divergence 철학 — 2틱 지속, severity = tanh·지속. */
export function FundamentalDivergence({ items }: { items: StockDivergence[] }) {
  if (items.length === 0) return <Empty>가격과 펀더멘털·산업 데이터가 어긋난 종목이 없습니다. 수급 괴리(외국인)는 데이터가 없어 판정하지 않습니다.</Empty>;
  return (
    <div className="rows">
      {items.slice(0, 10).map((d) => (
        <article key={d.id} className="row" style={{ gridTemplateColumns: "1fr", gap: 5 }}>
          <div style={{ display: "flex", gap: 9, alignItems: "baseline", flexWrap: "wrap" }}>
            <span style={{ color: "var(--ink)", fontSize: 13 }}>{d.stock_name}</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--faint)" }}>{KIND[d.kind] ?? d.kind}</span>
            <span className="num" style={{ marginLeft: "auto", fontSize: 11, color: d.duration_periods >= 2 ? "var(--muted)" : "var(--faint)" }} title={d.duration_periods >= 2 ? "" : "관측 1회 — 지속 확인 중"}>
              {d.severity.toFixed(0)} · {d.duration_periods}틱{d.duration_periods < 2 ? " (확인 중)" : ""}
            </span>
          </div>
          <div style={{ display: "flex", gap: 16 }}>
            <span style={{ fontSize: 11, color: "var(--faint)" }}>{d.left.name} <b className={`num ${d.left.value >= 0 ? "up" : "down"}`}>{d.left.display}</b></span>
            <span style={{ fontSize: 11, color: "var(--faint)" }}>{d.right.name} <b className={`num ${d.right.value >= 0 ? "up" : "down"}`}>{d.right.display}</b></span>
          </div>
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.5 }}>{d.explanation}</p>
        </article>
      ))}
    </div>
  );
}
