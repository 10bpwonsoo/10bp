/** 금리 탭 아래 세 패널(2026-10-13) — INFLATION PRESSURE MAP → TREASURY CURVE → YIELD MOVE BREAKDOWN. 다른 섹션은 그대로. */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import fx from "../__fixtures__/rates_regime_lower.json";
import checksFx from "../__fixtures__/scenario_check.json";
import type { IntelligenceSnapshot, RatesRegime, ScenarioCheck } from "../api/types";
import { RatesRegimeView } from "../components/RatesRegimeView";

const snapshot = snap as unknown as IntelligenceSnapshot;
const regime = fx as unknown as RatesRegime;
const check: ScenarioCheck = { ...(checksFx as unknown as ScenarioCheck[]).find((c) => c.name === "inflation_shock")!, focus: "rates_regime" };

describe("금리 탭 아래 세 패널", () => {
  it("순서: Inflation Pressure Map → Treasury Curve → Yield Move Breakdown, 그 뒤는 그대로", () => {
    const { container } = render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    const i = titles.indexOf("Inflation Pressure Map");
    expect(titles.slice(i, i + 5)).toEqual(["Inflation Pressure Map", "Treasury Curve", "Yield Move Breakdown", "Market Confirmation", "Key Divergence"]);
    expect(titles).not.toContain("Nominal Yield Decomposition");
    expect(screen.getAllByTestId("panel-link").length).toBe(3);
  });

  it("INFLATION PRESSURE MAP: 결론(신호 · 확인) 먼저, 구성요소는 상태 → 점수 → 근거, 결측은 DATA MISSING", () => {
    render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    expect(screen.getByTestId("inflation-signal").textContent).toContain("COOLING BIAS");
    expect(screen.getByTestId("inflation-confirmation").textContent).toContain("PARTIAL");
    const items = screen.getAllByTestId("pressure-item");
    expect(items.map((x) => x.getAttribute("data-state"))).toEqual(["DATA MISSING", "COOLING", "MILD PRESSURE", "DATA MISSING", "EASING"]);
    expect(items[0]!.textContent).toContain("실제 물가");
    expect(items[0]!.textContent).toContain("CPI / PCE 실제 물가 데이터 미연결");
    const t = items[1]!.textContent ?? "";
    expect(t.indexOf("COOLING")).toBeLessThan(t.indexOf("−59"));
    expect(t.indexOf("−59")).toBeLessThan(t.indexOf("10Y BE"));
    const read = screen.getByTestId("inflation-read");
    expect(read.textContent).toContain("AI INTERPRETATION · 세션 생성");
    expect(within(read).getByText(/둔화 신호/).textContent).not.toMatch(/\d/);
  });

  it("TREASURY CURVE: 모양(bp)과 이례성(σ)을 칸으로 나누고, 오늘·5D 전 곡선을 그린다", () => {
    render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    expect(screen.getByTestId("curve-shape").textContent).toContain("MILD BULL STEEPENING");
    expect(screen.getByTestId("curve-shape").textContent).toContain("5D bp");
    expect(screen.getByTestId("curve-intensity").textContent).toContain("5D σ");
    expect(screen.getByTestId("curve-spreads").textContent).toContain("2s10s +1bp STEEPENING");
    const chart = screen.getByTestId("curve-chart");
    expect(chart.querySelectorAll("path.rp-line").length).toBe(2);
    expect(chart.textContent).toContain("5D AGO");
    expect(screen.getByTestId("curve-1d").textContent).toContain("BULL FLATTENING");
  });

  it("YIELD MOVE BREAKDOWN: 5Y · 10Y 기본, 실질(모델) + 기대인플레 = 명목, 주도 요인과 OBSERVED TIPS 를 나눠 보인다", () => {
    render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    const cards = screen.getAllByTestId("breakdown-tenor");
    expect(cards.map((c) => c.getAttribute("data-tenor"))).toEqual(["5Y", "10Y"]);
    expect(within(cards[0]!).getByTestId("primary-driver").textContent).toContain("REAL YIELD ↓");
    expect(cards[0]!.textContent).toContain("MODEL");
    expect(within(cards[0]!).getByTestId("observed-tips").getAttribute("data-divergence")).toBe("0");
    expect(screen.queryByTestId("breakdown-all")).toBeNull(); // 2Y · 30Y 분해 계열이 없으면 View all 도 없다
  });

  it("View all — 기본 밖 만기가 있으면 접혀 있다가 펼쳐진다", () => {
    const yb = regime.yield_breakdown!;
    const more = { ...regime, yield_breakdown: { ...yb, tenors: [...yb.tenors, { ...yb.tenors[1]!, tenor: "30Y" }] } } as RatesRegime;
    render(<RatesRegimeView regime={more} snapshot={snapshot} check={check} />);
    expect(screen.getAllByTestId("breakdown-tenor").length).toBe(2);
    fireEvent.click(screen.getByTestId("breakdown-all"));
    expect(screen.getAllByTestId("breakdown-tenor").length).toBe(3);
  });
});
