/** 시나리오 점검 — 모의 탭을 실데이터로 바꾼 것. 서버가 준 일치도·룰 상태·행을 그대로 그린다. */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ScenarioCheck } from "../api/types";
import { ScenarioCheckPanel, scoreColor } from "../components/ScenarioCheckPanel";

const check: ScenarioCheck = {
  name: "inflation_shock", title: "물가 충격 — 유가 급등이 금리를 밀어올림", description: "d", as_of: "2026-09-29T00:45:00Z",
  label: "INFLATION_SHOCK", focus: "rule", factor: "Inflation", commodities: [], match_score: 43, match_label: "거의 다름", evaluated: 3, agree: 1, weak: 0, oppose: 1, quiet_ok: 0, quiet_broken: 0,
  missing: ["KR10Y"],
  rows: [
    { instrument_id: "US10Y", label: "US 10Y Treasury", expected_z: 1.6, actual_z_1d: -0.5, actual_z_5d: 1.4, used_z: 1.4, used_window: 5, ratio: 0.875, weight: 1.6, status: "agree", layer: "market" },
    { instrument_id: "BRENT", label: "브렌트 원유", expected_z: 2.1, actual_z_1d: -1.9, actual_z_5d: -0.6, used_z: -1.9, used_window: 1, ratio: 0, weight: 2.1, status: "oppose", layer: "market" },
    { instrument_id: "KR10Y", label: "국고 10년", expected_z: 1.2, actual_z_1d: null, actual_z_5d: null, used_z: null, used_window: null, ratio: 0, weight: 1.2, status: "missing", layer: "market" },
  ],
  hypothesis_score: 0, require_expression: "Inflation >= 1.0", require_passed: false, require_observed: -0.85,
  current_label: "LIQUIDITY_STRESS", current_confidence: 66, themes: [{ theme_id: "inflation", name: "Inflation", theme_score: 0.9, news_sentiment: 13.5 }],
  verdict: "실데이터는 '물가 충격' 시나리오와 43% 닮았다(거의 다름).", note: "예측이 아니다.",
};

describe("ScenarioCheckPanel", () => {
  it("일치도·룰 상태·행 상태를 서버 값 그대로 그린다", () => {
    const { container } = render(<ScenarioCheckPanel check={check} />);
    expect(screen.getByText("43%")).toBeInTheDocument();
    const rule = screen.getByTestId("scenario-rule");
    expect(rule.textContent).toContain("Inflation >= 1.0");
    expect(rule.textContent).toContain("-0.85");
    expect(rule.textContent).toContain("Liquidity Stress 66%");
    const rows = container.querySelectorAll(".sc-row");
    expect(rows.length).toBe(3);
    expect(container.querySelector('.sc-row[data-status="oppose"]')?.textContent).toContain("반대");
    // 결측은 맨 뒤, 값 대신 '결측'
    expect(rows[2]!.getAttribute("data-status")).toBe("missing");
    expect(rows[2]!.textContent).toContain("결측");
    // 가중치(|기대 z|) 순이라 브렌트(2.1)가 먼저, 결측은 맨 뒤
    expect(rows[0]!.getAttribute("data-status")).toBe("oppose");
    // 5일 창을 썼으면 그렇게 적는다
    const agree = container.querySelector('.sc-row[data-status="agree"]')!;
    expect(agree.textContent).toContain("+1.4σ");
    expect(agree.textContent).toContain("5일");
    expect(container.querySelector(".sc-theme")?.textContent).toContain("뉴스 +14");
  });

  it("평시·라벨 없음은 룰 대신 그 뜻을 쓴다", () => {
    render(<ScenarioCheckPanel check={{ ...check, name: "baseline", label: "NEUTRAL", require_expression: null }} />);
    expect(screen.getByTestId("scenario-rule").textContent).toContain("평시 = 룰 없음");
    render(<ScenarioCheckPanel check={{ ...check, name: "ai", label: null }} />);
    expect(screen.getAllByTestId("scenario-rule")[1]!.textContent).toContain("판정 라벨 없는 시나리오");
    expect(scoreColor(80)).toBe("var(--ok)");
    expect(scoreColor(10)).toBe("var(--muted)");
  });
});
