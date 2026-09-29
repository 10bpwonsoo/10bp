/** 물가 탭 — Inflation & Rates Intelligence. Regime → Rate Driver → Inflation Components → Curve → Decomposition → Confirmation → Divergence → Implication → Triggers → Diagnostics. */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import hist from "../__fixtures__/state_history.json";
import regimeFx from "../__fixtures__/rates_regime.json";
import checksFx from "../__fixtures__/scenario_check.json";
import type { IntelligenceSnapshot, MarketStateHistory, RatesRegime, ScenarioCheck } from "../api/types";
import { RatesRegimeView } from "../components/RatesRegimeView";
import { ScenarioView } from "../components/ScenarioView";

const snapshot = snap as unknown as IntelligenceSnapshot;
const history = hist as unknown as MarketStateHistory;
const regime = regimeFx as unknown as RatesRegime;
const check: ScenarioCheck = { ...(checksFx as unknown as ScenarioCheck[]).find((c) => c.name === "inflation_shock")!, focus: "rates_regime" };

describe("RatesRegimeView", () => {
  it("최상단 REGIME 카드가 지배 driver 와 물가 리프라이싱 상태, US 10Y 관측을 말한다", () => {
    render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    const card = screen.getByTestId("rates-regime-card");
    expect(card.textContent).toContain(regime.regime_label.split(" — ")[0]!);
    expect(screen.getByTestId("inflation-status").textContent).toContain("Inflation Repricing");
    expect(screen.getByTestId("rate-move").textContent).toContain("US 10Y YIELD");
    // 9/29 실데이터 예시: 장기금리·기간 프리미엄 충격, 물가 리프라이싱 미확인
    expect(regime.dominant).toBe("term_premium");
    expect(regime.regime_label).toBe("LONG-END RATE / TERM PREMIUM SHOCK — Inflation Repricing Not Confirmed");
    expect(regime.inflation_status).toBe("UNCONFIRMED");
    expect(card.textContent).not.toMatch(/probab|확률/i);
  });

  it("섹션이 정해진 순서로 놓이고 driver 5개·물가 구성 5개(결측 표시)·테너 4개·분해·확인표·괴리·전이·전환 조건이 있다", () => {
    const { container } = render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    expect(titles).toEqual(["Inflation & Rates Regime", "What Is Driving Rates?", "Inflation Pressure", "Treasury Curve", "Nominal Yield Decomposition", "Market Confirmation", "Key Divergence", "Market Implication", "What Changes The View", "Diagnostics"]);
    expect(screen.getAllByTestId("rates-driver").length).toBe(5);
    const comps = screen.getAllByTestId("inflation-component");
    expect(comps.length).toBe(5);
    expect(comps.filter((c) => c.getAttribute("data-status") === "missing").length).toBeGreaterThanOrEqual(1); // CPI·PCE 계열 없음 — 0 이 아니다
    expect(within(screen.getByTestId("curve")).getAllByRole("row").map((r) => r.getAttribute("data-tenor"))).toEqual(["2Y", "5Y", "10Y", "30Y"]);
    expect(screen.getByTestId("curve").textContent).toContain("Bear steepening");
    expect(screen.getByTestId("decomposition").textContent).toContain("TIPS 실측");
    expect(container.querySelectorAll('.rr-conf[data-status="CONFIRMED"]').length).toBe(regime.confirmations.filter((r) => r.status === "CONFIRMED").length);
    expect(screen.getAllByTestId("divergence-row").length).toBe(regime.divergences.length);
    expect(screen.getByTestId("market-implication").textContent).toContain("추천이 아니다");
    expect(screen.getByTestId("market-implication").textContent).not.toMatch(/매수|매도/);
    const triggers = screen.getAllByTestId("trigger-item");
    expect(triggers.length).toBeGreaterThanOrEqual(3);
    expect(triggers.length).toBeLessThanOrEqual(5);
    expect(screen.getAllByTestId("release-item").length).toBeGreaterThanOrEqual(1);
  });

  it("require/support 판정과 서명 대조는 Diagnostics(details) 안에만 있고, 라벨은 US 10Y Yield 로 명확하다", () => {
    const { container } = render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    const diag = screen.getByTestId("rates-diagnostics");
    expect(within(diag).getAllByText(/require/i).length).toBeGreaterThan(0);
    expect(within(diag).getByTestId("factor-breakdown")).toBeInTheDocument();
    const mainText = Array.from(container.querySelectorAll(".panel:not(details)")).map((e) => e.textContent).join(" ");
    expect(mainText).not.toMatch(/Inflation Shock 아님|require 실패|US 10Y Treasury/);
    expect(mainText).toMatch(/US 10Y Yield/i);
  });

  it("ScenarioView 는 물가 탭(focus=rates_regime)에서 이 화면을 그리고, 아직 못 받았으면 로딩 문구를 낸다", () => {
    const { unmount } = render(<ScenarioView check={check} snapshot={snapshot} history={history} investment={null} ratesRegime={regime} />);
    expect(screen.getByTestId("rates-regime")).toBeInTheDocument();
    unmount();
    render(<ScenarioView check={check} snapshot={snapshot} history={history} investment={null} />);
    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument();
  });
});
