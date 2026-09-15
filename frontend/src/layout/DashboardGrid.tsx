import type { IntelligenceSnapshot } from "../api/types";
import { AlertTimeline } from "../components/AlertTimeline";
import { ConfirmationMatrix } from "../components/ConfirmationMatrix";
import { DataHealthPanel } from "../components/DataHealthPanel";
import { DivergencePanel } from "../components/DivergencePanel";
import { ImpactMapPanel } from "../components/ImpactMap";
import { MarketStateHeader } from "../components/MarketStateHeader";
import { NewsFeed } from "../components/NewsFeed";
import { Panel } from "../components/Panel";
import { SentimentGauge } from "../components/SentimentGauge";
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
/**
 * 패널 머리에 무엇을 띄울지. 예상과 반대로 움직인 노드가 있으면 그것이
 * 먼저다 — 경로 개수보다 운용자가 먼저 알아야 할 것이다.
 */
function impactNote(snapshot: IntelligenceSnapshot) {
  // 한 노드가 여러 경로에 등장할 수 있다. 같은 자산을 두 번 세지 않는다.
  const bad = new Set<string>();
  for (const m of snapshot.impact_maps) {
    for (const n of m.nodes) if (n.reaction === "mismatch") bad.add(n.id);
  }
  const paths = snapshot.impact_maps.length;
  if (bad.size > 0) {
    return (
      <span style={{ color: "var(--crit)" }}>
        예상과 반대 {bad.size}개{paths > 1 ? ` · ${paths}개 경로` : ""}
      </span>
    );
  }
  return paths > 1 ? `${paths}개 경로` : undefined;
}

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
        {/* 판정과 온도계를 나란히. 온도계는 새 패널이 아니라 판정의 두 번째
            읽기다 — 라벨이 '무엇' 이라면 온도는 '얼마나' 다. */}
        <div className="state-split">
          <MarketStateHeader state={snapshot.market_state} />
          <SentimentGauge t={snapshot.thermometer} />
        </div>
      </Panel>

      <Panel title="Theme Heatmap" span={2} flush note={`${snapshot.themes.length}개`}>
        <ThemeHeatmap themes={snapshot.themes} events={snapshot.events} />
      </Panel>

      <Panel title="What's Moving" flush note="z-score 순">
        <WhatsMoving items={snapshot.whats_moving} />
      </Panel>

      <Panel title="Why · 뉴스" flush note={`${snapshot.events.length}건`}>
        <NewsFeed events={snapshot.events} />
      </Panel>

      <Panel title="Flow & Price Confirmation" flush note="세 신호 비교">
        <ConfirmationMatrix themes={snapshot.themes} />
      </Panel>

      <Panel
        title="Divergence"
        flush
        note={snapshot.divergences.length > 0 ? `${snapshot.divergences.length}건` : undefined}
      >
        <DivergencePanel items={snapshot.divergences} themeNames={themeNames} />
      </Panel>

      <Panel
        title="Impact Map"
        span={3}
        note={impactNote(snapshot)}
      >
        <ImpactMapPanel maps={snapshot.impact_maps} />
      </Panel>

      <Panel
        title="Alert · Timeline"
        span={3}
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
