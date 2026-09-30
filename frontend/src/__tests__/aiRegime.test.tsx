/** AI 탭 — AI TRADE INTELLIGENCE. Regime → AI vs Market → Drivers → Leadership → Breadth → Narrative×Price → Macro → Stress → What Changes → Diagnostics. 시장 온도는 핵심 화면에 없다. */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import hist from "../__fixtures__/state_history.json";
import regimeFx from "../__fixtures__/ai_regime.json";
import checksFx from "../__fixtures__/scenario_check.json";
import type { AiRegime, IntelligenceSnapshot, MarketStateHistory, ScenarioCheck } from "../api/types";
import { AiRegimeView } from "../components/AiRegimeView";
import { ScenarioView } from "../components/ScenarioView";

const snapshot = snap as unknown as IntelligenceSnapshot;
const history = hist as unknown as MarketStateHistory;
const regime = regimeFx as unknown as AiRegime;
const check: ScenarioCheck = { ...(checksFx as unknown as ScenarioCheck[]).find((c) => c.name === "ai_sentiment")!, focus: "ai_regime" };
const check2: ScenarioCheck = { ...check, name: "ai_sentiment2", title: "AI 센티2 — 확장", focus: "ai_regime_full" };

describe("AiRegimeView", () => {
  it("최상단이 AI TRADE REGIME 이고 상대 z·지배 driver·스트레스를 말하며, 시장 온도/냉각(공포) 표현은 핵심 화면에 없다", () => {
    const { container } = render(<AiRegimeView regime={regime} snapshot={snapshot} check={check} history={history} />);
    expect(screen.getByTestId("ai-regime-label").textContent).toBe(regime.regime_label);
    expect(screen.getByTestId("ai-rel-summary").textContent).toMatch(/AI vs NASDAQ 100/);
    expect(screen.getByTestId("ai-rel-summary").textContent).toContain(regime.ai_vs_market.rel_verdict.toUpperCase());
    // 9/29 실데이터: 매크로에 눌린 AI 약세 — 절대 하락, Nasdaq 대비 −0.7σ (AI-specific 문턱 −1 은 아님), 매크로 6/6 설명
    expect(regime.regime).toBe("macro_dragged");
    expect(regime.macro.verdict).toBe("macro_driven");
    const mainText = Array.from(container.querySelectorAll(".panel:not(details)")).map((e) => e.textContent).join(" ");
    expect(mainText).not.toMatch(/시장 온도|냉각\(공포\)|공포·탐욕|확률/);
    expect(screen.getByTestId("ai-context").textContent).toMatch(/맥락 입력/);
  });

  it("섹션 순서가 지정된 대로이고 driver 5 · 그룹 7(바스켓 6 + 국내) · breadth 3 지표 · 2×2 · 내러티브 driver 7 · 매크로 행 · 전환 조건 3~5", () => {
    const { container, unmount } = render(<AiRegimeView regime={regime} snapshot={snapshot} check={check2} history={history} extended />);
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    expect(titles).toEqual(["AI Trade Regime", "AI Sentiment · Greed & Fear", "AI vs Market", "What Is Driving AI?", "AI Fundamental Transmission", "AI / Semi / Infra / Software Leadership", "Semiconductor Fundamental Confirmation", "AI Basket Groups", "AI Breadth", "Narrative × Price", "AI Stock Impact Map", "Stock Radar", "News → Value Chain → Stock", "Expectations vs Fundamentals", "Macro Confirmation", "AI-specific Stress", "What Matters Now", "What Changes The View?", "Details / Data Quality"]);
    unmount();
    // AI 센티(기본) 는 확장 블록 없이 원래 순서
    const basic = render(<AiRegimeView regime={regime} snapshot={snapshot} check={check} history={history} />);
    expect(Array.from(basic.container.querySelectorAll(".panel-title")).map((e) => e.textContent)).toEqual(["AI Trade Regime", "AI vs Market", "What Is Driving AI?", "AI Leadership", "AI Breadth", "Narrative × Price", "Macro Confirmation", "AI-specific Stress", "What Changes The View?", "Diagnostics"]);
    expect(basic.queryByTestId("ai-status-strip")).toBeNull();
    expect(basic.queryByTestId("ai-sentiment")).toBeNull(); // 게이지는 AI 센티2 에만
    basic.unmount();
    render(<AiRegimeView regime={regime} snapshot={snapshot} check={check2} history={history} extended />);
    expect(screen.getAllByTestId("ai-driver").length).toBe(5);
    const groups = screen.getAllByTestId("ai-group");
    expect(groups.length).toBe(7);
    expect(groups.map((g) => g.getAttribute("data-key")).slice(0, 6)).not.toContain("korea_ai");
    expect(groups[groups.length - 1]!.getAttribute("data-key")).toBe("korea_ai");
    expect(within(screen.getByTestId("ai-vs-market")).getAllByRole("row").length).toBe(5);
    expect(screen.getByTestId("ai-breadth").textContent).toMatch(/> 5DMA.*> 20DMA.*ADVANCING/s);
    const quads = screen.getAllByTestId("ai-quadrant");
    expect(quads.length).toBe(4);
    expect(quads.filter((q) => q.getAttribute("data-on") === "1").length).toBe(regime.narrative.quadrant === "unclear" ? 0 : 1);
    expect(screen.getAllByTestId("ai-narrative-driver").length).toBe(7);
    expect(document.querySelectorAll('.ai-mac[data-status="EXPLAINS"]').length).toBe(regime.macro.rows.filter((r) => r.status === "EXPLAINS").length);
    expect(screen.getByTestId("ai-stress-level").textContent).toBe(regime.stress.level);
    const trig = screen.getAllByTestId("ai-trigger");
    expect(trig.length).toBeGreaterThanOrEqual(3);
    expect(trig.length).toBeLessThanOrEqual(5);
    expect(screen.getAllByTestId("ai-release").length).toBeGreaterThanOrEqual(1);
  });

  it("리더십 회전·breadth 문장이 있고, 서명 대조·판정 규칙·구성원 표·공포·탐욕 띠는 Diagnostics(details) 안에만 있다", () => {
    const { container } = render(<AiRegimeView regime={regime} snapshot={snapshot} check={check} history={history} />);
    expect(screen.getByTestId("ai-rotation").getAttribute("data-rotation")).toBe(regime.leadership.rotation);
    expect(screen.getByTestId("ai-breadth-sentence").textContent).toMatch(/20일선/);
    const diag = screen.getByTestId("ai-diagnostics");
    expect(within(diag).getAllByTestId("ai-check").length).toBe(regime.checks.length);
    expect(within(diag).getAllByTestId("ai-member").length).toBe(regime.members.length);
    expect(within(diag).getAllByText(/require|서명/i).length).toBeGreaterThan(0);
    const mainText = Array.from(container.querySelectorAll(".panel:not(details)")).map((e) => e.textContent).join(" ");
    expect(mainText).not.toMatch(/require/);
  });

  it("확장 층(AI 센티2): 상태 띠에 FUNDAMENTAL CONFIRMATION 이 있고, 전파 체인 9단계, 밸류체인 10세그먼트, 반도체 영역 6 + 메모리 6행(변화율 없는 행은 N/A), 종목 4축, 레이더 5버킷(이유 포함), 뉴스→종목, 기대 vs 펀더멘털 10행, What Matters ≤5", () => {
    const { container } = render(<AiRegimeView regime={regime} snapshot={snapshot} check={check2} history={history} extended />);
    expect(screen.getByTestId("ai-fundamental-confirmation").textContent).toContain(regime.fundamental_confirmation.level);
    expect(screen.getByTestId("ai-regime-subtitle").textContent).toContain("FUNDAMENTALS");
    expect(screen.getByTestId("ai-summary").textContent?.length).toBeGreaterThan(20);
    expect(screen.getAllByTestId("ai-stage").length).toBe(9);
    expect(screen.getAllByTestId("ai-segment").length).toBe(10);
    expect(within(screen.getByTestId("ai-leadership-list")).getAllByRole("listitem").length).toBe(regime.value_chain.leadership.length);
    expect(screen.getAllByTestId("ai-semi-area").length).toBe(6);
    const mem = screen.getAllByTestId("ai-memory-row");
    expect(mem.length).toBe(6);
    expect(mem.filter((m) => m.getAttribute("data-status") === "N/A").length).toBe(regime.semi_confirmation.memory.filter((m) => m.status === "N/A").length);
    const stocks = screen.getAllByTestId("ai-stock");
    expect(stocks.length).toBe(regime.stocks.filter((r) => r.available).length);
    expect(stocks[0]!.querySelectorAll(".ai-sim-ax").length).toBe(4);
    expect(screen.getAllByTestId("ai-radar-bucket").length).toBe(5);
    for (const it of screen.getAllByTestId("ai-radar-item")) expect(it.querySelector(".ai-radar-r")?.textContent?.length).toBeGreaterThan(3);
    expect(screen.getAllByTestId("ai-news-row").length).toBe(regime.news_impact.length);
    expect(screen.getAllByTestId("ai-gap-row").length).toBe(10);
    expect(screen.getAllByTestId("ai-matters-item").length).toBeLessThanOrEqual(5);
    // 업사이클 판정·신호 n/4·서명 일치도는 핵심 화면에 없다
    const mainText = Array.from(container.querySelectorAll(".panel:not(details)")).map((e) => e.textContent).join(" ");
    expect(mainText).not.toMatch(/업사이클 \d+%|신호 \d\/4|일치도|require/);
    expect(within(screen.getByTestId("ai-diagnostics")).getByTestId("ai-data-quality")).toBeInTheDocument();
  });

  it("ScenarioView 는 AI 탭(focus=ai_regime)에서 이 화면을 그리고, 아직 못 받았으면 로딩 문구를 낸다", () => {
    const { unmount } = render(<ScenarioView check={check} snapshot={snapshot} history={history} investment={null} aiRegime={regime} />);
    expect(screen.getByTestId("ai-regime")).toBeInTheDocument();
    expect(screen.queryByTestId("ai-transmission")).toBeNull();
    unmount();
    const r2 = render(<ScenarioView check={check2} snapshot={snapshot} history={history} investment={null} aiRegime={regime} />);
    expect(r2.getByTestId("ai-transmission")).toBeInTheDocument();
    r2.unmount();
    render(<ScenarioView check={check} snapshot={snapshot} history={history} investment={null} />);
    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument();
  });

  it("AI 센티2: AI TRADE REGIME 바로 아래 AI SENTIMENT · GREED & FEAR 반원 게이지 — 0~100 · 5 밴드 · 바늘 각도 −90°+s/100×180° · 구성요소 5 · READ · SUPPORT/PRESSURE ≤3 · 1M 스파크라인 · 확률 표현 없음", () => {
    const { container } = render(<AiRegimeView regime={regime} snapshot={snapshot} check={check2} history={history} extended />);
    const s = regime.sentiment!;
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    expect(titles.indexOf("AI Sentiment · Greed & Fear")).toBe(titles.indexOf("AI Trade Regime") + 1);
    expect(titles.indexOf("AI vs Market")).toBe(titles.indexOf("AI Sentiment · Greed & Fear") + 1);
    const sec = screen.getByTestId("ai-sentiment");
    expect(within(sec).getByTestId("ai-gf-index").textContent).toBe(s.index!.toFixed(0));
    expect(within(sec).getByTestId("ai-gf-state").textContent).toBe(s.state_label);
    expect(within(sec).getAllByTestId("ai-gf-band").length).toBe(5);
    expect(within(sec).getByTestId("ai-gf-needle").getAttribute("data-deg")).toBe((-90 + (s.index! / 100) * 180).toFixed(1));
    expect(within(sec).getByTestId("ai-gf-change").textContent).toContain("1D");
    const comps = within(sec).getAllByTestId("ai-gf-component");
    expect(comps.map((c) => c.getAttribute("data-key"))).toEqual(["narrative", "price", "breadth", "fundamentals", "macro"]);
    for (const c of s.components) {
      const el = comps.find((x) => x.getAttribute("data-key") === c.key)!;
      expect(el.textContent).toContain(c.score === null ? "DATA MISSING" : c.score.toFixed(0));
      expect(el.textContent).toContain(c.read);
    }
    expect(within(sec).getByTestId("ai-gf-read").textContent).toContain(s.read);
    expect(within(sec).getByTestId("ai-gf-secondary").textContent).toContain(s.secondary_label);
    expect(within(sec).getByTestId("ai-gf-support").querySelectorAll("li").length).toBe(Math.min(3, s.support.length));
    expect(within(sec).getByTestId("ai-gf-pressure").querySelectorAll("li").length).toBe(Math.min(3, s.pressure.length));
    if (s.history.points.filter((p) => p.index !== null).length >= 2) expect(within(sec).getByTestId("ai-gf-spark")).toBeInTheDocument();
    expect(sec.querySelector(".panel-body")!.textContent).not.toMatch(/확률|매수|매도/); // 머리글의 "확률·전망 아님" 은 의도된 고지
    // 기존 horizontal thermometer 는 쓰지 않는다
    expect(sec.querySelector(".gauge")).toBeNull();
  });
});
