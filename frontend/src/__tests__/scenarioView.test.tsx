/** 시나리오 탭 화면 — 실데이터 화면을 복제하지 않고 그 탭에 어울리는 판정을 앞세운다. 숫자는 스냅샷·히스토리·Investment 의 값 그대로. */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import hist from "../__fixtures__/state_history.json";
import inv from "../__fixtures__/investment.json";
import type { IntelligenceSnapshot, MarketStateHistory, ScenarioCheck } from "../api/types";
import type { InvestmentIntelligence } from "../api/investment";
import { ScenarioView, daysWithLabel, ruleHeadline, hypothesisFor } from "../components/ScenarioView";

const snapshot = snap as unknown as IntelligenceSnapshot;
const history = hist as unknown as MarketStateHistory;
const investment = inv as unknown as InvestmentIntelligence;
const base: ScenarioCheck = {
  name: "x", title: "물가 충격 — 유가", description: "", as_of: snapshot.as_of, label: "INFLATION_SHOCK", focus: "rule", factor: "Inflation", commodities: [],
  match_score: 43, match_label: "거의 다름", evaluated: 0, agree: 0, weak: 0, oppose: 0, quiet_ok: 0, quiet_broken: 0, missing: [], rows: [],
  hypothesis_score: 0, require_expression: "Inflation >= 1.0", require_passed: false, require_observed: -0.85,
  current_label: snapshot.market_state.primary_label, current_confidence: snapshot.market_state.confidence,
  themes: [{ theme_id: "inflation", name: "Inflation", theme_score: 1, news_sentiment: 10 }], verdict: "v", note: "n",
};

describe("ScenarioView", () => {
  it("rule 탭은 require 룰 상태로 '해당/아님' 을 말하고 팩터 재료를 펼친다 — 실데이터 그리드는 없다", () => {
    const { container } = render(<ScenarioView check={base} snapshot={snapshot} history={history} investment={investment} />);
    const head = screen.getByTestId("scenario-headline");
    const hyp = hypothesisFor(snapshot, "INFLATION_SHOCK");
    const expected = ruleHeadline(base, hyp);
    expect(head.textContent).toContain(expected.verdict);
    expect(expected.verdict.endsWith(hyp && hyp.matched_rules.filter((r) => r.kind === "require").every((r) => r.passed) && hyp.matched_rules.some((r) => r.kind === "require") ? "해당" : "아님")).toBe(true);
    expect(screen.getByTestId("factor-breakdown").textContent).toContain("Inflation");
    expect(container.querySelector('[data-testid="scenario-view"]')?.getAttribute("data-focus")).toBe("rule");
    // 실데이터 화면의 패널들은 없다
    expect(container.textContent).not.toContain("THEME HEATMAP");
    expect(container.querySelector('[data-testid="scenario-check"]')).not.toBeNull();
    const d = daysWithLabel(history, "INFLATION_SHOCK");
    expect(d.total).toBe(history.points.length);
  });

  it("fear_greed 탭은 온도계 밴드와 한 달 공포·탐욕 띠를 앞세운다", () => {
    render(<ScenarioView check={{ ...base, name: "ai", title: "AI 센티 — 뉴스", label: null, focus: "fear_greed", factor: null }} snapshot={snapshot} history={history} investment={investment} />);
    const head = screen.getByTestId("scenario-headline");
    expect(head.textContent).toContain("시장 온도");
    expect(screen.getByTestId("primary-legend").getAttribute("data-primary")).toBe("band");
  });

  it("semiconductor 탭은 네 신호의 합의를, calm 탭은 평시 여부를 말한다", () => {
    render(<ScenarioView check={{ ...base, name: "mem", title: "메모리 — x", label: null, focus: "semiconductor", factor: null }} snapshot={snapshot} history={history} investment={investment} />);
    expect(screen.getByTestId("scenario-headline").textContent).toMatch(/반도체/);
    render(<ScenarioView check={{ ...base, name: "base", title: "평시 — x", label: "NEUTRAL", focus: "calm", factor: null }} snapshot={snapshot} history={history} investment={investment} />);
    const heads = screen.getAllByTestId("scenario-headline");
    const calm = heads[heads.length - 1]!;
    expect(calm.textContent).toMatch(/평시/);
    expect(calm.getAttribute("data-on")).toBe(snapshot.market_state.primary_label === "NEUTRAL" ? "1" : "0");
  });
});
