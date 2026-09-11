import type { MarketState } from "../api/types";
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

/** 요구 10 의 [TOP] MARKET STATE. 운용자가 가장 먼저 보는 한 줄. */
export function MarketStateHeader({ state }: { state: MarketState }) {
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
      </div>

      {state.main_drivers.length > 0 && (
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          {state.main_drivers.map((d) => (
            <div key={d.instrument_id} style={{ display: "flex", gap: 7, alignItems: "baseline" }}>
              <span className={d.direction}>{d.arrow}</span>
              <span style={{ color: "var(--ink-2)" }}>{d.label}</span>
              <span className={`num ${d.direction}`}>{d.z >= 0 ? "+" : ""}{d.z.toFixed(1)}σ</span>
            </div>
          ))}
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
