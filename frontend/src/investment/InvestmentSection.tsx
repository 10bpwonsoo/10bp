import { Panel } from "../components/Panel";
import { TodaysMarketDrivers } from "../components/TodaysMarketDrivers";
import { AlternativeDataPulse } from "../components/AlternativeDataPulse";
import { MarketStockImpact } from "../components/MarketStockImpact";
import { SemiconductorIntelligence } from "../components/SemiconductorIntelligence";
import { CommodityImpact } from "../components/CommodityImpact";
import { UnusualMovers } from "../components/UnusualMovers";
import { ThemeStock } from "../components/ThemeStock";
import { AnalystRevision } from "../components/AnalystRevision";
import { FundamentalDivergence } from "../components/FundamentalDivergence";
import { StockIntelligence } from "../components/StockIntelligence";
import { WatchlistIntelligence } from "../components/WatchlistIntelligence";
import { ClaudeCommentary } from "../components/ClaudeCommentary";
import { useInvestment } from "../api/useInvestment";

/**
 * INVESTMENT INTELLIGENCE — 기존 대시보드 **아래** 에 붙는 신규 영역 (2026-09-16).
 *
 * 기존 패널은 손대지 않는다. 별도 엔드포인트(/api/v1/investment)와 별도 캐시를
 * 쓰므로 기존 화면이 먼저 뜨고 이 영역은 뒤따라 채워진다. 겹치는 정보가 있어도
 * 지금은 통합하지 않는다 — 실사용 뒤 정리한다.
 *
 * 순서: MARKET → ALTERNATIVE DATA → INDUSTRY → STOCK → PRICE/FLOW → FUNDAMENTAL → ANALYST → CLAUDE
 */
export function InvestmentSection({ scenario, enabled }: { scenario?: string; enabled: boolean }) {
  const { data, error, loading } = useInvestment(scenario, enabled);
  const names: Record<string, string> = {};
  if (data) for (const [id, s] of Object.entries(data.stocks)) names[id] = s.meta.name;
  if (data) for (const p of data.alternative) names[p.id] = p.label;
  names.MARKET = "시장 전체";

  return (
    <div className="ii-section">
      <div className="ii-banner">
        <div className="ii-banner-title">INVESTMENT INTELLIGENCE</div>
        <div className="ii-banner-sub mono">MARKET → ALTERNATIVE DATA → INDUSTRY → STOCK → PRICE / FLOW → FUNDAMENTAL → ANALYST → CLAUDE</div>
        {data && (
          <div className="ii-banner-meta mono">
            {new Date(data.as_of).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "medium", timeStyle: "short" })} KST ·
            종목 {data.health.stocks_available}/{data.health.stocks_expected} · 대체데이터 {data.health.alt_available}/{data.health.alt_expected}
            {data.health.stale.length > 0 ? ` · 낡음 ${data.health.stale.length}` : ""} · 계산 {Math.round(data.health.timings_ms.total ?? 0)}ms
          </div>
        )}
      </div>
      {error && <div className="banner" role="alert"><span className="tag">연결 오류</span><span>{error}</span></div>}
      {!data ? (
        <div className="grid"><section className="panel span-3"><div className="panel-body" style={{ color: "var(--muted)" }}>{loading ? "종목·대체데이터 계층을 계산하는 중… (기존 화면과 별도로 뜹니다)" : "표시할 데이터가 없습니다."}</div></section></div>
      ) : (
        <div className="grid">
          <Panel title="1 · Today's Market Drivers" span={3} note={`${data.drivers.length}개 · 임계 0.8σ`}>
            <TodaysMarketDrivers cards={data.drivers} />
          </Panel>
          <Panel title="2 · Alternative Data Pulse" span={2} flush note={`${data.health.alt_available}/${data.health.alt_expected} 확보 · 누르면 Why it matters`}>
            <AlternativeDataPulse points={data.alternative} />
          </Panel>
          <Panel title="3 · Market → Stock Impact" flush note="충격 × 노출 × 신뢰 × 관련성">
            <MarketStockImpact impacts={data.market_stock_impact} />
          </Panel>
          <Panel title="4 · Semiconductor Intelligence" span={3} note="메모리 · peer · 국내 · EPS 방향 합의">
            <SemiconductorIntelligence s={data.semiconductor} />
          </Panel>
          <Panel title="5 · Commodity → Industry → Stock" span={2} note="매출 / 원가 / 수요 경로 구분">
            <CommodityImpact rows={data.commodity_impact} />
          </Panel>
          <Panel title="6 · Unusual Stock Movers" flush note="수익률 · 거래량 · 상대 z">
            <UnusualMovers items={data.unusual_movers} />
          </Panel>
          <Panel title="7 · Theme → Stock" flush note="테마 점수가 종목에서 확인되는가">
            <ThemeStock rows={data.theme_stocks} />
          </Panel>
          <Panel title="8 · Analyst Revision Monitor" flush note={`${data.analyst.filter((a) => a.available).length}/${data.analyst.length} 확보`}>
            <AnalystRevision rows={data.analyst} />
          </Panel>
          <Panel title="9 · Price vs Fundamental Divergence" flush note={data.fundamental_divergences.length > 0 ? `${data.fundamental_divergences.length}건` : undefined}>
            <FundamentalDivergence items={data.fundamental_divergences} />
          </Panel>
          <Panel title="10 · Stock Intelligence" span={3} note="WHAT · WHY · WHAT CHANGED · WHAT NEXT">
            <StockIntelligence inv={data} />
          </Panel>
          <Panel title="11 · Watchlist Intelligence" span={3} flush note={`${data.watchlist.length}종목`}>
            <WatchlistIntelligence rows={data.watchlist} />
          </Panel>
          <Panel title="12 · Claude Commentary" span={3} note={data.commentary.length > 0 ? `${data.commentary.length}건 · 수기` : "수기 · API 아님"}>
            <ClaudeCommentary items={data.commentary} names={names} />
          </Panel>
          <Panel title="Investment Data Health" span={3}>
            <div className="ii-health">
              <div><span className="ii-k">미확보</span><ul>{data.health.not_available.map((n, i) => <li key={i}>{n}</li>)}</ul></div>
              {data.health.warnings.length > 0 && <div><span className="ii-k">경고</span><ul>{data.health.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}
              <div className="ii-src mono">엔진 {Object.entries(data.engine_versions).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
