import type { StateHypothesis } from "../api/types";

/**
 * 어떤 룰이 발동했는지 그대로 보여준다.
 *
 * 요구 14 의 "어떤 rule 에 의해 발생했는지 확인할 수 있어야 한다" 에 대한
 * 답이다. 판정을 믿을지 말지는 운용자가 이 목록을 보고 정한다.
 */
export function RuleTrace({ hypothesis }: { hypothesis: StateHypothesis }) {
  return (
    <div className="rules">
      {hypothesis.matched_rules.map((r) => {
        const cls = !r.evaluable ? "unknown" : r.passed ? "pass" : "fail";
        const mark = !r.evaluable ? "?" : r.passed ? "✓" : "·";
        return (
          <div className="rule" key={r.rule_id}>
            <span className={`rule-mark ${cls}`} aria-hidden="true">
              {mark}
            </span>
            <span className="rule-kind">{r.kind}</span>
            <span className="mono" style={{ color: "var(--ink-2)" }}>
              {r.expression}
            </span>
            <span className="num" style={{ textAlign: "right", color: "var(--muted)" }}>
              {r.observed === null
                ? "데이터 없음"
                : `${r.observed >= 0 ? "+" : ""}${r.observed.toFixed(2)}`}
            </span>
          </div>
        );
      })}
    </div>
  );
}
