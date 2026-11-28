import type { Alert, AlertType, SeverityBand } from "../api/types";
import { Pending } from "./Panel";

const BAND_COLOR: Record<SeverityBand, string> = {
  CRITICAL: "var(--crit)",
  HIGH: "var(--warn)",
  MEDIUM: "var(--info)",
  LOW: "var(--faint)",
};

const TYPE_LABEL: Record<AlertType, string> = {
  STATE_CHANGE: "상태 전환",
  DIVERGENCE_OPENED: "괴리 발생",
  VOL_SPIKE: "변동성 급등",
  PRICE_ZSCORE_SPIKE: "가격 급변",
  FLOW_REVERSAL: "수급 전환",
  THEME_SENTIMENT_SPIKE: "테마 급변",
  NEWS_VOLUME_SPIKE: "뉴스량 급증",
  DATA_QUALITY: "데이터 품질",
};

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("ko-KR", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * 요구 9 의 [ALERT / TIMELINE].
 *
 * 모든 알림이 baseline 과 delta 를 들고 있다. 수준이 아니라 변화를 보기
 * 때문이고, 스키마가 그것을 필수로 요구한다. 화면에도 "무엇이 얼마에서
 * 얼마로" 를 그대로 적는다.
 */
export function AlertTimeline({ items }: { items: Alert[] }) {
  // 해소된 알림도 보존 창 동안 남긴다. 타임라인은 '지금 참인 것' 이 아니라
  // '최근에 일어난 일' 의 기록이다. 다만 흐리게 그려 구분한다.
  const rows = [...items].sort(
    (a, b) => new Date(b.last_fired_at).getTime() - new Date(a.last_fired_at).getTime(),
  );

  if (rows.length === 0) {
    return (
      <Pending stage="관측 중">
        임계 이상으로 변한 항목이 없습니다. 직전 틱과 비교해 변화를 보므로
        최소 두 틱이 쌓여야 알림이 발생합니다.
      </Pending>
    );
  }

  return (
    <div className="rows">
      {rows.map((a) => {
        const done = a.state === "RESOLVED";
        return (
        <article
          key={a.id}
          className="row"
          style={{ gridTemplateColumns: "1fr", gap: 5, opacity: done ? 0.5 : 1 }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--faint)" }}>
              {time(a.last_fired_at)}
            </span>
            <span
              className="badge"
              style={{ color: BAND_COLOR[a.severity_band], fontSize: 9.5, padding: "1px 6px" }}
            >
              {TYPE_LABEL[a.type]}
            </span>
            <span style={{ color: "var(--ink)", fontSize: 12.5 }}>{a.title}</span>
            {done && (
              <span className="mono" style={{ fontSize: 10, color: "var(--faint)" }}>
                해소
              </span>
            )}
            {a.fire_count > 1 && (
              <span
                className="num"
                style={{ marginLeft: "auto", fontSize: 10.5, color: "var(--faint)" }}
                title="중복 억제되어 발화 횟수만 증가했습니다"
              >
                ×{a.fire_count}
              </span>
            )}
          </div>

          {/* 기준선이 없는 알림은 스키마가 허용하지 않는다. 그것을 그대로 보인다. */}
          <div className="num" style={{ fontSize: 11, color: "var(--muted)" }}>
            {a.trigger.metric} · {a.trigger.baseline.toFixed(1)} →{" "}
            {a.trigger.current.toFixed(1)}
            <span style={{ color: a.trigger.delta >= 0 ? "var(--up)" : "var(--down)" }}>
              {" "}
              ({a.trigger.delta >= 0 ? "+" : ""}
              {a.trigger.delta.toFixed(1)}
              {a.trigger.delta_pct !== null
                ? `, ${a.trigger.delta_pct >= 0 ? "+" : ""}${a.trigger.delta_pct.toFixed(0)}%`
                : ""}
              )
            </span>
          </div>
        </article>
        );
      })}
    </div>
  );
}
