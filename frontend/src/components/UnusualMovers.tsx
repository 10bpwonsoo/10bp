import type { StockAnomaly } from "../api/investment";
import { Empty } from "../investment/fmt";

const LABEL: Record<string, { t: string; c: string }> = {
  UNEXPLAINED_ACTIVITY: { t: "설명되지 않는 활동", c: "var(--crit)" },
  VOLUME_SPIKE: { t: "거래량 급증", c: "var(--warn)" },
  RELATIVE_MOVE: { t: "시장 대비 이탈", c: "var(--info)" },
  RETURN_SPIKE: { t: "수익률 급변", c: "var(--warn)" },
  NEWS_DRIVEN_MOVE: { t: "뉴스 동반", c: "var(--muted)" },
  NONE: { t: "", c: "var(--faint)" },
};
const FALLBACK = { t: "", c: "var(--faint)" };

/** Unusual Stock Movers (6). '매집' 을 말하지 않는다 — 수급 데이터가 없어 주체를 모른다. */
export function UnusualMovers({ items }: { items: StockAnomaly[] }) {
  if (items.length === 0) return <Empty>수익률·거래량·상대 z 가 임계를 넘은 종목이 없습니다.</Empty>;
  return (
    <div className="rows">
      {items.map((a) => (
        <article key={a.stock_id} className="row" style={{ gridTemplateColumns: "1fr", gap: 5 }}>
          <div style={{ display: "flex", gap: 9, alignItems: "baseline", flexWrap: "wrap" }}>
            <span style={{ color: "var(--ink)", fontSize: 13 }}>{a.stock_name}</span>
            <span className="badge" style={{ color: (LABEL[a.label] ?? FALLBACK).c, fontSize: 9.5, padding: "1px 6px" }}>{(LABEL[a.label] ?? FALLBACK).t}</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--faint)" }}>{a.flags.join(" · ")}</span>
            <span className="num" style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)" }}>{a.severity.toFixed(0)}</span>
          </div>
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.5 }}>{a.note}</p>
          <div className="ii-src mono">미확보: {a.missing.join(" · ")}</div>
        </article>
      ))}
    </div>
  );
}
