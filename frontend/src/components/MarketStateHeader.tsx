import type { AxisLink, CalendarEvent, EventWindow, MarketState } from "../api/types";
import { Pending } from "./Panel";
import { RuleTrace } from "./RuleTrace";
import { ScoreTooltip } from "./ScoreTooltip";

const LABEL_KO: Record<string, string> = {
  RISK_ON: "Risk-On",
  RISK_OFF: "Risk-Off",
  GROWTH_SHOCK: "Growth Shock",
  INFLATION_SHOCK: "Inflation Shock",
  LIQUIDITY_STRESS: "Liquidity Stress",
  POLICY_DRIVEN: "Policy Driven",
  GEOPOLITICAL_RISK: "Geopolitical Risk",
  NEUTRAL: "판정 없음",
};

function sz(v: number, digits = 1): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;
}

/** D-day 표기. D-2 / D-day / D+1. */
function dday(e: CalendarEvent): string {
  if (e.days_until === null) return "";
  if (e.days_until === 0) return "D-day";
  return e.days_until > 0 ? `D-${e.days_until}` : `D+${-e.days_until}`;
}

/**
 * 이벤트 창 표식 (GOAL Kickstart 의 '중앙은행 주간' 프레이밍).
 *
 * 창 안이면 무엇이 얼마나 조정됐는지 그대로 적는다 — 판정은 그대로고
 * 확신과 알림 민감도만 바뀐 것이므로 그 사실이 보여야 한다. 미확인 날짜는
 * '(미확인)' 을 붙인다. 불확실한 것을 확정처럼 보이게 하지 않는다.
 */
function CalendarBadge({ calendar }: { calendar: EventWindow | null }) {
  if (!calendar) return null;
  if (calendar.active) {
    return (
      <span className="cal-badge cal-active" title={calendar.note}>
        <span className="cal-k">이벤트 창</span>
        {calendar.in_window.map((e) => (
          <span key={e.id} className="mono">
            {e.label} {dday(e)}
            {!e.verified ? <span className="cal-unverified"> (미확인)</span> : null}
          </span>
        ))}
        <span className="cal-adj mono">
          지속성 ×{calendar.persistence_scale.toFixed(2)} · 알림 임계 ×
          {calendar.alert_threshold_scale.toFixed(2)}
        </span>
      </span>
    );
  }
  const next = calendar.upcoming[0];
  if (!next) return null;
  return (
    <span className="cal-badge mono" title={calendar.note}>
      다음 이벤트 {next.label} {next.date.slice(5).replace("-", "/")} {dday(next)}
      {!next.verified ? <span className="cal-unverified"> (미확인)</span> : null}
    </span>
  );
}

function AxisLinks({ rows, sign }: { rows: AxisLink[]; sign: "+" | "−" }) {
  if (rows.length === 0) return null;
  return (
    <span className="axis-links">
      <span className="axis-k">{sign === "+" ? "같은 방향" : "반대 방향"}</span>
      {rows.map((l) => (
        <span
          key={l.instrument_id}
          className="mono axis-link"
          title={
            `${l.label} 60일 변화량 상관 ${sz(l.corr, 2)}` +
            (l.prior !== null ? ` · 한 분기 전 ${sz(l.prior, 2)}` : "") +
            (l.z !== null ? ` · 오늘 ${sz(l.z)}σ` : "")
          }
        >
          {l.label} <span style={{ color: l.corr >= 0 ? "var(--up)" : "var(--down)" }}>{sz(l.corr, 2)}</span>
        </span>
      ))}
    </span>
  );
}

/** 요구 10 의 [TOP] MARKET STATE. 운용자가 가장 먼저 보는 한 줄. */
export function MarketStateHeader({
  state,
  calendar = null,
}: {
  state: MarketState;
  calendar?: EventWindow | null;
}) {
  const evaluated = Object.keys(state.factors).length > 0;

  if (!evaluated) {
    return (
      <Pending stage="P1">
        MarketStateEngine 이 붙으면 여기에 Risk-Off / Inflation Shock 같은 판정과
        confidence, 그리고 그 판정을 만든 factor 기여도가 표시됩니다. 지금은
        정량 데이터만 수집되어 있어 라벨을 붙이지 않습니다.
      </Pending>
    );
  }

  const label = LABEL_KO[state.primary_label] ?? state.primary_label;
  const second = state.secondary_label ? LABEL_KO[state.secondary_label] : null;
  const ranked = state.hypotheses.filter((h) => h.score > 0);
  const top = ranked[0];
  const passed = top ? top.matched_rules.filter((r) => r.passed).length : 0;
  const axis = state.dominant_axis;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 26, letterSpacing: "-0.02em" }}>
          {label}
          {second ? <span style={{ color: "var(--muted)" }}> / {second}</span> : null}
        </strong>
        <ScoreTooltip breakdown={state.confidence_breakdown} label="Confidence 계산 근거">
          <span className="num" style={{ color: "var(--muted)", fontSize: 13 }}>
            Confidence {state.confidence.toFixed(0)}%
          </span>
        </ScoreTooltip>
        <span
          className="num"
          style={{ fontSize: 11, color: "var(--faint)" }}
          title={state.cross_asset_confirmation.note}
        >
          Cross-asset {state.cross_asset_confirmation.verdict}
        </span>
        <CalendarBadge calendar={calendar} />
      </div>

      {state.main_drivers.length > 0 && (
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          {state.main_drivers.map((d) => (
            <div
              key={d.instrument_id}
              style={{ display: "flex", gap: 7, alignItems: "baseline" }}
              title={
                (d.z_week_ago !== null ? `1주 전 ${sz(d.z_week_ago)}σ` : "1주 전 값 없음") +
                (d.percentile !== null
                  ? ` · 최근 ${d.percentile_observations}봉 백분위 ${d.percentile.toFixed(0)}%`
                  : "")
              }
            >
              <span className={d.direction}>{d.arrow}</span>
              <span style={{ color: "var(--ink-2)" }}>{d.label}</span>
              <span className={`num ${d.direction}`}>{sz(d.z)}σ</span>
              {/* 60일 z 옆의 장기 백분위. z 는 '최근 두 달 대비', 백분위는
                  '역사 속 위치' 다. 둘이 다를 때가 가장 정보가 많다. */}
              {d.percentile !== null && (
                <span className="num" style={{ fontSize: 10.5, color: "var(--faint)" }}>
                  {d.percentile.toFixed(0)}%ile
                </span>
              )}
              {d.z_week_ago !== null && (
                <span className="num" style={{ fontSize: 10.5, color: "var(--faint)" }}>
                  ◇{sz(d.z_week_ago)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 지배 축 (GOAL Kickstart Exhibit 4). 무엇이 흔들었고 무엇이 따라
          움직이는가. 상관이지 인과가 아니므로 문장도 그렇게 쓴다. */}
      {axis && (
        <div className="axis" title={axis.note}>
          <span className="axis-head">
            <span className="axis-k">지배 축</span>
            <span className={axis.z >= 0 ? "up" : "down"}>{axis.arrow}</span>
            <span style={{ color: "var(--ink)" }}>{axis.label}</span>
            <span className={`num ${axis.z >= 0 ? "up" : "down"}`}>{sz(axis.z)}σ</span>
            {axis.z_week_ago !== null && (
              <span className="num" style={{ fontSize: 10.5, color: "var(--faint)" }}>
                ◇{sz(axis.z_week_ago)}
              </span>
            )}
            <span className="mono" style={{ fontSize: 10, color: "var(--faint)" }}>
              {axis.window}일 상관
            </span>
          </span>
          <AxisLinks rows={axis.positive} sign="+" />
          <AxisLinks rows={axis.negative} sign="−" />
          {axis.positive.length === 0 && axis.negative.length === 0 && (
            <span style={{ fontSize: 11.5, color: "var(--muted)" }}>
              ±0.3 을 넘는 연동 자산이 없다 — 이 축은 아직 혼자 움직이고 있다.
            </span>
          )}
        </div>
      )}

      {top && top.score > 0 ? (
        <details>
          <summary
            style={{
              cursor: "pointer",
              color: "var(--muted)",
              fontSize: 12,
              marginBottom: 8,
            }}
          >
            발동 룰 {passed}/{top.matched_rules.length} · 후보 판정 {ranked.length}건
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <RuleTrace hypothesis={top} />
            {ranked.length > 1 && (
              <div style={{ fontSize: 12, color: "var(--muted)" }}>
                다음 후보:{" "}
                {ranked
                  .slice(1, 4)
                  .map((h) => `${LABEL_KO[h.label] ?? h.label} ${h.score.toFixed(2)}`)
                  .join(" · ")}
              </div>
            )}
          </div>
        </details>
      ) : null}

      {state.narrative ? (
        <p style={{ margin: 0, color: "var(--ink-2)", maxWidth: "70ch" }}>
          {state.narrative}
          <span style={{ color: "var(--faint)", fontSize: 11, marginLeft: 8 }}>
            ({state.narrative_source === "llm" ? "AI 요약" : "템플릿"})
          </span>
        </p>
      ) : null}
    </div>
  );
}
