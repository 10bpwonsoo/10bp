import type { ThemeState } from "../api/types";
import { Pending } from "./Panel";
import { ScoreTooltip } from "./ScoreTooltip";

/** 점수(-100~+100)를 방향 색의 농도로. 0 근처는 거의 무색이다. */
function cellStyle(score: number): React.CSSProperties {
  const a = Math.min(Math.abs(score) / 100, 1) * 0.85;
  return {
    background:
      score >= 0
        ? `color-mix(in oklab, var(--up) ${a * 100}%, var(--surface-2))`
        : `color-mix(in oklab, var(--down) ${a * 100}%, var(--surface-2))`,
  };
}

const CONFIRM_LABEL: Record<ThemeState["cross_asset_confirmation"], string> = {
  HIGH: "높음",
  MEDIUM: "보통",
  LOW: "낮음",
  CONFLICT: "상충",
};

export function ThemeHeatmap({ themes }: { themes: ThemeState[] }) {
  if (themes.length === 0) {
    return (
      <Pending stage="P1">
        ThemeEngine 이 붙으면 테마별 Score, News Sentiment, Price/Flow Momentum,
        Cross-Asset Confirmation, Confidence 가 표시됩니다. 테마 레지스트리와
        테마-자산 매핑은 이미 정의되어 있고, 점수 산식만 P1 에서 붙습니다.
      </Pending>
    );
  }

  const sorted = [...themes].sort((a, b) => b.theme_score - a.theme_score);

  return (
    <div className="rows">
      <div
        className="row"
        style={{
          gridTemplateColumns: "minmax(0,1.4fr) 64px 56px 56px 56px 64px",
          color: "var(--faint)",
          fontSize: 10.5,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          fontFamily: "var(--font-mono)",
        }}
      >
        <span>테마</span>
        <span style={{ textAlign: "right" }}>Score</span>
        <span style={{ textAlign: "right" }}>News</span>
        <span style={{ textAlign: "right" }}>Price</span>
        <span style={{ textAlign: "right" }}>Flow</span>
        <span style={{ textAlign: "right" }}>Conf</span>
      </div>

      {sorted.map((t) => (
        <div
          key={t.theme_id}
          className="row"
          style={{ gridTemplateColumns: "minmax(0,1.4fr) 64px 56px 56px 56px 64px" }}
        >
          <span className="row-label">
            {t.name}
            {t.data_quality !== "OK" && (
              <span
                className="row-sub"
                style={{ marginLeft: 6 }}
                title={
                  t.breakdown.missing_inputs.length > 0
                    ? `누락: ${t.breakdown.missing_inputs.join(", ")}`
                    : undefined
                }
              >
                {t.data_quality === "INSUFFICIENT" ? "데이터 부족" : "일부 결손"}
              </span>
            )}
          </span>
          <ScoreTooltip breakdown={t.breakdown} label={`${t.name} Score`}>
            <span
              className="num"
              style={{
                ...cellStyle(t.theme_score),
                display: "block",
                textAlign: "right",
                padding: "2px 6px",
                borderRadius: 2,
              }}
            >
              {t.theme_score >= 0 ? "+" : ""}
              {t.theme_score.toFixed(0)}
            </span>
          </ScoreTooltip>
          {[
            ["뉴스 감성", t.news_sentiment],
            ["가격 모멘텀", t.price_momentum],
            ["수급 모멘텀", t.flow_momentum],
          ].map(([label, v]) => (
            <span
              key={label as string}
              className={`num ${v === null ? "" : (v as number) >= 0 ? "up" : "down"}`}
              style={{ textAlign: "right", color: v === null ? "var(--faint)" : undefined }}
              title={
                v === null
                  ? `${label as string}: 측정되지 않음`
                  : `${label as string} ${(v as number).toFixed(1)}`
              }
            >
              {/* 미측정은 0 이 아니다. 빈 값으로 보여야 한다. */}
              {v === null ? "–" : `${(v as number) >= 0 ? "+" : ""}${(v as number).toFixed(0)}`}
            </span>
          ))}
          <ScoreTooltip breakdown={t.confidence_breakdown} label={`${t.name} Confidence`}>
            <span
              className="num"
              style={{
                display: "block",
                textAlign: "right",
                color:
                  t.cross_asset_confirmation === "CONFLICT"
                    ? "var(--crit)"
                    : "var(--muted)",
              }}
              title={`Cross-asset 확인: ${CONFIRM_LABEL[t.cross_asset_confirmation]}`}
            >
              {t.confidence.toFixed(0)}%
            </span>
          </ScoreTooltip>
        </div>
      ))}
    </div>
  );
}
