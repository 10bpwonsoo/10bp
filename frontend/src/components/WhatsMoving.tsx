import type { MovingItem } from "../api/types";

/**
 * 요구 10 의 [WHAT'S MOVING].
 *
 * |z| 가 큰 순서다. 수익률 순이 아니다 — 유가 2% 와 금리 2% 는 전혀 다른
 * 사건이고, 자산군을 가로질러 비교하려면 표준화가 필요하다.
 */
export function WhatsMoving({ items }: { items: MovingItem[] }) {
  if (items.length === 0) {
    return (
      <p style={{ margin: 0, padding: "16px", color: "var(--muted)" }}>
        임계(0.5σ) 이상으로 움직인 변수가 없습니다.
      </p>
    );
  }

  const max = Math.max(...items.map((i) => Math.abs(i.z ?? 0)), 1);

  return (
    <div className="rows">
      {items.map((m) => {
        const z = m.z ?? 0;
        const pct = (Math.abs(z) / max) * 50;
        return (
          <div
            key={m.key}
            className="row"
            style={{ gridTemplateColumns: "20px minmax(0,1fr) 68px 84px 1fr" }}
          >
            <span className={m.direction} aria-hidden="true">
              {m.arrow}
            </span>
            <span className="row-label" title={m.key}>
              {m.label}
            </span>
            <span className={`num ${m.direction}`} style={{ textAlign: "right" }}>
              {z >= 0 ? "+" : ""}
              {z.toFixed(2)}σ
            </span>
            <span className="num" style={{ textAlign: "right", color: "var(--ink-2)" }}>
              {m.change_display}
            </span>
            {/* 중앙을 0 으로 두는 발산형 막대. 부호가 위치로도 읽힌다. */}
            <span
              aria-hidden="true"
              className="bar"
              style={{
                position: "relative",
                height: 6,
                background: "var(--surface-2)",
                borderRadius: 1,
                minWidth: 60,
              }}
            >
              <span
                style={{
                  position: "absolute",
                  top: 0,
                  bottom: 0,
                  left: z >= 0 ? "50%" : `${50 - pct}%`,
                  width: `${pct}%`,
                  background: z >= 0 ? "var(--up)" : "var(--down)",
                  borderRadius: 1,
                }}
              />
              <span
                style={{
                  position: "absolute",
                  left: "50%",
                  top: -2,
                  bottom: -2,
                  width: 1,
                  background: "var(--rule)",
                }}
              />
            </span>
          </div>
        );
      })}
    </div>
  );
}
