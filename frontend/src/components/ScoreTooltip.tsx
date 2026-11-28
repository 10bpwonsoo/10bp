import type { ReactNode } from "react";
import type { ScoreBreakdown } from "../api/types";

/**
 * 점수의 계산 근거를 보여준다.
 *
 * 요구 15-6 "모든 주요 score 는 계산 근거를 추적 가능하게 한다" 의 UI 쪽
 * 끝단이다. 백엔드가 모든 점수와 함께 ScoreBreakdown 을 내려주므로 여기서는
 * 그것을 펼쳐 보이기만 하면 된다.
 *
 * 마우스와 키보드 모두로 열린다. 트레이딩 데스크에서 키보드만 쓰는 경우가
 * 드물지 않다.
 */
export function ScoreTooltip({
  breakdown,
  children,
  label,
}: {
  breakdown: ScoreBreakdown | null;
  children: ReactNode;
  label?: string;
}) {
  if (!breakdown) return <>{children}</>;

  const sorted = [...breakdown.contributions].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  );

  return (
    <span className="tip">
      <span className="tip-trigger" tabIndex={0} role="button" aria-label={label ?? "계산 근거 보기"}>
        {children}
      </span>
      <span className="tip-panel" role="tooltip">
        <span className="tip-head">
          {label ? <strong>{label}</strong> : null}
          <span className="mono">{breakdown.method}</span>
        </span>

        {sorted.length === 0 ? (
          <span className="tip-empty">기여 항목이 없습니다.</span>
        ) : (
          <span className="tip-rows">
            <span className="tip-row tip-row-head">
              <span>항목</span>
              <span>표준화</span>
              <span>가중</span>
              <span>기여</span>
            </span>
            {sorted.map((c) => (
              <span className="tip-row" key={c.key}>
                <span title={c.note}>{c.key}</span>
                <span className={`num ${c.normalized >= 0 ? "up" : "down"}`}>
                  {c.normalized >= 0 ? "+" : ""}
                  {c.normalized.toFixed(2)}
                </span>
                <span className="num">{c.weight >= 0 ? "+" : ""}{c.weight.toFixed(2)}</span>
                <span className={`num ${c.contribution >= 0 ? "up" : "down"}`}>
                  {c.contribution >= 0 ? "+" : ""}
                  {c.contribution.toFixed(3)}
                </span>
              </span>
            ))}
          </span>
        )}

        {breakdown.missing_inputs.length > 0 && (
          <span className="tip-missing">
            결측 {breakdown.missing_inputs.length}건 ({breakdown.missing_inputs.join(", ")})
            — 0으로 채우지 않고 가중치를 재정규화했습니다.
          </span>
        )}

        <span className="tip-foot mono">입력 해시 {breakdown.inputs_hash}</span>
      </span>
    </span>
  );
}
