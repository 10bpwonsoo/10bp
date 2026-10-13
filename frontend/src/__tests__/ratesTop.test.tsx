/** 금리 탭 상단 정리(2026-10-12) — RATES REGIME · CURRENT RATES ANALYSIS · HISTORY · POLICY & MACRO EVENTS. 하단 패널은 그대로. */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import regimeFx from "../__fixtures__/rates_regime_top.json";
import oldFx from "../__fixtures__/rates_regime.json";
import checksFx from "../__fixtures__/scenario_check.json";
import type { IntelligenceSnapshot, RatesRegime, ScenarioCheck } from "../api/types";
import { RatesRegimeView } from "../components/RatesRegimeView";

const snapshot = snap as unknown as IntelligenceSnapshot;
const regime = regimeFx as unknown as RatesRegime;
const check: ScenarioCheck = { ...(checksFx as unknown as ScenarioCheck[]).find((c) => c.name === "inflation_shock")!, focus: "rates_regime" };

describe("금리 탭 상단 정리", () => {
  it("순서: REGIME → CURRENT RATES ANALYSIS → HISTORY → POLICY & MACRO EVENTS → 기존 하단 그대로(What Is Driving Rates 패널은 위로 흡수)", () => {
    const { container } = render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    const titles = Array.from(container.querySelectorAll(".rr > .panel > .panel-head .panel-title, .rr > details > summary .panel-title")).map((e) => e.textContent);
    expect(titles).toEqual(["Inflation & Rates Regime", "Current Rates Analysis", "Inflation & Rates State History · 1M", "Policy & Macro Events", "Inflation Pressure", "Treasury Curve", "Nominal Yield Decomposition", "Market Confirmation", "Key Divergence", "Market Implication", "What Changes The View", "Diagnostics"]);
  });

  it("REGIME: 큰 판정 아래 금리 방향 · 주도 driver · 물가 여부 · 신뢰도, MARKET READ(규칙 기반)는 숫자 없이 최대 2문장, DRIVER READ 는 PRIMARY/COUNTER/NOT CONFIRMED", () => {
    render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    expect(screen.getByTestId("rates-regime-label").textContent).toBe("LONG-END RATE / TERM PREMIUM SHOCK");
    const dir = screen.getByTestId("yield-direction");
    expect(dir.getAttribute("data-direction")).toBe("down");
    expect(dir.textContent).toContain("↓ FALLING");
    expect(screen.getByTestId("driver-title").textContent).toBe("TERM PREMIUM / SUPPLY DRIVEN");
    expect(screen.getByTestId("inflation-status").textContent).toContain("NOT CONFIRMED");
    expect(screen.getByTestId("rate-move").textContent).toContain("5.22%");
    // 옛 캡처(메타 없음)는 규칙 기반 문장 — 숫자 없음, 상투 문구 없음
    const read = screen.getByTestId("market-read-text").textContent ?? "";
    expect(read).toContain("기간 프리미엄·공급");
    expect(read).not.toMatch(/\d|확률|주된 원인은|아직 확인되지 않았습니다/);
    expect(screen.getByTestId("market-read-source").textContent).toBe("RULE-BASED");
    const dr = screen.getByTestId("driver-read");
    expect(dr.textContent).toContain("PRIMARY");
    expect(screen.getByTestId("driver-counter").textContent).toContain("Growth");
    expect(screen.getByTestId("driver-nc").textContent).toContain("Inflation / Fed Policy");
    // 기존 driver chip · Transmission 은 그대로 남는다
    expect(screen.getByTestId("rates-regime-card").querySelectorAll(".rr-chip").length).toBe(5);
    expect(screen.getByTestId("rates-regime-card").textContent).toContain("TRANSMISSION");
  });

  it("MARKET READ: LLM 해석이면 AI INTERPRETATION · 테마 태그 · 데이터 주의, 규칙 기반이면 그 이유가 보이고 모델 이름은 없다", () => {
    const meta = { source: "llm", status: "ok", generator: "api", reason: "", themes: ["term_premium", "oil"], themes_ko: ["기간 프리미엄", "유가"], move_quality: "fiscal_supply_premium",
      move_quality_ko: "재정·공급 프리미엄", regime_fit: "partly_consistent", data_caveat: "미국채는 10월 8일 종가 기준이다.", generated_at: "2026-10-13T01:30:00Z", context_as_of: null, rule_read: "규칙 문장", warnings: [] } as const;
    const llm = { ...regime, top: { ...regime.top!, market_read: "장기물 강세는 되돌림에 더 가깝다. 위험자산에는 선별적인 환경으로 읽힌다.", market_read_meta: meta } } as unknown as RatesRegime;
    const { unmount } = render(<RatesRegimeView regime={llm} snapshot={snapshot} check={check} />);
    const box = screen.getByTestId("rates-market-read");
    expect(box.getAttribute("data-source")).toBe("llm");
    expect(screen.getByTestId("market-read-source").textContent).toBe("AI INTERPRETATION · 10/13 10:30 KST");
    expect(screen.getAllByTestId("market-read-theme").map((x) => x.textContent)).toEqual(["기간 프리미엄", "유가"]);
    expect(screen.getByTestId("market-read-caveat").textContent).toContain("10월 8일");
    expect(box.textContent).not.toMatch(/claude|opus|sonnet|규칙 문장/i);
    unmount();
    const fb = { ...regime, top: { ...regime.top!, market_read_meta: { ...meta, source: "rule", status: "fallback", generator: "none", reason: "API 오류 — API 계정 크레딧 부족", themes: [], themes_ko: [] } } } as unknown as RatesRegime;
    render(<RatesRegimeView regime={fb} snapshot={snapshot} check={check} />);
    expect(screen.getByTestId("market-read-source").textContent).toBe("RULE-BASED · AI 해석 없음");
    expect(screen.getByTestId("market-read-reason").textContent).toContain("크레딧 부족");
    expect(screen.queryAllByTestId("market-read-theme").length).toBe(0);
  });

  it("CURRENT RATES ANALYSIS: Driver · Curve · Real Yield · Breakeven 네 칸 + 한 줄, compact driver 행은 누르면 근거가 펼쳐진다", () => {
    render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    const tiles = screen.getAllByTestId("analysis-tile");
    expect(tiles.map((t) => t.getAttribute("data-key"))).toEqual(["driver", "curve", "real_yield", "breakeven"]);
    expect(tiles[0]!.textContent).toContain("DOMINANT");
    expect(tiles[1]!.textContent).toContain("Bull Flattening");
    expect(tiles[2]!.getAttribute("data-move")).toBe("down");
    expect(screen.getByTestId("analysis-sentence").textContent).toContain("압도적");
    const rows = screen.getAllByTestId("rates-driver");
    expect(rows.length).toBe(5);
    expect(rows[0]!.textContent).toContain("장기금리 하락의 핵심 driver");
    expect(screen.queryAllByTestId("driver-evidence").length).toBe(0);
    fireEvent.click(within(rows[0]!).getByRole("button"));
    expect(screen.getByTestId("driver-evidence").textContent).toContain("US 30Y Yield");
  });

  it("POLICY & MACRO EVENTS: regime 연결 → RECENT(EVENT → SURPRISE → RATES REACTION, 기본 4) · 중앙은행 4 · UPCOMING(기본 5), 누르면 상세", () => {
    render(<RatesRegimeView regime={regime} snapshot={snapshot} check={check} />);
    const ev = regime.events!;
    const link = screen.getByTestId("regime-link");
    expect(link.getAttribute("data-impact")).toBe(ev.link!.impact);
    expect(link.textContent).toContain("Term Premium / Supply");
    const recent = screen.getAllByTestId("recent-event");
    expect(recent.length).toBe(ev.recent_default);
    for (const r of recent) expect(within(r).getByTestId("event-chain").textContent).toMatch(/→/);
    const cpi = recent.find((r) => r.getAttribute("data-key") === "us_cpi")!;
    expect(cpi.textContent).toContain("HOT");
    expect(within(cpi).getByTestId("event-impact").getAttribute("data-impact")).toBe("CHALLENGED");
    fireEvent.click(within(cpi).getByRole("button"));
    const det = screen.getByTestId("release-detail");
    expect(det.textContent).toContain("ACTUAL");
    expect(det.textContent).toContain("CONSENSUS");
    expect(det.querySelectorAll("a").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByTestId("recent-all"));
    expect(screen.getAllByTestId("recent-event").length).toBe(ev.recent.length);
    const banks = screen.getAllByTestId("bank-card");
    expect(banks.map((b) => b.getAttribute("data-bank"))).toEqual(["FED", "ECB", "BOJ", "BOK"]);
    fireEvent.click(within(banks[0]!).getByRole("button"));
    expect(screen.getByTestId("policy-detail").textContent).toContain("3.75–4.00%");
    expect(screen.getAllByTestId("upcoming-event").length).toBe(Math.min(ev.upcoming_default, ev.upcoming.length));
    expect(screen.getByTestId("policy-macro-events").textContent).not.toMatch(/확률|매수|매도/);
  });

  it("옛 캡처(top 없음)는 예전 머리와 순서를 그대로 그린다", () => {
    const { container } = render(<RatesRegimeView regime={oldFx as unknown as RatesRegime} snapshot={snapshot} check={check} />);
    expect(screen.queryByTestId("rates-top")).toBeNull();
    expect(screen.queryByTestId("policy-macro-events")).toBeNull();
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    expect(titles[2]).toBe("What Is Driving Rates?");
  });
});
