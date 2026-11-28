import type { DataHealth } from "../api/types";

/** 요구 12 의 메타데이터를 숨기지 않고 그대로 보여준다. */
/**
 * 661701초 는 사람이 못 읽는다. 지연은 판단에 직접 쓰이는 숫자라
 * 한눈에 들어와야 한다.
 */
function humanAge(seconds: number): string {
  if (seconds < 90) return `${seconds}초`;
  const minutes = seconds / 60;
  if (minutes < 90) return `${minutes.toFixed(0)}분`;
  const hours = minutes / 60;
  if (hours < 48) return `${hours.toFixed(1)}시간`;
  return `${(hours / 24).toFixed(1)}일`;
}

export function DataHealthPanel({
  health,
  versions,
}: {
  health: DataHealth;
  versions: Record<string, string>;
}) {
  const totalMs = Object.values(health.engine_timings_ms).reduce((a, b) => a + b, 0);

  const rows: Array<[string, string]> = [
    ["모드", health.mode],
    [
      "커버리지",
      `${(health.coverage * 100).toFixed(0)}% (${health.available_instruments}/${health.expected_instruments})`,
    ],
    [
      "최대 지연",
      health.max_freshness_trading_days !== undefined && health.max_freshness_trading_days >= 1
        ? `${health.max_freshness_trading_days}거래일 (${humanAge(health.max_freshness_sec)})`
        : humanAge(health.max_freshness_sec),
    ],
    ["기사 수", String(health.news_items)],
    ["LLM", health.llm_status],
    ["파이프라인", `${totalMs.toFixed(0)}ms`],
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <dl
        style={{
          margin: 0,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(118px, 1fr))",
          gap: "10px 14px",
        }}
      >
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt
              className="mono"
              style={{
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--faint)",
              }}
            >
              {k}
            </dt>
            <dd className="num" style={{ margin: 0, color: "var(--ink-2)" }}>
              {v}
            </dd>
          </div>
        ))}
      </dl>

      <div className="mono" style={{ fontSize: 11, color: "var(--faint)" }}>
        {Object.entries(health.engine_timings_ms)
          .map(([k, v]) => `${k} ${v.toFixed(0)}ms`)
          .join("   ")}
      </div>

      {health.missing.length > 0 && (
        <div style={{ fontSize: 12, color: "var(--warn)" }}>
          미확보 {health.missing.length}건: {health.missing.slice(0, 6).join(", ")}
          {health.missing.length > 6 ? " …" : ""}
        </div>
      )}

      {health.stale.length > 0 && (
        <div style={{ fontSize: 12, color: "var(--warn)" }}>
          오래된 데이터 {health.stale.length}건: {health.stale.slice(0, 6).join(", ")}
        </div>
      )}

      {health.warnings.map((w) => (
        <div key={w} style={{ fontSize: 12, color: "var(--warn)" }}>
          {w}
        </div>
      ))}

      <div className="mono" style={{ fontSize: 10.5, color: "var(--faint)" }}>
        {Object.entries(versions)
          .map(([k, v]) => `${k}@${v}`)
          .join("  ")}
      </div>
    </div>
  );
}
