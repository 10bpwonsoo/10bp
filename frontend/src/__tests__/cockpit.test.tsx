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
