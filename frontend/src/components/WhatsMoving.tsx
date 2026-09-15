import type { MovingItem } from "../api/types";

/**
 * 요구 10 의 [WHAT'S MOVING].
 *
 * |z| 가 큰 순서다. 수익률 순이 아니다 — 유가 2% 와 금리 2% 는 전혀 다른
 * 사건이고, 자산군을 가로질러 비교하려면 표준화가 필요하다.
 *
 * z 옆에 두 칸을 더 둔다 (GOAL Kickstart 의 표 관례 차용).
 *   · 백분위 — 60일 z 는 "최근 두 달 대비 이례적인가" 만 답한다. "역사적으로
 *     어디 있는가" 는 백분위가 답한다. 10년물 5% 가 z 로는 +0.9σ 지만
 *     백분위로는 98% 인 식이다. 히스토리가 252봉보다 짧으면 그 봉 수를 적는다.
 *   · 3개월 변화 — 거기까지 얼마나 움직여 왔는가.
 * 막대 위의 ◇ 는 1주 전 그 시점의 z 다.
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
      <div className="row moving-row moving-head">
        <span />
        <span>변수</span>
        <span style={{ textAlign: "right" }}>z</span>
        <span style={{ textAlign: "right" }}>1일</span>
        <span className="moving-extra" style={{ textAlign: "right" }} title="장기 백분위 (최대 252봉)">
          %ile
        </span>
        <span className="moving-extra" style={{ textAlign: "right" }} title="63봉(≈3개월) 변화">
          3개월
        </span>
        <span className="moving-extra" title="막대 = 오늘 z · ◇ = 1주 전 z">
          ◇ 1주 전
        </span>
      </div>
      {items.map((m) => {
        const z = m.z ?? 0;
        const pct = (Math.abs(z) / max) * 50;
        const ghost = m.z_week_ago !== null ? 50 + (m.z_week_ago / max) * 50 : null;
        const pctile = m.percentile;
        const pctTitle =
          pctile === null
            ? "백분위: 히스토리가 짧아 계산하지 못함"
            : `최근 ${m.percentile_observations}봉 안에서 ${pctile.toFixed(0)}번째 백분위` +
              (m.percentile_observations < 252 ? " (1년치가 안 된다)" : "");
        return (
          <div key={m.key} className="row moving-row">
            <span className={m.direction} aria-hidden="true">
              {m.arrow}
            </span>
            <span className="row-label" title={m.key}>
              {m.label}
              {/* 좁은 화면에서는 열 대신 한 줄 요약으로 */}
              <span className="moving-sub mono">
                {pctile !== null ? `${pctile.toFixed(0)}%ile` : ""}
                {m.change_3m !== null ? ` · 3개월 ${m.change_3m_display}` : ""}
                {m.z_week_ago !== null
                  ? ` · 1주 전 ${m.z_week_ago >= 0 ? "+" : ""}${m.z_week_ago.toFixed(1)}σ`
                  : ""}
              </span>
            </span>
            <span className={`num ${m.direction}`} style={{ textAlign: "right" }}>
              {z >= 0 ? "+" : ""}
              {z.toFixed(2)}σ
            </span>
            <span className="num" style={{ textAlign: "right", color: "var(--ink-2)" }}>
              {m.change_display}
            </span>
            <span
              className="num moving-extra"
              style={{ textAlign: "right", color: pctile === null ? "var(--faint)" : "var(--ink-2)" }}
              title={pctTitle}
            >
              {pctile === null ? "–" : `${pctile.toFixed(0)}%`}
              {pctile !== null && m.percentile_observations < 252 && (
                <span style={{ color: "var(--faint)", fontSize: 9 }}>
                  {" "}/{m.percentile_observations}
                </span>
              )}
            </span>
            <span
              className="num moving-extra"
              style={{ textAlign: "right", color: m.change_3m === null ? "var(--faint)" : "var(--ink-2)" }}
              title="63봉(≈3개월) 변화"
            >
              {m.change_3m === null ? "–" : m.change_3m_display}
            </span>
            {/* 중앙을 0 으로 두는 발산형 막대. 부호가 위치로도 읽힌다. */}
            <span
              aria-hidden="true"
              className="bar moving-extra"
              title={
                m.z_week_ago === null
                  ? "1주 전 z: 히스토리가 짧아 없음"
                  : `1주 전 z ${m.z_week_ago >= 0 ? "+" : ""}${m.z_week_ago.toFixed(2)}σ`
              }
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
              {ghost !== null && (
                <span
                  className="ghost-mark"
                  style={{ left: `${Math.max(0, Math.min(100, ghost))}%` }}
                />
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}
