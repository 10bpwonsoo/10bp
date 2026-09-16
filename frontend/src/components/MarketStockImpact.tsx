import type { StockImpact } from "../api/investment";
import { ScoreTooltip } from "./ScoreTooltip";
import { Empty, MiniBar, sig } from "../investment/fmt";

/** Market → Stock Impact (3). 시장 충격이 종목에 어떻게 이어지는가 — 점수와 그 근거. */
export function MarketStockImpact({ impacts }: { impacts: StockImpact[] }) {
  if (impacts.length === 0) return <Empty>임계 이상의 시장 → 종목 영향이 없습니다. 드라이버가 조용하거나 노출 통계가 약합니다.</Empty>;
  return (
    <div className="rows">
      <div className="row ii-impact-row ii-head mono">
        <span>종목</span><span>드라이버</span><span style={{ textAlign: "right" }}>충격</span><span style={{ textAlign: "right" }}>노출</span><span style={{ textAlign: "right" }}>점수</span><span />
      </div>
      {impacts.slice(0, 14).map((i) => (
        <div key={`${i.stock_id}-${i.driver_id}`} className="row ii-impact-row" title={i.rationale}>
          <span className="row-label">
            {i.stock_name}
            {i.sign_conflict ? <span className="row-sub" style={{ color: "var(--warn)" }} title="통계 부호와 사업 노출 부호가 다르다"> 상충</span> : null}
          </span>
          <span style={{ color: "var(--ink-2)", fontSize: 12 }}>{i.driver_label}</span>
          <span className={`num ${i.shock_z >= 0 ? "up" : "down"}`} style={{ textAlign: "right" }}>{sig(i.shock_z)}</span>
          <span className="num" style={{ textAlign: "right" }} title={`통계 신뢰 ${(i.stat_confidence * 100).toFixed(0)}% · 사업 관련성 ${(i.fund_relevance * 100).toFixed(0)}%`}>{i.exposure >= 0 ? "+" : ""}{i.exposure.toFixed(2)}</span>
          <ScoreTooltip breakdown={i.breakdown} label={`${i.stock_name} ← ${i.driver_label}`}>
            <span className={`num ${i.direction}`} style={{ textAlign: "right", display: "block" }}>{i.direction === "up" ? "▲" : i.direction === "down" ? "▼" : "→"} {i.score.toFixed(0)}</span>
          </ScoreTooltip>
          <MiniBar v={i.direction === "down" ? -i.score / 100 : i.score / 100} max={1} />
        </div>
      ))}
    </div>
  );
}
