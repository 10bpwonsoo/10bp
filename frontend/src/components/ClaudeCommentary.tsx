import type { Commentary } from "../api/investment";
import { CommentaryBlock } from "./StockIntelligence";
import { Empty } from "../investment/fmt";

/** Claude Commentary (12). 시장·대체데이터·애널리스트 해설. API 호출이 아니라 Claude 수기다. */
export function ClaudeCommentary({ items, names }: { items: Commentary[]; names: Record<string, string> }) {
  const top = items.filter((c) => c.kind !== "stock");
  const stocks = items.filter((c) => c.kind === "stock");
  if (items.length === 0) {
    return <Empty>작성된 해설이 없습니다. 해설은 Claude 가 데이터를 읽고 직접 쓰며, FACT / NEWS / ANALYST / INTERPRETATION / UNKNOWN 을 분리해 저장합니다 (data/commentary/*.json). API 호출이 아니므로 자동 갱신되지 않습니다.</Empty>;
  }
  return (
    <div className="ii-cm-list">
      {top.map((c) => (
        <article key={`${c.kind}-${c.entity}`} className="ii-card">
          <header className="ii-card-head"><span className="ii-card-title">{c.kind === "market" ? "시장" : c.kind === "alternative" ? "대체데이터" : "애널리스트"} · {names[c.entity] ?? c.entity}</span></header>
          <CommentaryBlock c={c} />
        </article>
      ))}
      {stocks.length > 0 && (
        <div className="ii-src mono" style={{ padding: "4px 0" }}>종목 해설 {stocks.length}건은 Stock Intelligence 에서 종목을 고르면 보입니다: {stocks.map((c) => names[c.entity] ?? c.entity).join(" · ")}</div>
      )}
    </div>
  );
}
