import type { IntelligenceSnapshot } from "../api/types";
import { AlertTimeline } from "../components/AlertTimeline";
import { ConfirmationMatrix } from "../components/ConfirmationMatrix";
import { DataHealthPanel } from "../components/DataHealthPanel";
import { DivergencePanel } from "../components/DivergencePanel";
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
export function DashboardGrid({ snapshot }: { snapshot: IntelligenceSnapshot }) {
  const themeNames = Object.fromEntries(snapshot.themes.map((t) => [t.theme_id, t.name]));

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

      <Panel title="Why · 뉴스" flush note={`${snapshot.events.length}건`}>
        <NewsFeed events={snapshot.events} />
      </Panel>

      <Panel title="Flow & Price Confirmation" flush note="네 신호 비교">
        <ConfirmationMatrix themes={snapshot.themes} />
      </Panel>

      <Panel
        title="Divergence"
        flush
        note={snapshot.divergences.length > 0 ? `${snapshot.divergences.length}건` : undefined}
      >
        <DivergencePanel items={snapshot.divergences} themeNames={themeNames} />
      </Panel>

      <Panel title="Impact Map" span={2}>
        <Pending stage="P3">
          Event → Theme → Macro → Asset → Sector 관계 그래프입니다. 사전 정의
          관계는 실선, LLM 이 제안한 관계는 점선으로 구분해 그립니다.
        </Pending>
      </Panel>

      <Panel
        title="Alert · Timeline"
        flush
        note={
          snapshot.alerts.length > 0
            ? `${snapshot.alerts.filter((a) => a.state !== "RESOLVED").length}건 진행 / ${snapshot.alerts.length}건`
            : undefined
        }
      >
        <AlertTimeline items={snapshot.alerts} />
      </Panel>

      <Panel title="Data Health" span={3}>
        <DataHealthPanel health={snapshot.data_health} versions={snapshot.engine_versions} />
      </Panel>
    </div>
  );
}
