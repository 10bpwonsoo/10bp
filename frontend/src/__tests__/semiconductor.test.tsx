/** 반도체 사이클 탭 (2026-10-23) — 10/23 07:30 KST 캡처로 그린다. 없는 값은 NO DATA · '–' (0 이 아니다), 과거 날짜는 저장본만. */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import fx from "../__fixtures__/semiconductor_cycle.json";
import type { SemiconductorCycle } from "../api/semiconductor";
import { resolveArchived, type DashboardArchive } from "../api/archive";
import { SemiconductorCycleView, SemiconductorNotArchived } from "../components/SemiconductorCycleView";
import { semiAfter } from "../App";

const cycle = fx as unknown as SemiconductorCycle;
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

describe("SemiconductorCycleView", () => {
  it("REGIME 카드 — 국면 · 신뢰도 · 칩, 확률 표현 없음", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const card = screen.getByTestId("semi-regime");
    expect(screen.getByTestId("semi-regime-label").textContent).toBe(cycle.regime.label);
    expect(screen.getByTestId("semi-confidence").textContent).toContain(`신뢰도 ${cycle.regime.confidence.toFixed(0)}`);
    const chips = within(screen.getByTestId("semi-chips")).getAllByText(/./, { selector: "b" });
    expect(chips.map((c) => c.textContent)).toEqual(cycle.regime.chips.map((c) => c.value));
    expect(card.textContent).not.toMatch(/확률|매수|매도/);
    // EPS 증거는 공급원이 없어 NO DATA — 0 으로 그리지 않는다
    expect(card.querySelector('[data-key="eps_revision"]')!.textContent).toContain("NO DATA");
  });

  it("Market Read 는 2~4문장 해석, 출처(세션 생성)를 밝힌다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    expect(screen.getByTestId("semi-read-text").textContent).toBe(cycle.market_read.read);
    expect(screen.getByTestId("semi-read").textContent).toContain("세션 생성");
  });

  it("가격 표 — 기준 관측이 없는 창은 '–' 이고 0% 로 그리지 않는다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const row = screen.getAllByTestId("semi-price-row").find((r) => r.getAttribute("data-id") === "DDR4_16G_SPOT")!;
    const p = cycle.memory_prices.find((x) => x.id === "DDR4_16G_SPOT")!;
    expect(p.change_1w).toBeNull();
    expect(row.querySelector('[data-label="1W"]')!.textContent).toBe("–");
    expect(row.textContent).not.toContain("0.0%");
  });

  it("Spot Premium — DDR5 는 PROXY PREMIUM, NAND 는 계산하지 않는다, 계약 기준 월을 보인다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const rows = screen.getAllByTestId("semi-premium-row");
    const ddr5 = rows.find((r) => r.getAttribute("data-spot") === "DDR5_16G_SPOT")!;
    expect(ddr5.textContent).toContain("PROXY PREMIUM");
    const nand = rows.find((r) => r.getAttribute("data-spot") === "NAND_512G_TLC_WAFER")!;
    expect(nand.textContent).toContain("NOT COMPUTED");
    const d4 = rows.find((r) => r.getAttribute("data-spot") === "DDR4_16G_SPOT")!;
    expect(d4.textContent).toContain("Aug-2026");
    expect(d4.textContent).toContain("STALE");
  });

  it("가격 + 프리미엄 차트 — 제품 선택 · 기간 버튼 · 0% 선 · 툴팁", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const chart = screen.getByTestId("semi-chart");
    expect(within(chart).getByTestId("semi-zero-line")).toBeTruthy(); // 첫 제품(DDR5)은 proxy premium 이 있다
    const sel = within(chart).getByTestId("semi-product-select") as HTMLSelectElement;
    const options = Array.from(sel.options).map((o) => o.value);
    expect(options).toEqual(cycle.memory_prices.filter((p) => p.selector && p.available).map((p) => p.id));
    fireEvent.change(sel, { target: { value: "NAND_512G_TLC_WAFER" } });
    expect(within(chart).queryByTestId("semi-zero-line")).toBeNull(); // NAND 는 premium 없음 → 0% 선 없음
    expect(chart.textContent).toContain("Spot Premium 계산 안 함");
    fireEvent.click(within(chart).getByRole("button", { name: "1M" }));
    expect(within(chart).getByRole("button", { name: "1M" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.change(sel, { target: { value: "DDR5_16G_SPOT" } });
    fireEvent.pointerMove(within(chart).getByTestId("semi-price-svg"), { clientX: 10, clientY: 50 });
    expect(within(chart).getByTestId("semi-tooltip").textContent).toMatch(/Spot \$\d/);
  });

  it("전파 사슬 상태는 CONFIRMED / PARTIAL / WATCH / NOT CONFIRMED / NO DATA 중 하나", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const ok = new Set(["CONFIRMED", "PARTIAL", "WATCH", "NOT CONFIRMED", "NO DATA"]);
    for (const s of screen.getAllByTestId("semi-stage")) expect(ok.has(s.getAttribute("data-status")!)).toBe(true);
    expect(within(screen.getByTestId("semi-spot-contract")).getAllByTestId("semi-stage").length).toBe(cycle.spot_to_contract.stages.length);
  });

  it("수출 나우캐스트 — 1~10D · 1~20D · Full Month Nowcast · Actual(Pending), 일평균 YoY 와 accuracy 메모", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const rows = screen.getAllByTestId("semi-export-row");
    expect(rows.map((r) => r.getAttribute("data-scope"))).toEqual(["1-10", "1-20", "nowcast", "actual"]);
    expect(rows[3]!.textContent).toContain("Pending");
    expect(rows[1]!.textContent).toContain("+160.5%");
    expect(screen.getByTestId("semi-export-accuracy").textContent).toContain("기록이 없다");
  });

  it("주가 확인 — DIVERGENCE 와 해석 문장", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    expect(screen.getByTestId("semi-equity").textContent).toContain(cycle.equity_confirmation.status);
    expect(screen.getByTestId("semi-divergence-read").textContent).toBe(cycle.equity_confirmation.read);
  });

  it("What Matters Next ≤ 5, Data Quality 는 Fresh/Stale/Unavailable", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    expect(screen.getAllByTestId("semi-next-row").length).toBeLessThanOrEqual(5);
    for (const r of screen.getAllByTestId("semi-quality-row")) expect(["FRESH", "STALE", "UNAVAILABLE"]).toContain(r.getAttribute("data-status"));
    expect(screen.getAllByTestId("semi-quality-row").some((r) => r.getAttribute("data-status") === "UNAVAILABLE")).toBe(true);
  });

  it("History 1M 는 daily snapshot 기준 strip", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    expect(screen.getByTestId("semi-history").textContent).toContain(cycle.memory_history!.footnote);
  });

  it("없는 섹션 데이터가 비어 있어도 깨지지 않는다(NO DATA)", () => {
    const c = clone(cycle);
    c.news = []; c.normalized = { "1M": [], "3M": [], "6M": [] }; c.memory_history = null;
    c.export_nowcast = { available: false, note: "발표된 반도체 수출 자료가 없다" };
    render(<SemiconductorCycleView cycle={c} />);
    expect(screen.getByTestId("semi-export").textContent).toContain("NO DATA");
    expect(screen.getByTestId("semi-normalized").textContent).toContain("NO DATA");
    expect(screen.getByTestId("semi-news").textContent).toContain("기사 없음");
  });
});

describe("반도체 사이클 — 저장본 · 탭 위치", () => {
  it("저장본에 섹션이 없으면 NOT ARCHIVED — 지금 값으로 메우지 않는다", () => {
    const a = { schema_version: "1", snapshot_date: "2026-10-22", generated_at: "", archive_status: "COMPLETE", snapshot: { mode: "DELAYED" } } as unknown as DashboardArchive;
    expect(() => resolveArchived(a, "/api/v1/semiconductor-cycle")).toThrow(/NOT ARCHIVED/);
    const b = { ...a, semiconductor_cycle: cycle } as unknown as DashboardArchive;
    expect(resolveArchived(b, "/api/v1/semiconductor-cycle")).toBe(cycle);
    render(<SemiconductorNotArchived />);
    expect(screen.getByTestId("semi-not-archived").textContent).toContain("SEMICONDUCTOR CYCLE NOT ARCHIVED FOR THIS DATE");
  });

  it("탭은 AI 센티 바로 뒤", () => {
    expect(semiAfter([{ focus: "ai_regime_full" }, { focus: "rates_regime" }, { focus: "oil_regime" }, { focus: null }])).toBe(0);
    expect(semiAfter([{ focus: "rates_regime" }])).toBe(-1);
  });
});
