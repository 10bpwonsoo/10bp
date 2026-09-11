import type { IntelligenceSnapshot, RawNewsItem } from "../api/types";
import { DataHealthPanel } from "../components/DataHealthPanel";
import { MarketStateHeader } from "../components/MarketStateHeader";
import { NewsFeed } from "../components/NewsFeed";
import { Panel, Pending } from "../components/Panel";
import { ThemeHeatmap } from "../components/ThemeHeatmap";
import { WhatsMoving } from "../components/WhatsMoving";

/**
 * 패널 배치는 설계서 STEP 10 의 화면 순서를 따른다.
 *   MARKET STATE → THEME HEATMAP → WHAT'S MOVING → WHY →
 *   FLOW & PRICE CONFIRMATION → DIVERGENCE → IMPACT MAP → ALERT
 *
 * 아직 만들지 않은 패널도 자리를 차지한다. 구현 순서에 따라 화면이 어떻게
 * 채워질지 한눈에 보이고, P1~P3 에서 붙일 자리가 분명해진다.
 */
export function DashboardGrid({
  snapshot,
  news,
}: {
  snapshot: IntelligenceSnapshot;
  news: RawNewsItem[];
}) {
  return (
    <div className="grid">
      <Panel
        title="Market State"
        span={3}
        note={
          <span className="num">
            {new Date(snapshot.as_of).toLocaleString("ko-KR", {
              timeZone: "Asia/Seoul",
              dateStyle: "medium",
              timeStyle: "short",
            })}{" "}
            KST
          </span>
        }
      >
        <MarketStateHeader state={snapshot.market_state} />
      </Panel>

      <Panel title="Theme Heatmap" span={2} flush note={`${snapshot.themes.length}개`}>
        <ThemeHeatmap themes={snapshot.themes} />
      </Panel>

      <Panel title="What's Moving" flush note="z-score 순">
        <WhatsMoving items={snapshot.whats_moving} />
      </Panel>

      <Panel title="Why · 뉴스" flush note={`${news.length}건`}>
        <NewsFeed items={news} />
      </Panel>

      <Panel title="Flow & Price Confirmation">
        <Pending stage="P2">
          News · Flow · Price · Volatility 네 신호를 나란히 놓고 서로를 확인하는
          패널입니다. ConfirmationEngine 이 붙으면 활성화됩니다.
        </Pending>
      </Panel>

      <Panel title="Divergence">
        <Pending stage="P2">
          뉴스 내러티브와 실제 가격·수급이 어긋나는 지점을 찾습니다. 이
          프로젝트의 핵심 차별화 기능이며 DivergenceEngine 에서 붙습니다.
        </Pending>
      </Panel>

      <Panel title="Impact Map" span={2}>
        <Pending stage="P3">
          Event → Theme → Macro → Asset → Sector 관계 그래프입니다. 사전 정의
          관계는 실선, LLM 이 제안한 관계는 점선으로 구분해 그립니다.
        </Pending>
      </Panel>

      <Panel title="Alert · Timeline">
        <Pending stage="P2">
          수준이 아니라 변화를 봅니다. 직전 스냅샷 대비 급변과 중복 억제는
          AlertEngine 에서 붙습니다.
        </Pending>
      </Panel>

      <Panel title="Data Health" span={3}>
        <DataHealthPanel health={snapshot.data_health} versions={snapshot.engine_versions} />
      </Panel>
    </div>
  );
}
