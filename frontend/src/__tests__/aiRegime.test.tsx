/** AI 탭 — AI TRADE INTELLIGENCE. Regime → AI vs Market → Drivers → Leadership → Breadth → Narrative×Price → Macro → Stress → What Changes → Diagnostics. 시장 온도는 핵심 화면에 없다. */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
    // 10/6 실데이터: AI 위험선호 확인 — 바스켓 절대 상승(+0.6σ·5일), Nasdaq 과 같은 걸음, breadth 81% widening, 매크로는 약세를 설명할 필요가 없다
    expect(regime.regime).toBe("confirmed_risk_on");
    expect(regime.macro.verdict).toBe("not_weak");
    const mainText = Array.from(container.querySelectorAll(".panel:not(details)")).map((e) => e.textContent).join(" ");
    expect(mainText).not.toMatch(/시장 온도|냉각\(공포\)|공포·탐욕|확률/);
    expect(screen.getByTestId("ai-context").textContent).toMatch(/맥락 입력/);
  });

  it("섹션 순서가 지정된 대로이고 driver 5 · 그룹 7(바스켓 6 + 국내) · breadth 3 지표 · 2×2 · 내러티브 driver 7 · 매크로 행 · 전환 조건 3~5", () => {
    const { container, unmount } = render(<AiRegimeView regime={regime} snapshot={snapshot} check={check2} history={history} extended />);
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    expect(titles).toEqual(["AI Trade Regime", "AI Sentiment · Greed & Fear", "AI vs Market", "What Is Driving AI?", "AI Chain Snapshot", "AI Fundamental Transmission", "AI Value-Chain Leadership", "Semiconductor Confirmation", "AI Basket Groups", "AI Breadth", "Narrative × Price", "AI Stock Impact Map", "Stock Radar", "News → Value Chain → Stock", "Expectations vs Fundamentals", "Macro Confirmation", "AI-specific Stress", "What Matters Now", "What Changes The View?", "Details / Data Quality"]);
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
    // 상태 띠: ENGLISH CATEGORY / ENGLISH STATUS / 한 줄 한국어 의미. 장문(FC 문장 · SUMMARY · 맥락)은 Details 안으로
    const strip = screen.getByTestId("ai-status-strip");
    expect(within(strip).getAllByTestId("ai-strip-meaning").length).toBe(regime.status_strip.length);
    for (const it of regime.status_strip) expect(strip.textContent).toContain(it.meaning);
    expect(within(strip).getByTestId("ai-regime-read").textContent).toContain(regime.regime_read);
    expect((regime.regime_read.match(/다\./g) ?? []).length).toBeLessThanOrEqual(3);
    if (regime.sentiment && regime.sentiment.secondary_key !== "none") expect(within(strip).getByTestId("ai-key-tension").textContent).toContain(regime.sentiment.secondary_label);
    expect(within(strip).queryByTestId("ai-summary")).toBeNull();
    const diag = within(screen.getByTestId("ai-diagnostics"));
    expect(diag.getByTestId("ai-fundamental-confirmation").textContent).toContain(regime.fundamental_confirmation.level);
    expect(diag.getByTestId("ai-summary").textContent?.length).toBeGreaterThan(20);
    expect(diag.getByTestId("ai-context").textContent).toMatch(/맥락 입력/);
    expect(screen.getByTestId("ai-regime-subtitle").textContent).toContain("FUNDAMENTALS");
    // AI CHAIN VIEW: 기본 화면은 압축(전파 9행 · 상하위 3 · 반도체 6행), 상세 표는 펼쳐야 보인다
    const cv = regime.chain_view;
    expect(screen.getAllByTestId("ai-chain-stage").length).toBe(9);
    expect(screen.getAllByTestId("ai-chain-leader").length).toBe(cv.leaders.length + cv.laggards.length);
    expect(screen.getAllByTestId("ai-chain-semi").length).toBe(6);
    expect(screen.queryAllByTestId("ai-stage").length).toBe(0); expect(screen.queryAllByTestId("ai-segment").length).toBe(0); expect(screen.queryAllByTestId("ai-memory-row").length).toBe(0);
    fireEvent.click(screen.getByTestId("ai-chain-view-segments"));
    expect(screen.getAllByTestId("ai-segment").length).toBe(10);
    expect(within(screen.getByTestId("ai-leadership-list")).getAllByRole("listitem").length).toBe(regime.value_chain.leadership.length);
    fireEvent.click(screen.getByTestId("ai-chain-view-matrix"));
    expect(screen.getAllByTestId("ai-semi-area").length).toBe(6);
    const mem = screen.getAllByTestId("ai-memory-row");
    expect(mem.length).toBe(6);
    expect(mem.filter((m) => m.getAttribute("data-status") === "N/A").length).toBe(regime.semi_confirmation.memory.filter((m) => m.status === "N/A").length);
    fireEvent.click(screen.getByTestId("ai-chain-full"));
    expect(screen.getAllByTestId("ai-stage").length).toBe(9);
    // STOCK IMPACT MAP: 기본은 TOP STOCK SIGNALS 만, View all 로 네 축 전체 표
    const sv = regime.stock_view;
    expect(screen.getAllByTestId("ai-stock-signal").length).toBe(sv.signals.length);
    expect(screen.queryAllByTestId("ai-stock").length).toBe(0);
    fireEvent.click(screen.getByTestId("ai-stock-view-all"));
    const stocks = screen.getAllByTestId("ai-stock");
    expect(stocks.length).toBe(regime.stocks.filter((r) => r.available).length);
    expect(stocks[0]!.querySelectorAll(".ai-sim-ax").length).toBe(4);
    expect(screen.getAllByTestId("ai-radar-bucket").length).toBe(sv.radar.length);
    for (const it of screen.getAllByTestId("ai-radar-item")) expect(within(it).getByTestId("ai-radar-why").textContent?.length).toBeGreaterThan(3);
    expect(screen.getAllByTestId("ai-news-card").length).toBe(sv.news_top.length + Math.min(sv.news_others_default, sv.news_others.length));
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

  it("AI 센티2: AI TRADE REGIME 바로 아래 AI SENTIMENT · GREED & FEAR — 게이지 → 5 factor bar(FUNDAMENTALS·NARRATIVE·PRICE·BREADTH·MACRO) → KEY TENSION → SUPPORT/PRESSURE + NET → 1M(밴드 배경·현재점·NOW/1W/RANGE·변화 한 줄) → READ ≤2문장 · 숫자 나열·큰 legend 없음", () => {
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
    expect(comps.map((c) => c.getAttribute("data-key"))).toEqual(["fundamentals", "narrative", "price", "breadth", "macro"]);
    for (const c of s.components) {
      const el = comps.find((x) => x.getAttribute("data-key") === c.key)!;
      expect(el.textContent).toContain(c.score === null ? "DATA MISSING" : c.score.toFixed(0));
      expect(el.textContent).toContain(c.desc_ko);
      const bar = el.querySelector(".gf-fb-bar i") as HTMLElement | null;
      if (c.score !== null) expect(bar!.style.width).toBe(`${c.score}%`);
    }
    // 읽는 순서: 게이지 → factor → KEY TENSION → DRIVERS → 1M → READ
    const t = sec.textContent!;
    expect(t.indexOf("Why ")).toBeLessThan(t.indexOf("Key tension"));
    expect(t.indexOf("Key tension")).toBeLessThan(t.indexOf("Sentiment Drivers"));
    expect(t.indexOf("Sentiment Drivers")).toBeLessThan(t.indexOf("1M Sentiment"));
    expect(t.indexOf("1M Sentiment")).toBeLessThan(t.indexOf("AI Sentiment Read"));
    expect(within(sec).getByTestId("ai-gf-secondary").textContent).toContain(s.secondary_label);
    expect(within(sec).getByTestId("ai-gf-gap").textContent).toBe(s.gap_read);
    expect(within(sec).getByTestId("ai-gf-support").querySelectorAll("li").length).toBe(Math.min(3, s.support.length));
    expect(within(sec).getByTestId("ai-gf-pressure").querySelectorAll("li").length).toBe(Math.min(3, s.pressure.length));
    expect(within(sec).getByTestId("ai-gf-net").textContent).toContain(s.net_effect);
    const read = within(sec).getByTestId("ai-gf-read").textContent!;
    expect(read).toContain(s.read);
    expect((s.read.match(/다\./g) ?? []).length).toBeLessThanOrEqual(2);
    if (s.history.points.filter((p) => p.index !== null).length >= 2) {
      const spark = within(sec).getByTestId("ai-gf-spark");
      expect(spark.querySelectorAll(".gf-hist-band").length).toBe(5);
      expect(spark.querySelector(".gf-hist-now")).not.toBeNull();
      expect(within(sec).getByTestId("ai-gf-hist-kv").textContent).toMatch(/NOW.*1W.*1M RANGE/);
      expect(within(sec).getByTestId("ai-gf-hist-read").textContent).toBe(s.history.read);
      expect(t).not.toMatch(/\d+ → \d+ → \d+/); // 숫자 나열 없음
    }
    expect(sec.querySelector(".gf-legend")).toBeNull(); // 큰 5개 legend 없음
    expect(sec.querySelector(".panel-body")!.textContent).not.toMatch(/확률|매수|매도/);
    expect(sec.querySelector(".gauge")).toBeNull();
  });

  it("AI 센티2: AI VS MARKET 은 ABSOLUTE / RELATIVE / RELATIVE Z + MARKET READ + compact 표(AI vs Nasdaq 강조) + RELATIVE PERFORMANCE READ + 연결 문구, WHAT IS DRIVING AI 는 EVIDENCE SCORE 범례 + DRIVER VERDICT + driver 카드(질적 라벨 · 한글 의미 · evidence ≤3 · why · PRICE CHECK · 상태 뜻), 클릭하면 전파 경로", () => {
    render(<AiRegimeView regime={regime} snapshot={snapshot} check={check2} history={history} extended />);
    const a = regime.ai_vs_market; const vm = screen.getByTestId("ai-vs-market");
    expect(within(vm).getByTestId("ai-vm-abs").textContent).toContain(a.absolute_trend); expect(within(vm).getByTestId("ai-vm-abs").textContent).toContain(a.absolute_ko);
    expect(within(vm).getByTestId("ai-vm-rel").textContent).toContain(a.relative_trend); expect(within(vm).getByTestId("ai-vm-relz").textContent).toContain(a.relative_z_text);
    expect(within(vm).getByTestId("ai-vm-market-read").textContent).toContain(a.market_read_label); expect(within(vm).getByTestId("ai-vm-market-read").textContent).toContain(a.market_read);
    expect(within(vm).getByTestId("ai-vm-key-row").textContent).toContain("AI vs Nasdaq");
    expect(within(vm).getByTestId("ai-vm-relative-read").textContent).toContain(a.relative_read);
    expect((a.relative_read.match(/다\./g) ?? []).length).toBeLessThanOrEqual(2);
    expect(within(vm).getByTestId("ai-vm-connector").textContent).toContain(a.connector);
    const dv = screen.getByTestId("ai-drivers"); const v = regime.driver_verdict;
    expect(within(dv).getByTestId("ai-score-legend").textContent).toMatch(/−100.*0.*\+100/s);
    expect(within(dv).getByTestId("ai-score-legend").textContent).toContain("확률이 아니라");
    const verdict = within(dv).getByTestId("ai-driver-verdict");
    expect(verdict.textContent).toContain(v.gap_label); expect(verdict.textContent).toContain(v.gap_value);
    const refs = within(verdict).getAllByTestId("ai-verdict-ref");
    expect(refs[0]!.getAttribute("data-id")).toBe(v.primary!.id); expect(refs[0]!.getAttribute("data-role")).toBe(v.primary!.role);
    expect(within(dv).getByTestId("ai-verdict-conclusion").textContent).toBe(v.conclusion);
    // verdict 는 DRIVER 카드보다 먼저
    expect(dv.textContent!.indexOf("Driver verdict")).toBeLessThan(dv.textContent!.indexOf(regime.drivers[0]!.why));
    const cards = within(dv).getAllByTestId("ai-driver");
    expect(cards.length).toBe(5);
    for (const d of regime.drivers) {
      const el = cards.find((c) => c.getAttribute("data-id") === d.id)!;
      expect(within(el).getByTestId("ai-driver-band").textContent).toBe(d.band);
      expect(el.textContent).toContain(d.band_ko); expect(el.textContent).toContain(d.why);
      expect(within(el).getAllByTestId("ai-driver-price-check").length).toBe(d.price_check.length);
      expect(within(el).getByTestId("ai-driver-status").textContent).toContain(d.status);
      expect(within(el).queryByTestId("ai-driver-more")).toBeNull();
      expect(el.textContent).not.toContain("Transmission");
    }
    const bands = new Set(regime.drivers.map((d) => d.band));
    for (const b of bands) expect(["STRONG POSITIVE", "POSITIVE", "NEUTRAL", "NEGATIVE", "STRONG NEGATIVE"]).toContain(b);
    // 클릭 → 전파 경로 · 전체 evidence
    const first = cards.find((c) => c.getAttribute("data-id") === "macro_rates")!;
    fireEvent.click(first);
    expect(within(first).getByTestId("ai-driver-more").textContent).toContain(regime.drivers.find((d) => d.id === "macro_rates")!.transmission[0]);
    // 10/6 실데이터: AI 강세의 primary 는 Broad Risk-Off(CONFIRMED), secondary 는 AI Narrative, Macro / Rates 는 상쇄 압력, 반도체 사이클은 NOT YET CONFIRMED
    expect(v.primary!.id).toBe("broad_risk_off"); expect(v.secondary!.id).toBe("ai_narrative");
    expect(v.offset.some((x) => x.id === "macro_rates")).toBe(true); expect(v.unconfirmed.some((x) => x.id === "semi_cycle")).toBe(true);
    expect(v.conclusion).toMatch(/주로 설명합니다/);
  });

  it("AI 센티2 AI CHAIN VIEW: SNAPSHOT 4 타일 + 한 줄 → FUNDAMENTAL × PRICE(기본 6행, View all 10, VIEW 범례) → 전파 한 줄씩 + FUNDAMENTAL READ → LEADERS/LAGGARDS 3+3 + LEADERSHIP READ → 반도체 상태 행 + 의미 + HBM key evidence; 긴 설명문·숫자 반복 없음", () => {
    render(<AiRegimeView regime={regime} snapshot={snapshot} check={check2} history={history} extended />);
    const cv = regime.chain_view; const snap = screen.getByTestId("ai-chain-snapshot");
    const tiles = within(snap).getByTestId("ai-chain-snap-tiles").textContent!;
    for (const t of [cv.snapshot.fundamentals, cv.snapshot.price_leadership, cv.snapshot.semi_confirmation, cv.snapshot.key_gap]) expect(tiles).toContain(t);
    expect(within(snap).getByTestId("ai-chain-snap-read").textContent).toBe(cv.snapshot.read);
    let rows = within(snap).getAllByTestId("ai-chain-row");
    expect(rows.length).toBe(Math.min(cv.main_rows, cv.rows.length));
    expect(rows[0]!.getAttribute("data-view")).toBe("CONFIRMED"); // 확인된 행이 맨 위
    fireEvent.click(within(snap).getByTestId("ai-chain-view-all"));
    rows = within(snap).getAllByTestId("ai-chain-row"); expect(rows.length).toBe(cv.rows.length);
    for (const r of cv.rows) { const el = rows.find((x) => x.getAttribute("data-key") === r.key)!; expect(el.textContent).toContain(r.fund_status); expect(el.textContent).toContain(r.price_status); expect(el.textContent).toContain(r.view); expect(el.textContent).toContain(r.view_ko); }
    expect(new Set(cv.rows.map((r) => r.view))).toEqual(new Set([...new Set(cv.rows.map((r) => r.view))].filter((v) => ["CONFIRMED", "DIVERGENCE", "FUNDAMENTAL-LED", "PRICE-LED", "MIXED", "WEAK"].includes(v))));
    expect(within(snap).getByTestId("ai-chain-view-legend").textContent).toContain("DIVERGENCE");
    // 9/29: Equipment · Packaging CONFIRMED, HBM DIVERGENCE(펀더멘털 > 가격), key gap HBM
    expect(cv.rows.find((r) => r.key === "equipment")!.view).toBe("CONFIRMED"); expect(cv.rows.find((r) => r.key === "hbm")!.view).toBe("DIVERGENCE"); expect(cv.snapshot.key_gap).toMatch(/HBM/);
    const tr = screen.getByTestId("ai-transmission");
    expect(within(tr).getByTestId("ai-chain-fund-read").textContent).toContain(cv.fundamental_read);
    expect(tr.textContent).not.toContain(regime.transmission.sentence); // 긴 문장 반복 없음
    // 근거 유형 태그 — 결측 입력은 빠진다 (9/29: HBM 은 DATA+NEWS, Equipment 는 PRICE+NEWS, Commodity Memory 는 NO DATA)
    const basisEls = within(tr).getAllByTestId("ai-chain-basis"); expect(basisEls.length).toBe(9);
    for (const st of cv.stages) { const el = basisEls[cv.stages.indexOf(st)]!; for (const b of st.basis) expect(el.textContent).toContain(b); if (!st.basis.length) expect(el.textContent).toContain("NO DATA"); }
    expect(cv.stages.find((x) => x.key === "hbm")!.basis).toEqual(expect.arrayContaining(["DATA"]));
    expect(cv.stages.find((x) => x.key === "commodity_memory")!.basis).toEqual([]);
    expect(within(tr).getByTestId("ai-chain-basis-legend").textContent).toMatch(/NEWS.*PRICE.*DATA/);
    expect(tr.querySelector(".panel-note")!.textContent).toContain(cv.subtitles.transmission);
    const ld = screen.getByTestId("ai-value-chain");
    expect(within(ld).getByTestId("ai-chain-lead-read").textContent).toContain(cv.leadership_read);
    expect(ld.textContent).not.toContain("1주 상대 모멘텀 상위");
    const leaders = within(ld).getAllByTestId("ai-chain-leader"); expect(leaders.length).toBeLessThanOrEqual(6);
    expect(leaders[0]!.textContent).toContain("vs NDX"); expect(leaders[0]!.textContent).toContain("Breadth");
    const sm = screen.getByTestId("ai-semi-confirmation");
    const areas = within(sm).getAllByTestId("ai-chain-semi"); expect(areas.length).toBe(6);
    for (const a of cv.semi_areas) { const el = areas.find((x) => x.textContent!.includes(a.label))!; expect(el.textContent).toContain(a.status); expect(el.textContent).toContain(a.meaning); }
    expect(within(sm).getByTestId("ai-chain-hbm-ev").textContent).toMatch(/HBM3E.*HBM4/);
    expect(sm.textContent).not.toContain(regime.semi_confirmation.sentence);
    expect(within(sm).getByTestId("ai-chain-view-matrix").textContent).toMatch(/PRICE.*REL STRENGTH.*BREADTH.*NEWS \/ FUND.*EPS/);
  });

  it("AI 센티2: AI BASKET GROUPS 와 AI BREADTH 는 각자 BASKET READ / BREADTH READ(최대 3문장, 숫자 나열·'1주 리더는' 식 문장 없음)를 보이고, 기본 탭은 예전 문장 그대로", () => {
    render(<AiRegimeView regime={regime} snapshot={snapshot} check={check2} history={history} extended />);
    const br = screen.getByTestId("ai-basket-read").textContent!; const bd = screen.getByTestId("ai-breadth-read").textContent!;
    expect(br).toContain(regime.leadership.read); expect(bd).toContain(regime.breadth.read);
    for (const txt of [regime.leadership.read, regime.breadth.read]) {
      expect((txt.match(/다\./g) ?? []).length).toBeLessThanOrEqual(3);
      expect(txt).not.toMatch(/1주 리더|1개월 리더|1주 후미|바뀌었다|20일선 위 \d+%|5일선 위 \d+%|오늘 상승 \d+%|%p/);
    }
    expect(screen.queryByTestId("ai-rotation")).toBeNull(); expect(screen.queryByTestId("ai-breadth-sentence")).toBeNull();
    // 10/6: Semis / Networking 이 Nasdaq 을 실제로 outperform → AI 내부 leadership, Software 는 breadth 유지된 단기 약세; breadth 는 단기 엇갈림 · 중기 넓은 참여 · 20DMA 빠른 확산
    expect(regime.leadership.read).toMatch(/AI 내부 leadership 은 Semiconductors \/ Compute/); expect(regime.leadership.read).toMatch(/Software \/ Application.*단기 약세/);
    expect(regime.leadership.read).not.toMatch(/옮겨가고|뚜렷한 AI leadership/);
    expect(regime.breadth.read).toMatch(/참여가 넓은 건강한 상승/); expect(regime.breadth.read).toMatch(/Memory.*내부 참여도가 크게 약해/); expect(regime.breadth.read).toMatch(/20DMA breadth 가 빠르게/);
  });

  it("AI 센티2 STOCK VIEW: IMPACT MAP 은 anomaly 라벨 하나 + 한 줄 read + Fundamental/Macro 만 보이고 클릭하면 상세, RADAR 는 버킷 설명 + Relative/Price/Fundamental + WHY WATCH(버킷당 기본 3), NEWS 는 TOP IMPACT 3 + OTHER + 범례 + 뉴스×가격 관계, 클릭하면 전파 경로", () => {
    render(<AiRegimeView regime={regime} snapshot={snapshot} check={check2} history={history} extended />);
    const sv = regime.stock_view;
    expect(sv.signals.length).toBeLessThanOrEqual(10); expect(sv.signals.length).toBeGreaterThanOrEqual(8);
    expect(sv.all_signals.length).toBe(regime.stocks.filter((r) => r.available).length);
    const rows = screen.getAllByTestId("ai-stock-signal");
    for (const s of sv.signals) {
      const el = rows.find((x) => x.getAttribute("data-id") === s.id)!;
      expect(within(el).getByTestId("ai-stock-label").textContent).toBe(s.label);
      expect(within(el).getByTestId("ai-stock-read").textContent).toBe(s.read);
      expect(within(el).queryByTestId("ai-stock-more")).toBeNull();
      expect(el.textContent).not.toContain("THEME"); // 네 축 나열 없음
      expect(["CONFIRMED", "FUNDAMENTAL LEADING", "RELATIVE BREAKOUT", "RELATIVE BREAKDOWN", "NEWS > PRICE", "MACRO RESILIENT", "PRICE LEADING", "MACRO SENSITIVE", "PRICE > NEWS", "DIVERGENCE"]).toContain(s.label);
      expect((s.read.match(/다\./g) ?? []).length).toBeLessThanOrEqual(2);
    }
    // 같은 세그먼트·같은 라벨은 기본 목록에 2개까지
    const counts = new Map<string, number>(); for (const s of sv.signals) counts.set(`${s.segment}|${s.label}`, (counts.get(`${s.segment}|${s.label}`) ?? 0) + 1);
    for (const n of counts.values()) expect(n).toBeLessThanOrEqual(2);
    fireEvent.click(rows[0]!);
    const more = within(rows[0]!).getByTestId("ai-stock-more").textContent!;
    for (const k of ["What changed", "Price / Relative", "Fundamentals", "News & Sentiment", "Macro exposure", "What to watch"]) expect(more).toContain(k);
    expect(within(rows[0]!).getByTestId("ai-stock-more").querySelectorAll(".sv-watch li").length).toBeLessThanOrEqual(3);
    // 10/6: 한미반도체 RELATIVE BREAKOUT, Sandisk FUNDAMENTAL LEADING, Micron 은 전체 목록에서 CONFIRMED
    expect(sv.signals.find((s) => s.id === "HANMI_SEMI")!.label).toBe("RELATIVE BREAKOUT"); expect(sv.signals.find((s) => s.id === "SNDK")!.label).toBe("FUNDAMENTAL LEADING"); expect(sv.all_signals.find((s) => s.id === "MU")!.label).toBe("CONFIRMED");
    // RADAR
    const radar = screen.getByTestId("ai-radar");
    expect(radar.textContent).toContain(sv.radar_subtitle);
    const buckets = within(radar).getAllByTestId("ai-radar-bucket");
    expect(buckets.map((b) => b.getAttribute("data-key"))).toEqual(["confirmed_leaders", "improving_setups", "divergences", "macro_sensitive"]);
    for (const b of sv.radar) { const el = buckets.find((x) => x.getAttribute("data-key") === b.key)!; expect(el.textContent).toContain(b.desc); expect(within(el).queryAllByTestId("ai-radar-item").length).toBe(Math.min(b.items.length, sv.radar_default)); }
    expect(radar.textContent).not.toMatch(/Radar Score|Conviction/);
    const item = within(radar).getAllByTestId("ai-radar-item")[0]!; expect(item.textContent).toMatch(/Relative.*Price.*Fundamental.*Why watch/s);
    // NEWS
    const news = screen.getByTestId("ai-news-impact");
    expect(within(news).getByTestId("ai-news-legend").textContent).toContain("확률이 아니라");
    expect(within(news).getByTestId("ai-news-top").querySelectorAll('[data-testid="ai-news-card"]').length).toBe(sv.news_top.length);
    expect(sv.news_top.length + sv.news_others.length).toBeGreaterThanOrEqual(8);
    const card = within(news).getAllByTestId("ai-news-card")[0]!;
    expect(card.textContent).toMatch(/Primary impact.*Key stocks.*Price reaction/s);
    expect(within(card).queryByTestId("ai-news-more")).toBeNull();
    fireEvent.click(card);
    const nm = within(card).getByTestId("ai-news-more").textContent!;
    for (const k of ["Why it matters", "Primary", "Secondary", "Tertiary", "Key stocks", "Current price reaction", "System read", "Source"]) expect(nm).toContain(k);
    expect(within(news).getByTestId("ai-news-relation").textContent).toMatch(/CONFIRMED.*CONFIRMED NEGATIVE.*NOT PRICED.*RESILIENT/);
    for (const c of [...sv.news_top, ...sv.news_others]) expect(["CONFIRMED", "CONFIRMED NEGATIVE", "NOT PRICED", "RESILIENT", "UNCLEAR"]).toContain(c.reaction);
    // 우선순위: 단순 최신순·톤 절대값 순이 아니다 — divergence(NOT PRICED/RESILIENT)와 전파 폭이 반영된 priority 내림차순
    const pr = [...sv.news_top, ...sv.news_others].map((c) => c.priority); expect(pr).toEqual([...pr].sort((a, b) => b - a));
  });
});
