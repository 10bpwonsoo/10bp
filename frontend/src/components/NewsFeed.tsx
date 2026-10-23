import type { NewsEventLite } from "../api/types";

function ago(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins}분 전`;
  const h = Math.floor(mins / 60);
  return h < 24 ? `${h}시간 전` : `${Math.floor(h / 24)}일 전`;
}

const EXTRACTOR_LABEL: Record<NewsEventLite["extractor"], string> = {
  rule: "룰",
  llm: "AI",
  manual: "수기",
};

/**
 * 요구 10 의 [WHY].
 *
 * 기사마다 어떤 테마로 읽혔고 그 테마에 대해 어느 방향인지 보여준다.
 * extractor 배지가 이 구조화가 룰에서 나왔는지 LLM 에서 나왔는지 밝힌다 —
 * LLM 추론과 사전 정의를 구분해 두는 것이 이 시스템의 약속이다.
 */
export function NewsFeed({ events }: { events: NewsEventLite[] }) {
  if (events.length === 0) {
    return (
      <p style={{ margin: 0, padding: 16, color: "var(--muted)" }}>수집된 기사가 없습니다.</p>
    );
  }

  return (
    <div className="rows">
      {events.map((e) => {
        const tags = Object.entries(e.theme_sentiment);
        return (
          <article key={e.id} className="row" style={{ gridTemplateColumns: "1fr", gap: 5 }}>
            <div style={{ color: "var(--ink)", lineHeight: 1.45 }}>
              {e.url ? (
                <a href={e.url} target="_blank" rel="noopener noreferrer" className="news-link">
                  {e.event}
                </a>
              ) : (
                e.event
              )}
            </div>

            {tags.length > 0 && (
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                {tags.map(([theme, s]) => (
                  <span
                    key={theme}
                    className="mono"
                    style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      borderRadius: 2,
                      border: "1px solid var(--rule)",
                      color: s > 5 ? "var(--up)" : s < -5 ? "var(--down)" : "var(--muted)",
                    }}
                    title={`${theme} 감성 ${s}`}
                  >
                    {theme} {s >= 0 ? "+" : ""}
                    {s}
                  </span>
                ))}
              </div>
            )}

            <div className="row-sub">
              <span className="mono">{ago(e.timestamp)}</span>
              {e.source ? ` · ${e.source}` : ""}
              {` · 영향도 ${e.impact_score}`}
              <span
                style={{ marginLeft: 6, color: "var(--faint)" }}
                title={e.reason}
              >
                추출 {EXTRACTOR_LABEL[e.extractor]} (신뢰도 {(e.confidence * 100).toFixed(0)}%)
              </span>
            </div>
          </article>
        );
      })}
    </div>
  );
}
