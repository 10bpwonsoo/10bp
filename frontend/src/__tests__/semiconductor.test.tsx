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
    expect(screen.getByTestId("semi-confidence").querySelector('[data-key="confidence"] b')!.textContent).toBe(cycle.regime.confidence.toFixed(0));
    const chips = within(screen.getByTestId("semi-chips")).getAllByText(/./, { selector: "b" });
    expect(chips.map((c) => c.textContent)).toEqual(cycle.regime.chips.map((c) => c.value));
    expect(card.textContent).not.toMatch(/확률|매수|매도/);
    // EPS 증거는 공급원이 없어 NO DATA — 0 으로 그리지 않는다
    expect(card.querySelector('[data-key="eps_revision"]')!.textContent).toContain("NO DATA");
  });

  // ── 설명 레이어 (2026-11-24) — 숫자 · 판정은 그대로, 뜻과 관계만 더한다 ──
  it("국면의 뜻 · composite/신뢰도/증거 확보 설명 · 구간 기준 · 점수 안내를 보인다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    expect(screen.getByTestId("semi-regime-meaning").textContent).toBe("주요 업황 증거가 상승 방향으로 정렬된 상태");
    const m = screen.getByTestId("semi-confidence");
    expect(m.querySelector('[data-key="composite"]')!.textContent).toContain("+46");
    expect(m.querySelector('[data-key="composite"]')!.textContent).toContain("상승 방향이 뚜렷하게 우세");
    expect(m.querySelector('[data-key="confidence"]')!.textContent).toContain("확신도");
    expect(m.querySelector('[data-key="evidence"]')!.textContent).toContain("82%");
    expect(m.querySelector('[data-key="evidence"]')!.textContent).toContain("확보된 비율");
    expect(screen.getByTestId("semi-thresholds").textContent).toContain("STRONG UPSWING ≥ +55 · UPSWING ≥ +25 · EARLY RECOVERY ≥ +8 · NEUTRAL ≥ -8 · DOWNTURN ≥ -40 · DEEP DOWNTURN 그 아래");
    expect(screen.getByTestId("semi-score-legend").textContent).toContain("× 숫자 = Composite 에 반영되는 가중치");
    expect(screen.getByTestId("semi-path").textContent).toContain("직전 국면 STRONG UPSWING 에서");
    expect(screen.getByTestId("semi-regime").textContent).not.toMatch(/확률|매수|매도|전망/);
  });

  it("지지 · 제약 묶음은 점수의 부호로만 나눈다 — 옛 저장본(CYCLE READ 없음)에서도 보인다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    expect(screen.queryByTestId("semi-cycle-read")).toBeNull();
    expect(screen.queryByTestId("semi-cycle-read-none")).toBeNull(); // 필드가 아예 없는 옛 저장본 — 아무 말도 하지 않는다
    const why = screen.getByTestId("semi-why");
    expect(why.textContent).toContain("WHY UPSWING?");
    const keys = (side: string) => Array.from(why.querySelectorAll(`[data-side="${side}"] [data-key]`)).map((e) => e.getAttribute("data-key"));
    const score = (k: string) => cycle.regime.components.find((x) => x.key === k)!.score!;
    expect(keys("support")).toEqual(["spot_premium", "export", "hbm", "contract"]);
    expect(why.textContent).toContain("그 밖 · Memory Pricing +23 · Breadth +33"); // |점수 × 가중치| 큰 순서, 4개까지
    expect(keys("support").every((k) => score(k!) >= 10)).toBe(true);
    expect(keys("constraint")).toEqual(["equity"]);
    expect(why.textContent).toContain("UPSWING SUPPORT");
    expect(why.textContent).toContain("NO DATA · EPS Revision · Supply / Inventory News");
    expect(why.querySelector('[data-key="contract"] b')!.textContent).toBe("RISING"); // 같은 증거의 상태 칩 단어
    expect(why.querySelector('[data-key="equity"] b')!.textContent).toBe("WEAK");
  });

  it("CYCLE READ — 그날 해설 · 결론 한 줄 · 증거별 메모(서버 값 그대로), 없으면 이유만", () => {
    const c = clone(cycle);
    c.cycle_read = { status: "ok", source: "llm", generator: "session", reason: "", read: "지지 증거가 우세합니다. 다만 주가가 따라오지 않습니다.", verdict: "가격은 강하고 주가만 어긋난 상태",
      support: [{ key: "hbm", label: "HBM", note: "HBM 계약가 앵커 급등" }], constraint: [{ key: "equity", label: "Equity", note: "메모리 대형주 주가 급락" }], warnings: [], generated_at: null };
    const { unmount } = render(<SemiconductorCycleView cycle={c} />);
    expect(screen.getByTestId("semi-cycle-read-text").textContent).toBe(c.cycle_read.read);
    expect(screen.getByTestId("semi-cycle-read").textContent).toContain("세션 생성");
    expect(screen.getByTestId("semi-verdict").textContent).toBe("→ 가격은 강하고 주가만 어긋난 상태");
    const why = screen.getByTestId("semi-why");
    expect(why.querySelector('[data-side="support"] [data-key="hbm"]')!.textContent).toContain("HBM 계약가 앵커 급등");
    expect(why.querySelector('[data-side="constraint"] [data-key="equity"]')!.textContent).toContain("메모리 대형주 주가 급락");
    unmount();
    c.cycle_read = { ...c.cycle_read!, status: "unavailable", source: "none", generator: "none", reason: "LLM 비활성 — 키 없음 또는 설정 off", read: "", verdict: "", support: [], constraint: [] };
    render(<SemiconductorCycleView cycle={c} />);
    expect(screen.queryByTestId("semi-cycle-read")).toBeNull();
    expect(screen.getByTestId("semi-cycle-read-none").textContent).toContain("LLM 비활성");
    expect(screen.getByTestId("semi-why").querySelectorAll("[data-side] [data-key]").length).toBe(5); // 묶음은 점수만으로 그대로
  });

  it("상태 배지 한 줄 설명 — Equity Confirm 은 '현물과 같은 방향인가' 이고 함께 내리면 좋은 색이 아니다", () => {
    const c = clone(cycle);
    const set = (k: string, v: string) => { c.regime.chips.find((x) => x.key === k)!.value = v; };
    c.regime.components.find((x) => x.key === "memory_pricing")!.score = -24;
    set("memory_pricing", "SOFT"); set("equity", "BROAD CONFIRMATION"); set("contract", "RISING · STALE"); set("turning", "EARLY SOFTENING");
    c.turning = { signal: "EARLY SOFTENING", tightening: [], softening: ["DDR5 16Gb 1M 모멘텀 양→음", "breadth 악화"], breadth_trend: "DETERIORATING", note: "" };
    render(<SemiconductorCycleView cycle={c} />);
    const chip = (k: string) => screen.getByTestId("semi-chips").querySelector(`[data-key="${k}"]`)!;
    expect(chip("equity").textContent).toContain("현물 가격과 같은 방향 — 지금은 둘 다 하락");
    expect((chip("equity").querySelector("b") as HTMLElement).style.color).toBe("var(--down)");
    expect(screen.getByTestId("semi-equity-note").textContent).toContain("방향 일치");
    expect(chip("memory_pricing").textContent).toContain("모멘텀 약화");
    expect(chip("contract").textContent).toContain("절반만 반영");
    expect(chip("eps").textContent).toContain("공급원이 없어 계산에서 뺀다");
    expect(chip("export").textContent).toContain("증가 중이지만 증가 속도는 둔화");
    const tp = screen.getByTestId("semi-turning");
    expect(tp.textContent).toContain("현재 Regime 이 아니라");
    expect(tp.textContent).toContain("DDR5 16Gb 1M 모멘텀 양→음 · breadth 악화");
  });

  it("증거 이름을 누르면 무엇을 재는지 · 지금 근거 · composite 몫이 펼쳐진다(몫의 합 = composite)", async () => {
    const { contribution } = await import("../components/semiExplain");
    render(<SemiconductorCycleView cycle={cycle} />);
    expect(screen.queryByTestId("semi-factor-detail")).toBeNull();
    const btn = screen.getAllByTestId("semi-factor-btn").find((b) => b.textContent!.startsWith("Equity"))!;
    fireEvent.click(btn);
    const d = screen.getByTestId("semi-factor-detail");
    expect(d.textContent).toContain("메모리 3사");
    expect(d.textContent).toContain(`${cycle.equity_confirmation.stocks[0]!.label} `);
    expect(d.textContent).toContain("COMPOSITE 몫");
    const sum = cycle.regime.components.reduce((a, x) => a + (contribution(x, cycle.regime.components) ?? 0), 0);
    expect(sum).toBeCloseTo(cycle.regime.composite!, 1);
    fireEvent.click(btn);
    expect(screen.queryByTestId("semi-factor-detail")).toBeNull();
    // 가중치 · 점수 표시는 그대로
    const row = screen.getByTestId("semi-regime").querySelector('.sm-ev-item[data-key="equity"]')!;
    expect(row.textContent).toContain("×0.6");
    expect(row.textContent).toContain("-100");
  });

  it("Market Read 는 2~4문장 해석, 출처(세션 생성)를 밝힌다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    expect(screen.getByTestId("semi-read-text").textContent).toBe(cycle.market_read.read);
    expect(screen.getByTestId("semi-read").textContent).toContain("세션 생성");
  });

  it("가격 표 — 기준 관측이 없는 창은 '–' 이고 0% 로 그리지 않는다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const row = screen.getAllByTestId("semi-price-row").find((r) => r.getAttribute("data-id") === "NAND_256G_TLC_WAFER")!;
    const p = cycle.memory_prices.find((x) => x.id === "NAND_256G_TLC_WAFER")!;
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

describe("1년 과거 이력 차트 (2026-10-23)", () => {
  it("기본은 1Y 이력이 GOOD 인 제품(DDR4 8Gb) · 1Y 범위 — 1년치 Daily State 를 그린다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const chart = screen.getByTestId("semi-chart");
    expect((within(chart).getByTestId("semi-product-select") as HTMLSelectElement).value).toBe("DDR4_8G_SPOT");
    expect(within(chart).getByRole("button", { name: "1Y" }).getAttribute("aria-pressed")).toBe("true");
    const cov = within(chart).getByTestId("semi-chart-coverage");
    expect(cov.getAttribute("data-status")).toBe("GOOD");
    const d4 = cycle.memory_prices.find((p) => p.id === "DDR4_8G_SPOT")!;
    expect(d4.daily!.length).toBeGreaterThanOrEqual(250);
    const first = d4.daily!.filter((r) => r[0] >= "2025-10-22")[0]![0];
    expect(chart.textContent).toContain(first);   // x축 시작 = 1년 전 첫 평일
    expect(within(chart).getByTestId("semi-contract-line")).toBeTruthy();
    expect(within(chart).getByTestId("semi-premium-area")).toBeTruthy();
  });

  it("툴팁에 원천 관측일과 RAW / CARRIED_FORWARD 를 보인다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const chart = screen.getByTestId("semi-chart");
    fireEvent.pointerMove(within(chart).getByTestId("semi-price-svg"), { clientX: 10, clientY: 50 });
    const tip = within(chart).getByTestId("semi-tooltip");
    expect(tip.textContent).toMatch(/Latest Source Observation \d{4}-\d{2}-\d{2}/);
    expect(tip.textContent).toMatch(/Origin (RAW|CARRIED_FORWARD)/);
    expect(tip.textContent).toMatch(/Contract \$[\d.]+ \([A-Z][a-z]{2}-\d{4}\)/);
  });

  it("1Y 를 덮지 못하는 제품은 PARTIAL 과 Available From · 실제 수치로 된 이유를 말한다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const chart = screen.getByTestId("semi-chart");
    fireEvent.change(within(chart).getByTestId("semi-product-select"), { target: { value: "DDR4_16G_SPOT" } });
    const cov = within(chart).getByTestId("semi-chart-coverage");
    expect(cov.getAttribute("data-status")).toBe("PARTIAL");
    expect(cov.textContent).toContain("Available From 2026-02-02");
    expect(within(chart).getByTestId("semi-history-quality").getAttribute("data-class")).toBe("PARTIAL");
  });

  it("DDR5 16Gb — 보존된 공개 화면으로 재구성한 1Y 이력은 RECONSTRUCTED · GOOD, RAW 수는 일간 기대치와 따로", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const chart = screen.getByTestId("semi-chart");
    fireEvent.change(within(chart).getByTestId("semi-product-select"), { target: { value: "DDR5_16G_SPOT" } });
    const d5 = cycle.memory_prices.find((p) => p.id === "DDR5_16G_SPOT")!;
    const hq = within(chart).getByTestId("semi-history-quality");
    expect(hq.getAttribute("data-class")).toBe("RECONSTRUCTED GOOD");
    expect(hq.textContent).toContain("RECONSTRUCTED · GOOD");
    expect(hq.textContent).toContain(`Raw observations ${d5.history_quality!.raw_obs}`);
    expect(hq.textContent).toContain("Internet Archive");
    expect(d5.history_quality!.raw_obs).toBeLessThan(d5.history_quality!.expected_obs);
    expect(chart.textContent).toContain("PROXY PREMIUM");
  });

  it("DDR4 8Gb premium 의 1Y z-score · percentile 은 RAW 관측 기준으로 표시", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const prem = cycle.spot_premium.find((x) => x.spot === "DDR4_8G_SPOT")!;
    expect(prem.z_status).toBe("OK");
    expect(prem.raw_premium_obs!).toBeGreaterThanOrEqual(200);
    expect(screen.getByTestId("semi-premium-stats").textContent).toContain(`percentile ${prem.percentile_1y}%`);
  });

  it("Contract 는 토글로 끌 수 있다", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const chart = screen.getByTestId("semi-chart");
    fireEvent.click(within(chart).getByTestId("semi-contract-toggle"));
    expect(within(chart).queryByTestId("semi-contract-line")).toBeNull();
  });

  it("Data Quality 의 제품별 coverage 표 — GOOD / PARTIAL 과 RAW 관측 수", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const rows = screen.getAllByTestId("semi-coverage-row");
    expect(rows.length).toBe(cycle.coverage_table!.length);
    const d4 = rows.find((r) => r.getAttribute("data-id") === "DDR4_8G_SPOT")!;
    expect(d4.getAttribute("data-coverage")).toBe("GOOD");
    const d5 = rows.find((r) => r.getAttribute("data-id") === "DDR5_16G_SPOT")!;
    expect(d5.getAttribute("data-coverage")).toBe("GOOD");
    expect(d5.getAttribute("data-class")).toBe("RECONSTRUCTED GOOD");
    const d16 = rows.find((r) => r.getAttribute("data-id") === "DDR4_16G_SPOT")!;
    expect(d16.getAttribute("data-coverage")).toBe("PARTIAL");
    expect(d16.textContent).toContain("Available From");
  });

  it("제품별 HISTORY QUALITY — 분류 라벨 · 원천 · 관측 수, coverage 표의 분류", () => {
    render(<SemiconductorCycleView cycle={cycle} />);
    const chart = screen.getByTestId("semi-chart");
    const hq = within(chart).getByTestId("semi-history-quality");
    const d4 = cycle.memory_prices.find((p) => p.id === "DDR4_8G_SPOT")!;
    expect(hq.getAttribute("data-class")).toBe(d4.history_quality!.class);
    expect(hq.textContent).toContain(d4.history_quality!.label);
    expect(hq.textContent).toContain(`Raw observations ${d4.history_quality!.raw_obs}`);
    for (const r of screen.getAllByTestId("semi-coverage-row")) {
      expect(["FULL", "RECONSTRUCTED GOOD", "PARTIAL", "UNAVAILABLE"]).toContain(r.getAttribute("data-class"));
    }
  });

  it("Daily State 칸은 평일만, 'R'/'C' 로 구분된다", () => {
    const d4 = cycle.memory_prices.find((p) => p.id === "DDR4_8G_SPOT")!;
    for (const [d, , o] of d4.daily!) {
      expect([1, 2, 3, 4, 5]).toContain(new Date(`${d}T00:00:00Z`).getUTCDay());
      expect(["R", "C"]).toContain(o);
    }
    expect(d4.daily![d4.daily!.length - 1]![0]).toBe("2026-10-22");   // 저장 시각(10/23 07:30 KST) 이후 날짜 없음
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
