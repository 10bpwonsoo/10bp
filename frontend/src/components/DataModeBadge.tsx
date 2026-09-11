import type { DataHealth } from "../api/types";

const LABEL: Record<DataHealth["mode"], string> = {
  LIVE: "실시간",
  DELAYED: "지연",
  MOCK: "모의",
};

function freshness(sec: number): string {
  if (sec < 60) return `${sec}초 전`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
  const h = Math.floor(sec / 3600);
  return h < 48 ? `${h}시간 전` : `${Math.floor(h / 24)}일 전`;
}

/**
 * 데이터 모드와 신선도를 항상 표시한다.
 *
 * 지연된 데이터를 실시간이라 부르지 않는 것이 이 시스템의 약속이다
 * (설계서 STEP 7.2). 데이터의 나이를 숨기는 도구는 한 번 들키면 다시
 * 쓰이지 않는다.
 */
export function DataModeBadge({
  health,
  scenario,
}: {
  health: DataHealth;
  scenario: string | null;
}) {
  const cls =
    health.mode === "LIVE"
      ? "badge-live"
      : health.mode === "DELAYED"
        ? "badge-delayed"
        : "badge-mock";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      <span className={`badge ${cls}`}>
        <span className="dot" />
        {LABEL[health.mode]}
        {scenario ? ` · ${scenario}` : ""}
      </span>
      <span className="num" style={{ fontSize: 11, color: "var(--muted)" }}>
        {freshness(health.max_freshness_sec)}
      </span>
      <span className="num" style={{ fontSize: 11, color: "var(--faint)" }}>
        커버리지 {(health.coverage * 100).toFixed(0)}% ({health.available_instruments}/
        {health.expected_instruments})
      </span>
      <span
        className="num"
        style={{
          fontSize: 11,
          color: health.llm_status === "disabled" ? "var(--faint)" : "var(--ok)",
        }}
      >
        LLM {health.llm_status}
      </span>
    </div>
  );
}
