/** 실시간 메인 탭 — decision cockpit. MARKET NOW → DRIVERS → CROSS-ASSET → LEADERSHIP → TRANSMISSION → RADAR → CATALYSTS → NEXT → WATCHLIST → DATA. 빈 카드는 숨긴다. */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import hist from "../__fixtures__/state_history.json";
import ckFx from "../__fixtures__/cockpit.json";
import type { Cockpit, IntelligenceSnapshot, MarketStateHistory } from "../api/types";
import { CockpitView } from "../components/CockpitView";

const snapshot = snap as unknown as IntelligenceSnapshot;
const history = hist as unknown as MarketStateHistory;
const cockpit = ckFx as unknown as Cockpit;

describe("CockpitView", () => {
  it("MARKET NOW 가 맨 위: 판정·Conviction·Persistence·Change·핵심 변수 ≤4·한 문장·sparkline·작은 데이터 줄", () => {
    const { container } = render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} />);
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    expect(titles[0]).toBe("Market Now");
    expect(screen.getByTestId("ck-now-label").textContent).toBe(cockpit.market_now.label_text);
    expect(within(screen.getByTestId("ck-key-variables")).getAllByText(/σ/).length).toBeLessThanOrEqual(4);
    expect(screen.getByTestId("ck-sentence").textContent).toContain("환경이다");
    expect(screen.getByTestId("ck-now").textContent).toMatch(/Conviction|Persistence|Change/);
    expect(screen.getByTestId("ck-now").textContent).toMatch(/Last update/);
    // 22일 대형 히스토리 차트·What's Moving·Claude Commentary·Alert Timeline·Data Health 카드는 메인에 없다
    expect(titles).not.toContain("What's Moving");
    expect(titles).not.toContain("Alert · Timeline");
    expect(titles).not.toContain("Data Health");
    expect(titles.some((t) => /Claude Commentary/.test(t ?? ""))).toBe(false);
  });

  it("정보 순서가 REGIME → DRIVERS → CONFIRMATION → LEADERSHIP → TRANSMISSION → RADAR → CATALYSTS → NEXT → WATCHLIST 이고 driver ≤5, 크로스에셋 7행 + 괴리 ≤2, 카탈리스트 ≤12", () => {
    const { container } = render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} />);
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    const expected = ["Market Now", "Today's Market Drivers", "Cross-Asset Confirmation", "Market Leadership", "Market → Stock Transmission", "Stock Radar", "Live Catalysts", "What Matters Next", "Watchlist"];
    expect(titles.filter((t) => expected.includes(t ?? ""))).toEqual(expected.filter((t) => titles.includes(t)));
    expect(screen.getAllByTestId("ck-driver").length).toBeLessThanOrEqual(5);
    for (const d of screen.getAllByTestId("ck-driver")) expect(d.textContent).toMatch(/Why it matters/);
    expect(screen.getAllByTestId("ck-ca-row").length).toBe(7);
    expect(screen.getByTestId("ck-cross").textContent).toMatch(/Regime Confirmation/);
    expect(screen.getByTestId("ck-cross").textContent).not.toMatch(/확률|probab/i);
    expect(screen.getByTestId("ck-divergences").querySelectorAll(".ck-div-row").length).toBeLessThanOrEqual(2);
    expect(screen.getAllByTestId("ck-catalyst").length).toBeLessThanOrEqual(12);
    expect(screen.getAllByTestId("ck-next-item").length).toBeLessThanOrEqual(5);
    expect(screen.getAllByTestId("ck-radar-stock").length).toBeLessThanOrEqual(8);
    for (const r of screen.getAllByTestId("ck-radar-stock")) expect(r.textContent).toMatch(/Why|Watch/);
  });

  it("뉴스는 클릭해 펼치고, 데이터 없는 카드(Earnings)는 숨기며, Details / Diagnostics 는 토글로 연다", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} details={<div data-testid="old-dashboard">old</div>} />);
    expect(screen.queryByTestId("ck-earnings")).toBeNull(); // 컨센서스 없음 → 카드 자체를 숨긴다
    const first = screen.getAllByTestId("ck-catalyst")[0]!;
    expect(first.querySelector(".ck-cat-x")).toBeNull();
    fireEvent.click(first);
    expect(first.querySelector(".ck-cat-x")).not.toBeNull();
    expect(screen.queryByTestId("old-dashboard")).toBeNull();
    fireEvent.click(screen.getByTestId("ck-details-toggle"));
    expect(screen.getByTestId("old-dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("ck-data-status").textContent).toMatch(/DATA/);
  });
});

describe("CockpitView — MARKET REGIME HISTORY · 1M (실시간 2 전용)", () => {
  it("MARKET NOW 바로 다음, DRIVERS 앞에 온다 — 띠는 display regime, 컨텍스트는 Current/Duration/Previous/Transitions/Share, 전환 ≤3, 3M/6M 은 꺼져 있다", () => {
    const { container } = render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} />);
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    expect(titles.indexOf("Market Regime History · 1M")).toBe(titles.indexOf("Market Now") + 1);
    expect(titles.indexOf("Today's Market Drivers")).toBe(titles.indexOf("Market Regime History · 1M") + 1);
    const h = cockpit.history!;
    expect(screen.getByTestId("ck-h-current").textContent).toBe(h.current_label);
    expect(screen.getByTestId("ck-h-ctx").textContent).toMatch(/Duration.*Previous.*1M Transitions.*1M Share/s);
    expect(screen.getAllByTestId("ck-h-cell").length).toBe(h.days.length);
    expect(screen.getAllByTestId("ck-h-transition").length).toBeLessThanOrEqual(3);
    expect(screen.getAllByTestId("ck-h-heat-row").length).toBe(5);
    const ranges = within(screen.getByTestId("ck-history")).getAllByRole("button", { name: /^(1M|3M|6M)$/ });
    expect(ranges.map((b) => (b as HTMLButtonElement).disabled)).toEqual([false, true, true]);
    // 기존 복잡한 플롯의 요소(세 개의 선·판정 라벨 카운트·require/support)는 없다
    expect(screen.getByTestId("ck-history").textContent).not.toMatch(/require|support|확률/);
    expect(screen.getByTestId("ck-history").querySelectorAll("polyline").length).toBe(1);
  });

  it("날짜 셀을 누르면 raw 판정·dominant/end·dwell 상세가, 전환을 누르면 evidence 가 펼쳐진다", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} />);
    const h = cockpit.history!;
    const bridged = h.days.findIndex((d) => d.bridged);
    const cells = screen.getAllByTestId("ck-h-cell");
    fireEvent.click(cells[bridged >= 0 ? bridged : 0]!);
    const detail = screen.getByTestId("ck-h-detail");
    expect(detail.textContent).toContain(h.days[bridged >= 0 ? bridged : 0]!.raw_state);
    expect(detail.textContent).toMatch(/Daily dwell/);
    if (bridged >= 0) expect(detail.textContent).toMatch(/bridged/);
    const tr = screen.getAllByTestId("ck-h-transition")[0]!;
    fireEvent.click(tr);
    expect(tr.querySelectorAll("li").length).toBeGreaterThanOrEqual(2);
  });
});
