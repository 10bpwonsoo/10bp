import type { DriverCard } from "../api/investment";
import { ScoreTooltip } from "./ScoreTooltip";
import { Empty, pct, sig } from "../investment/fmt";

/**
 * Today's Market Drivers (Investment Intelligence 1).
 * 기존 Main Drivers 는 그대로 두고, 여기서는 드라이버마다 "누가 영향받나" 까지 잇는다.
 */
export function TodaysMarketDrivers({ cards }: { cards: DriverCard[] }) {
  if (cards.length === 0) return <Empty>임계(0.8σ) 이상으로 움직인 드라이버 후보가 없습니다.</Empty>;
  return (
    <div className="ii-cards">
      {cards.map((c) => (
        <article key={c.instrument_id} className="ii-card">
          <header className="ii-card-head">
            <span className="ii-card-title">{c.label}</span>
            <span className={`num ${c.z >= 0 ? "up" : "down"}`} style={{ fontSize: 15 }}>{c.change_1d_display}</span>
          </header>
          <div className="ii-kv mono">
            <span>값 <b className="num">{c.value >= 1000 ? c.value.toLocaleString("ko-KR", { maximumFractionDigits: 1 }) : c.value.toFixed(2)}</b></span>
            <span>z <b className={`num ${c.z >= 0 ? "up" : "down"}`}>{sig(c.z)}</b></span>
            <span title={`최근 ${c.percentile_observations}봉 안의 백분위`}>%ile <b className="num">{c.percentile === null ? "–" : `${c.percentile.toFixed(0)}%`}</b></span>
            <span>1W <b className="num">{pct(c.change_1w)}</b></span>
            <span>3M <b className="num">{pct(c.change_3m)}</b></span>
          </div>
          {c.affected_sectors.length > 0 && (
            <div className="ii-line"><span className="ii-k">영향 업종</span> {c.affected_sectors.join(" · ")}</div>
          )}
          <div className="ii-line">
            <span className="ii-k">민감 종목</span>
            {c.top_stocks.length === 0 ? (
              <span style={{ color: "var(--faint)" }}>임계 이상 영향 없음 — 노출 정의가 없거나 통계가 약하다</span>
            ) : (
              c.top_stocks.map((s) => (
                <ScoreTooltip key={s.stock_id} breakdown={s.breakdown} label={`${s.stock_name} ← ${s.driver_label} 영향 점수`}>
                  <span className={`ii-chip ${s.direction}`} title={s.rationale}>
                    {s.stock_name} <span className="num">{s.score.toFixed(0)}</span>{s.sign_conflict ? " ?" : ""}
                  </span>
                </ScoreTooltip>
              ))
            )}
          </div>
          <div className="ii-src mono">
            {c.source} · {c.stale ? <span style={{ color: "var(--warn)" }}>낡음 </span> : ""}{Math.round(c.freshness_sec / 3600)}시간 전
          </div>
        </article>
      ))}
    </div>
  );
}
