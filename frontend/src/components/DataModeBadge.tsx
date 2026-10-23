import type { DataHealth } from "../api/types";

const LABEL: Record<DataHealth["mode"], string> = {
  LIVE: "실시간",
  DELAYED: "지연",
  MOCK: "모의",
};

/**
 * 뉴스를 누가 판단했는가. "LLM disabled" 는 API 경로가 꺼졌다는 말일 뿐이라
 * 수기 판단이 들어갔는지를 말하지 못했다. 세 상태로 나눈다.
 */
const JUDGMENT: Record<DataHealth["news_judgment"], { label: string; color: string }> = {
  none: { label: "뉴스 판단 없음", color: "var(--faint)" },
  manual: { label: "뉴스 판단 수기", color: "var(--warn)" },
  api: { label: "뉴스 판단 API", color: "var(--ok)" },
};

function freshnessSec(sec: number): string {
  if (sec < 60) return `${sec}초 전`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
  const h = Math.floor(sec / 3600);
  return h < 48 ? `${h}시간 전` : `${Math.floor(h / 24)}일 전`;
}

/**
 * 배지의 나이. 가장 오래된 재료가 하루 이상 전 봉이면 **거래일**로 센다 — 금요일 봉을 월요일 아침에
 * "3일 전" 이라 부르지 않기 위해서다. 같은 거래일 안이면 초·분·시간. 옛 캡처(필드 없음)는 초 기준.
 */
export function freshness(health: Pick<DataHealth, "max_freshness_sec" | "max_freshness_trading_days">): string {
  const td = health.max_freshness_trading_days;
  if (td !== undefined && td >= 1) return `${td}거래일 전`;
  return freshnessSec(health.max_freshness_sec);
}

export function freshnessTitle(health: DataHealth): string {
  const parts = [`가장 오래된 재료 기준. 초로는 ${freshnessSec(health.max_freshness_sec)}.`];
  if (health.freshness_note) parts.push(health.freshness_note);
  else if (health.oldest_instruments?.length) parts.push(`해당 계열: ${health.oldest_instruments.join(", ")}`);
  return parts.join("\n");
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
      <span className="num" style={{ fontSize: 11, color: "var(--muted)" }} title={freshnessTitle(health)} data-testid="freshness">
        {freshness(health)}
      </span>
      <span className="num" style={{ fontSize: 11, color: "var(--faint)" }}>
        커버리지 {(health.coverage * 100).toFixed(0)}% ({health.available_instruments}/
        {health.expected_instruments})
      </span>
      <span
        className="num"
        style={{ fontSize: 11, color: JUDGMENT[health.news_judgment].color }}
        title={`${health.news_judgment_note}\nAPI 경로 상태: ${health.llm_status}`}
      >
        {JUDGMENT[health.news_judgment].label}
        {health.llm_status !== "disabled" && health.llm_status !== "ok"
          ? ` · API ${health.llm_status}`
          : ""}
      </span>
    </div>
  );
}
