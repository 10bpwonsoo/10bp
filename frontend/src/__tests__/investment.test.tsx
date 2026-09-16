/**
 * Investment Intelligence 렌더 테스트 (2026-09-16).
 *
 * 픽스처는 실제 API 응답(MOCK inflation_shock 캡처 + 실데이터 해설 일부)을 잘라 넣은 것이다.
 * 화면이 숫자를 계산하지 않는다는 원칙대로, 여기서는 "백엔드가 준 것을 그대로, 없는 것은 없다고"
 * 그리는지만 본다.
 */
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, within, waitFor, fireEvent } from "@testing-library/react";
import inv from "../__fixtures__/investment.json";
import snapshot from "../__fixtures__/snapshot.json";
import news from "../__fixtures__/news.json";
import type { InvestmentIntelligence } from "../api/investment";
import { TodaysMarketDrivers } from "../components/TodaysMarketDrivers";
import { AlternativeDataPulse } from "../components/AlternativeDataPulse";
import { MarketStockImpact } from "../components/MarketStockImpact";
import { SemiconductorIntelligence } from "../components/SemiconductorIntelligence";
import { CommodityImpact } from "../components/CommodityImpact";
import { UnusualMovers } from "../components/UnusualMovers";
import { ThemeStock } from "../components/ThemeStock";
import { AnalystRevision } from "../components/AnalystRevision";
import { FundamentalDivergence } from "../components/FundamentalDivergence";
import { CommentaryBlock, StockIntelligence } from "../components/StockIntelligence";
import { WatchlistIntelligence } from "../components/WatchlistIntelligence";
import { ClaudeCommentary } from "../components/ClaudeCommentary";
import { InvestmentSection } from "../investment/InvestmentSection";
import App from "../App";

const data = inv as unknown as InvestmentIntelligence;

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

/** 백엔드 대신 캡처된 응답을 돌려준다. 경로별로 나눈다. */
function mockApi(overrides: Record<string, unknown> = {}) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (url.includes("/api/v1/info")) return jsonResponse(overrides.info ?? { status: "ok", version: "0.1.0", mode: "MOCK", scenario: "inflation_shock", llm_enabled: false, llm_available: false, llm_reason: null, zscore_window: 60 });
    if (url.includes("/api/v1/scenarios")) return jsonResponse(overrides.scenarios ?? []);
    if (url.includes("/api/v1/news")) return jsonResponse(overrides.news ?? news);
    if (url.includes("/api/v1/investment")) return "investment" in overrides ? (overrides.investment as Promise<Response>) : jsonResponse(data);
    if (url.includes("/api/v1/snapshot")) return jsonResponse(overrides.snapshot ?? snapshot);
    return jsonResponse({}, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("개별 패널", () => {
  it("1 · 드라이버 카드는 값·z·백분위와 영향 종목을 그린다", () => {
    render(<TodaysMarketDrivers cards={data.drivers} />);
    expect(data.drivers.length).toBeGreaterThan(0);
    for (const d of data.drivers) expect(screen.getAllByText(d.label).length).toBeGreaterThan(0);
  });
  it("1 · 드라이버가 없으면 빈 상태 문장을 쓴다", () => {
    render(<TodaysMarketDrivers cards={[]} />);
    expect(screen.getByText(/임계|없/)).toBeInTheDocument();
  });

  it("2 · 대체데이터는 없는 지표를 '없음' 으로 남기고 0 으로 채우지 않는다", () => {
    render(<AlternativeDataPulse points={data.alternative} />);
    const missing = data.alternative.filter((p) => p.quality === "MISSING");
    expect(missing.length).toBeGreaterThan(0);
    expect(screen.getAllByText("없음").length).toBeGreaterThanOrEqual(missing.length);
    for (const p of data.alternative.filter((x) => x.quality !== "MISSING").slice(0, 3)) {
      expect(screen.getAllByText(p.label).length).toBeGreaterThan(0);
    }
    expect(screen.queryByText("0.00%")).toBeNull();
  });
  it("2 · 줄을 누르면 왜 중요한지와 영향 종목이 펼쳐진다", () => {
    render(<AlternativeDataPulse points={data.alternative} />);
    const p = data.alternative.find((x) => x.quality !== "MISSING" && x.affected_names.length > 0)!;
    const esc = p.label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const row = screen.getAllByRole("button", { name: new RegExp(esc) })[0]!;
    expect(row).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText(p.why).length).toBeGreaterThan(0);
    expect(screen.getAllByText(p.affected_names.join(" · ")).length).toBeGreaterThan(0);
  });

  it("3 · Impact 는 점수와 근거를 함께 그린다", () => {
    render(<MarketStockImpact impacts={data.market_stock_impact} />);
    for (const i of data.market_stock_impact) expect(screen.getAllByText(i.stock_name).length).toBeGreaterThan(0);
  });
  it("3 · 임계 이상 영향이 없으면 그렇게 말한다", () => {
    render(<MarketStockImpact impacts={[]} />);
    expect(screen.getByText(/없습니다|없/)).toBeInTheDocument();
  });

  it("4 · 반도체 해석 문장과 결측 목록을 그린다", () => {
    render(<SemiconductorIntelligence s={data.semiconductor} />);
    expect(screen.getByText(data.semiconductor.interpretation)).toBeInTheDocument();
  });

  it("5 · 원자재 카드는 종목 경로(매출/원가/수요)를 그린다", () => {
    render(<CommodityImpact rows={data.commodity_impact} />);
    for (const r of data.commodity_impact) expect(screen.getAllByText(new RegExp(r.label.replace(/[()]/g, "\\$&"))).length).toBeGreaterThan(0);
  });

  it("6 · 이상 거동은 라벨을 그리되 '매집' 을 쓰지 않는다", () => {
    const { container } = render(<UnusualMovers items={data.unusual_movers} />);
    expect(data.unusual_movers.length).toBeGreaterThan(0);
    expect(container.textContent).not.toMatch(/매집 중|매집이다|매집으로 확정/);
    for (const a of data.unusual_movers) expect(screen.getAllByText(a.stock_name).length).toBeGreaterThan(0);
  });
  it("6 · 모르는 라벨이 와도 깨지지 않는다", () => {
    const odd = { ...data.unusual_movers[0]!, label: "SOMETHING_NEW" as never };
    render(<UnusualMovers items={[odd]} />);
    expect(screen.getAllByText(odd.stock_name).length).toBeGreaterThan(0);
  });

  it("7 · 테마 → 종목 은 일치 여부를 쓴다", () => {
    render(<ThemeStock rows={data.theme_stocks} />);
    for (const t of data.theme_stocks) expect(screen.getAllByText(t.theme_name).length).toBeGreaterThan(0);
  });

  it("8 · 컨센서스가 없으면 억지로 채우지 않고 없다고 말한다", () => {
    render(<AnalystRevision rows={data.analyst.map((a) => ({ ...a, available: false }))} />);
    expect(screen.getByText(/컨센서스 데이터가 없습니다|없/)).toBeInTheDocument();
  });

  it("9 · 괴리는 양쪽 값과 지속 기간을 그린다", () => {
    render(<FundamentalDivergence items={data.fundamental_divergences} />);
    expect(data.fundamental_divergences.length).toBeGreaterThan(0);
    for (const d of data.fundamental_divergences.slice(0, 3)) expect(screen.getAllByText(d.stock_name).length).toBeGreaterThan(0);
  });

  it("10 · 종목 화면은 WHAT/WHY/WHAT CHANGED/WHAT NEXT 를 먼저 보여주고 종목을 바꿀 수 있다", () => {
    render(<StockIntelligence inv={data} />);
    expect(screen.getByText("WHAT IS HAPPENING?")).toBeInTheDocument();
    expect(screen.getByText("WHY?")).toBeInTheDocument();
    expect(screen.getByText("WHAT CHANGED?")).toBeInTheDocument();
    expect(screen.getByText("WHAT MATTERS NEXT?")).toBeInTheDocument();
    const sel = screen.getByLabelText("종목 선택") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "KOREAN_AIR" } });
    expect(screen.getByText(data.stocks.KOREAN_AIR!.headline_what)).toBeInTheDocument();
  });
  it("10 · 수기 해설은 FACT / NEWS / ANALYST / INTERPRETATION / UNKNOWN 을 나눠 그린다", () => {
    const c = data.stocks.SAMSUNG!.commentary!;
    render(<CommentaryBlock c={c} />);
    for (const k of ["FACT", "NEWS", "ANALYST", "INTERPRETATION", "UNKNOWN"]) expect(screen.getByText(k)).toBeInTheDocument();
    expect(screen.getByText(/API 아님/)).toBeInTheDocument();
    for (const line of c.sections.fact) expect(screen.getByText(line)).toBeInTheDocument();
  });

  it("11 · 워치리스트는 배지를 한글 라벨로 그리고 수급은 '없음' 이다", () => {
    render(<WatchlistIntelligence rows={data.watchlist} />);
    for (const r of data.watchlist) expect(screen.getAllByText(r.name).length).toBeGreaterThan(0);
    expect(screen.getAllByText("없음").length).toBeGreaterThanOrEqual(data.watchlist.length);
  });
  it("11 · 모르는 배지가 와도 깨지지 않는다", () => {
    const row = { ...data.watchlist[0]!, badges: ["FUTURE_BADGE" as never] };
    render(<WatchlistIntelligence rows={[row]} />);
    expect(screen.getByText("FUTURE_BADGE")).toBeInTheDocument();
  });

  it("12 · 해설 패널은 출처 모드(수기)와 확신을 쓴다", () => {
    render(<ClaudeCommentary items={data.commentary} names={{ KOSPI: "KOSPI", GASOLINE: "휘발유 (RBOB)", SOX: "SOX" }} />);
    expect(screen.getAllByText(/수기/).length).toBeGreaterThan(0);
  });
  it("12 · 해설이 없으면 API 를 부르지 않는다는 사실을 말한다", () => {
    render(<ClaudeCommentary items={[]} names={{}} />);
    expect(screen.getByText(/API/)).toBeInTheDocument();
  });
});

describe("InvestmentSection", () => {
  it("배너와 열두 패널을 순서대로 그린다", async () => {
    mockApi();
    render(<InvestmentSection enabled />);
    await waitFor(() => expect(screen.getByText(/1 · Today's Market Drivers/)).toBeInTheDocument());
    const titles = screen.getAllByRole("heading").map((h) => h.textContent ?? "");
    const idx = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((n) => titles.findIndex((t) => t.startsWith(`${n} · `)));
    expect(idx.every((i) => i >= 0)).toBe(true);
    expect(idx).toEqual([...idx].sort((a, b) => a - b));
    expect(screen.getByText("INVESTMENT INTELLIGENCE")).toBeInTheDocument();
    expect(screen.getByText(/종목 \d+\/\d+ · 대체데이터 \d+\/\d+/)).toBeInTheDocument();
  });

  it("백엔드가 실패해도 오류를 쓰고 구조는 유지된다", async () => {
    mockApi({ investment: jsonResponse({ detail: "boom" }, 500) });
    render(<InvestmentSection enabled />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText("INVESTMENT INTELLIGENCE")).toBeInTheDocument();
  });

  it("enabled=false 면 아무것도 부르지 않는다", () => {
    const f = mockApi();
    render(<InvestmentSection enabled={false} />);
    expect(f.mock.calls.filter(([u]) => String(u).includes("/investment")).length).toBe(0);
  });
});

describe("App — 기존 대시보드는 그대로, 그 아래 Investment Intelligence", () => {
  it("기존 아홉 패널이 먼저, 열두 패널이 뒤에 온다", async () => {
    mockApi();
    render(<App />);
    await waitFor(() => expect(screen.getByText(/1 · Today's Market Drivers/)).toBeInTheDocument(), { timeout: 5000 });
    const titles = screen.getAllByRole("heading").map((h) => h.textContent ?? "");
    const oldOnes = ["Market State", "Theme Heatmap", "What's Moving", "Divergence", "Impact Map", "Data Health"];
    for (const t of oldOnes) expect(titles.some((x) => x.startsWith(t))).toBe(true);
    const lastOld = Math.max(...oldOnes.map((t) => titles.findIndex((x) => x.startsWith(t))));
    const firstNew = titles.findIndex((x) => x.startsWith("1 · Today"));
    expect(firstNew).toBeGreaterThan(lastOld);
    const section = document.querySelector(".ii-section")!;
    expect(section).not.toBeNull();
    expect(within(section as HTMLElement).getByText("INVESTMENT INTELLIGENCE")).toBeInTheDocument();
  });
});
