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

  it("INFLATION PRESSURE MAP: 결론(신호 · 확인) 먼저, 구성요소는 상태 → 점수 → 근거, 출처 급이 항상 보인다", () => {
    render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    expect(screen.getByTestId("inflation-signal").textContent).toContain("COOLING BIAS");
    expect(screen.getByTestId("inflation-confirmation").textContent).toContain("PARTIAL");
    expect(screen.getByTestId("confirmation-quality").textContent).toBe("Official data 4/5 · Proxy 1 · News 1");
    const items = screen.getAllByTestId("pressure-item");
    expect(items.map((x) => x.getAttribute("data-key"))).toEqual(["realized", "implied", "energy", "wages", "fx", "news"]);
    expect(items.map((x) => x.getAttribute("data-tier"))).toEqual(["PRIMARY", "PRIMARY", "PRIMARY", "PROXY", "PRIMARY", "NEWS"]);
    // 실제 물가 — 공식 원자료(BLS / BEA), 값 줄과 갱신일
    const real = items[0]!;
    expect(within(real).getByTestId("item-source").textContent).toContain("BLS / BEA via FRED");
    expect(within(real).getByTestId("item-source").textContent).toContain("Updated 9/30");
    expect(within(real).getByTestId("item-values").textContent).toContain("Core PCE");
    const t = items[1]!.textContent ?? "";
    expect(t.indexOf("COOLING")).toBeLessThan(t.indexOf("−59"));
    expect(t.indexOf("−59")).toBeLessThan(t.indexOf("10Y BE"));
  });

  it("PROXY 는 숨기지 않는다 — 배지 · 원데이터 누락 설명 · 무엇으로 대체했는지 세 가지를 함께", () => {
    render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    const wages = screen.getAllByTestId("pressure-item").find((x) => x.getAttribute("data-key") === "wages")!;
    expect(within(wages).getAllByTestId("tier-badge")[0]!.textContent).toBe("PROXY");
    const d = within(wages).getByTestId("proxy-disclosure").textContent ?? "";
    expect(d).toContain("실제 원데이터 미연결 · 대체 지표로 추정");
    expect(d).toContain("실제 Wage / Services 단일 원데이터 미연결");
    expect(d).toContain("대체: AHE · ECI · Services CPI · Core Services PCE 기반");
    // 뉴스는 보조 신호 — 신호 점수에 넣지 않는다고 적는다
    const news = screen.getAllByTestId("pressure-item").find((x) => x.getAttribute("data-key") === "news")!;
    expect(within(news).getByTestId("item-source").textContent).toContain("INFLATION SIGNAL 점수 미반영");
    // DATA SOURCES — 모든 series 의 급 · 갱신일
    const ds = screen.getByTestId("data-sources");
    expect(ds.querySelectorAll('[role="row"]').length).toBe(regime.inflation_map!.data_sources!.length);
    const read = screen.getByTestId("inflation-read");
    expect(read.textContent).toContain("AI INTERPRETATION · 세션 생성");
    expect(within(read).getByText(/대체 지표로 본/).textContent).not.toMatch(/\d/);
  });

  it("옛 캡처 형식(출처 급 없음)의 결측 칸은 DATA UNAVAILABLE 로 그대로 그린다", () => {
    const im = regime.inflation_map!;
    const old = { ...regime, inflation_map: { ...im, items: [{ key: "realized", label: "Realized Inflation", label_ko: "실제 물가", state: "DATA MISSING", state_ko: "", tone: "missing", score: null, evidence_text: "", missing_text: "CPI / PCE 실제 물가 데이터 미연결" }] } } as unknown as RatesRegime;
    render(<RatesRegimeView regime={old} snapshot={snapshot} check={check} />);
    const it0 = screen.getByTestId("pressure-item");
    expect(it0.getAttribute("data-tier")).toBe("UNAVAILABLE");
    expect(it0.textContent).toContain("CPI / PCE 실제 물가 데이터 미연결");
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
