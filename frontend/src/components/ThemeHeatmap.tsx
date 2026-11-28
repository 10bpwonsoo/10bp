import { useMemo, useState } from "react";
import type { NewsEventLite, ThemeState } from "../api/types";
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

const EXTRACTOR_LABEL: Record<NewsEventLite["extractor"], string> = {
  rule: "룰",
  llm: "AI",
  manual: "수기",
};

/** 행을 펼쳤을 때 보여줄 기사 수. 더 많으면 목록이 되고 히트맵이 아니다. */
const RELATED_LIMIT = 4;

function ago(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins}분 전`;
  const h = Math.floor(mins / 60);
  return h < 24 ? `${h}시간 전` : `${Math.floor(h / 24)}일 전`;
}

/**
 * 테마별 관련 기사. 그 테마가 태그된 기사 중 영향도가 큰 것부터,
 * 같은 영향도면 최신 순. 테마 점수를 만든 실제 재료이지 검색 결과가 아니다.
 */
function relatedEvents(events: NewsEventLite[], themeId: string): NewsEventLite[] {
  return events
    .filter((e) => e.themes.includes(themeId))
    .sort(
      (a, b) =>
        b.impact_score - a.impact_score ||
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    )
    .slice(0, RELATED_LIMIT);
}

export function ThemeHeatmap({
  themes,
  events = [],
}: {
  themes: ThemeState[];
  events?: NewsEventLite[];
}) {
  const [open, setOpen] = useState<string | null>(null);
  const byTheme = useMemo(() => {
    const m = new Map<string, NewsEventLite[]>();
    for (const t of themes) m.set(t.theme_id, relatedEvents(events, t.theme_id));
    return m;
  }, [themes, events]);

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
        className="row heat-row heat-head"
        style={{
          color: "var(--faint)",
          fontSize: 10.5,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          fontFamily: "var(--font-mono)",
        }}
      >
        <span>
          테마<span className="heat-hint"> · 누르면 관련 기사</span>
        </span>
        <span style={{ textAlign: "right" }}>Score</span>
        <span style={{ textAlign: "right" }} title="1주 전 저장 스냅샷 대비 점수 변화">
          Δ1w
        </span>
        <span style={{ textAlign: "right" }}>News</span>
        <span style={{ textAlign: "right" }}>Price</span>
        <span style={{ textAlign: "right" }}>Conf</span>
      </div>

      {sorted.map((t) => {
        const related = byTheme.get(t.theme_id) ?? [];
        const isOpen = open === t.theme_id;
        const count = events.filter((e) => e.themes.includes(t.theme_id)).length;
        return (
          <div key={t.theme_id}>
            <div
              className="row row-toggle heat-row"
              role="button"
              tabIndex={0}
              aria-expanded={isOpen}
              aria-controls={`theme-news-${t.theme_id}`}
              onClick={() => setOpen(isOpen ? null : t.theme_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setOpen(isOpen ? null : t.theme_id);
                }
              }}
            >
              <span className="row-label">
                <span
                  className="mono"
                  aria-hidden="true"
                  style={{ color: "var(--faint)", marginRight: 6, fontSize: 9 }}
                >
                  {isOpen ? "▾" : "▸"}
                </span>
                {t.name}
                {count > 0 && (
                  <span
                    className="mono"
                    style={{ marginLeft: 6, fontSize: 10, color: "var(--faint)" }}
                    title={`${count}건의 기사가 이 테마로 태그됨`}
                  >
                    {count}
                  </span>
                )}
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
              {/* 점수 셀은 툴팁을 열어야 하므로 행 토글로 전파되지 않게 한다 */}
              <span onClick={(e) => e.stopPropagation()}>
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
              </span>
              {/* 1주 전 대비 (GOAL Kickstart 의 'Latest vs 1-week ago' 관례).
                  저장된 1주 전 스냅샷이 없으면 빈 칸이다 — 0 이 아니다. */}
              {(() => {
                const d = t.week_ago_score === null ? null : t.theme_score - t.week_ago_score;
                return (
                  <span
                    className={`num ${d === null ? "" : d >= 0 ? "up" : "down"}`}
                    style={{ textAlign: "right", color: d === null ? "var(--faint)" : undefined }}
                    title={
                      d === null
                        ? "1주 전 저장 스냅샷이 없어 비교하지 못함"
                        : `1주 전 ${t.week_ago_score!.toFixed(0)} → 지금 ${t.theme_score.toFixed(0)}`
                    }
                  >
                    {d === null ? "–" : `${d >= 0 ? "+" : ""}${d.toFixed(0)}`}
                  </span>
                );
              })()}
              {/* 수급 열은 뺐다 — 무료 공급자가 없어 항상 결측이었고, 그 역할은
                  뉴스 감성이 맡는다 (scoring.yaml theme.use_flow). */}
              {[
                ["뉴스 감성", t.news_sentiment],
                ["가격 모멘텀", t.price_momentum],
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
              <span onClick={(e) => e.stopPropagation()}>
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
              </span>
            </div>

            {isOpen && (
              <div className="theme-news" id={`theme-news-${t.theme_id}`}>
                {related.length === 0 ? (
                  <div className="theme-news-empty">
                    이 테마로 태그된 기사가 없습니다. News 열이 <span className="mono">–</span> 인
                    이유가 이것입니다.
                  </div>
                ) : (
                  related.map((e) => {
                    const s = e.theme_sentiment[t.theme_id];
                    const dir = e.theme_direction[t.theme_id];
                    return (
                      <div key={e.id} className="theme-news-row">
                        <span
                          className={`theme-news-sent ${s === undefined ? "" : s >= 0 ? "up" : "down"}`}
                          title={
                            s === undefined
                              ? "이 테마의 감성 없음"
                              : `${t.name} 감성 ${s >= 0 ? "+" : ""}${s}${dir ? ` · 방향 ${dir}` : ""}`
                          }
                        >
                          {s === undefined ? "–" : `${s >= 0 ? "+" : ""}${s}`}
                        </span>
                        <span>
                          <div className="theme-news-title">
                            {e.url ? (
                              <a href={e.url} target="_blank" rel="noopener noreferrer" className="news-link">
                                {e.event}
                              </a>
                            ) : (
                              e.event
                            )}
                          </div>
                          <div className="theme-news-meta">
                            {ago(e.timestamp)}
                            {e.source ? ` · ${e.source}` : ""}
                            {` · 영향도 ${e.impact_score}`}
                            {` · ${EXTRACTOR_LABEL[e.extractor]}`}
                          </div>
                        </span>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
