import type { SentimentThermometer } from "../api/types";
import { SentimentGauge } from "./SentimentGauge";

/**
 * MARKET TONE SNAPSHOT (2026-10-07) — 실시간 2 의 MARKET REGIME HISTORY 와 TODAY'S MARKET DRIVERS 사이.
 * 실시간 탭의 시장 온도 화면(SentimentGauge)을 **그대로** 보인다 — 같은 컴포넌트, 같은 snapshot.thermometer. 숫자를 다시 만들지 않는다.
 * HISTORY(한 달의 regime) → 현재 tone(왜 이 regime 인가) → TODAY'S DRIVERS 의 다리.
 */
export function MarketToneCard({ thermo }: { thermo: SentimentThermometer | null }) {
  return (
    <section className="panel ck-card" style={{ gridArea: "tone" }} data-testid="ck-tone">
      <header className="panel-head"><h2 className="panel-title">Market Tone Snapshot</h2><div className="panel-note mono">현재 시장의 가격·위험선호·변동성·신용·성장 신호 · 실시간 탭과 같은 온도계</div></header>
      <div className="panel-body ck-tone-body"><SentimentGauge t={thermo} /></div>
    </section>
  );
}
