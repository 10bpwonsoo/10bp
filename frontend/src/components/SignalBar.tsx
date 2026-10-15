/**
 * -100 ~ +100 신호를 중앙 0 기준의 발산형 막대로.
 * null 은 '측정되지 않음' 이라 막대를 그리지 않는다.
 */
export function SignalBar({ value, height = 6 }: { value: number | null; height?: number }) {
  if (value === null) {
    return (
      <span
        aria-hidden="true"
        style={{
          display: "block",
          height,
          background: "var(--surface-2)",
          borderRadius: 1,
          opacity: 0.4,
        }}
      />
    );
  }
  const pct = (Math.min(Math.abs(value), 100) / 100) * 50;
  return (
    <span
      aria-hidden="true"
      style={{ position: "relative", display: "block", height, background: "var(--surface-2)", borderRadius: 1 }}
    >
      <span
        style={{
          position: "absolute",
          top: 0,
          bottom: 0,
          left: value >= 0 ? "50%" : `${50 - pct}%`,
          width: `${pct}%`,
          background: value >= 0 ? "var(--up)" : "var(--down)",
          borderRadius: 1,
        }}
      />
      <span
        style={{
          position: "absolute",
          left: "50%",
          top: -1,
          bottom: -1,
          width: 1,
          background: "var(--rule)",
        }}
      />
    </span>
  );
}
