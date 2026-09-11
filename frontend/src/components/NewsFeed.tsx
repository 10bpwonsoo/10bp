import type { RawNewsItem } from "../api/types";

function ago(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins}분 전`;
  const h = Math.floor(mins / 60);
  return h < 24 ? `${h}시간 전` : `${Math.floor(h / 24)}일 전`;
}

/**
 * 요구 10 의 [WHY] 자리.
 *
 * P0 는 기사 원문만 보여준다. P1 에서 룰 기반 테마 태깅이, P3 에서 LLM
 * 이벤트 추출과 AI 요약이 여기에 더해진다. 지금 구조화된 척하지 않는다.
 */
export function NewsFeed({ items }: { items: RawNewsItem[] }) {
  if (items.length === 0) {
    return (
      <p style={{ margin: 0, padding: 16, color: "var(--muted)" }}>수집된 기사가 없습니다.</p>
    );
  }

  return (
    <div className="rows">
      {items.map((n) => (
        <article key={n.id} className="row" style={{ gridTemplateColumns: "1fr", gap: 3 }}>
          <div style={{ color: "var(--ink)", lineHeight: 1.45 }}>{n.title}</div>
          <div className="row-sub">
            <span className="mono">{ago(n.published_at)}</span>
            {n.publisher ? ` · ${n.publisher}` : ""}
          </div>
        </article>
      ))}
    </div>
  );
}
