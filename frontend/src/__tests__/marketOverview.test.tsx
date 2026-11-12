/** MARKET OVERVIEW · 시장 종합 (2026-11-12) — 13개 섹션 순서, 판단(LLM) 먼저 · 숫자는 기존 섹션, 상세 탭 연결, 종합이 없는 날짜도 숫자 칸은 그 날짜 데이터로. */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import ckFx from "../__fixtures__/cockpit.json";
import aiFx from "../__fixtures__/ai_regime.json";
import moFx from "../__fixtures__/market_overview.json";
import type { AiRegime, Cockpit, MarketOverview } from "../api/types";
import { MarketOverviewView } from "../components/MarketOverviewView";

const cockpit = ckFx as unknown as Cockpit;
const ai = aiFx as unknown as AiRegime;
const mo = moFx as unknown as MarketOverview;
const ORDER = ["mo-view", "mo-regime", "mo-drivers", "mo-equity", "mo-rates", "mo-cross", "mo-aisemi", "mo-lead", "mo-style", "mo-risk", "mo-cat", "mo-next", "mo-port"];

describe("MARKET OVERVIEW", () => {
  it("13개 섹션이 top-down 순서로, 맨 위에 LLM 판단(헤드라인 · 종합 · 4개 요약)", () => {
    const { container } = render(<MarketOverviewView cockpit={cockpit} overview={mo} rates={null} oil={null} ai={ai} semi={null} />);
    const ids = Array.from(container.querySelectorAll("[data-testid^='mo-']")).map((e) => e.getAttribute("data-testid")).filter((x) => ORDER.includes(x!));
    expect(ids).toEqual(ORDER);
    expect(screen.getByTestId("mo-headline").textContent).toBe(mo.view!.headline);
    expect(screen.getByTestId("mo-synthesis").textContent).toBe(mo.view!.market_view);
    expect(within(screen.getByTestId("mo-labels")).getByText("IMPROVING")).toBeTruthy();
    expect(screen.getAllByTestId("mo-driver")).toHaveLength(mo.view!.key_drivers.length);
    expect(screen.getAllByTestId("mo-risk-row").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByTestId("mo-next-row").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByTestId("mo-port").textContent).toMatch(/매매 지시가 아니다/);
  });

  it("없는 섹션은 EXCLUDED — 지금 값으로 메우지 않는다", () => {
    render(<MarketOverviewView cockpit={cockpit} overview={mo} rates={null} oil={null} ai={null} semi={null} />);
    expect(screen.getByTestId("mo-rates").textContent).toMatch(/EXCLUDED/);
    expect(screen.getByTestId("mo-semi").textContent).toMatch(/EXCLUDED/);
  });

  it("종합 코멘트가 없는 날짜도 숫자 칸은 그대로, 해석 칸은 '없음'", () => {
    render(<MarketOverviewView cockpit={cockpit} overview={null} overviewError="DATA UNAVAILABLE FOR THIS DATE" rates={null} oil={null} ai={ai} semi={null} archived />);
    expect(screen.getByTestId("mo-view-none").textContent).toMatch(/종합 코멘트 없음/);
    expect(screen.queryByTestId("mo-headline")).toBeNull();
    expect(screen.getByTestId("mo-regime").textContent).toMatch(/OFFICIAL/);
    expect(screen.getByTestId("mo-ai").textContent).toContain(ai.regime_label);
  });

  it("DETAIL → 는 기존 탭으로", () => {
    const go = vi.fn();
    render(<MarketOverviewView cockpit={cockpit} overview={mo} rates={null} oil={null} ai={ai} semi={null} onDetail={go} />);
    fireEvent.click(screen.getAllByTestId("mo-detail-live")[0]!);
    fireEvent.click(screen.getByTestId("mo-detail-oil"));
    expect(go.mock.calls.map((c) => c[0])).toEqual(["live", "oil"]);
  });
});
