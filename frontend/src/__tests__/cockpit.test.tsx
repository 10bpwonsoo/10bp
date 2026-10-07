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
    expect(titles.indexOf("Market Tone Snapshot")).toBe(titles.indexOf("Market Regime History · 1M") + 1); // 사이에 MARKET TONE SNAPSHOT
    expect(titles.indexOf("Today's Market Drivers")).toBe(titles.indexOf("Market Regime History · 1M") + 2);
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

describe("CockpitView — STOCK RADAR analyst view · WHAT MATTERS NEXT transmission path", () => {
  it("radar 에는 확인된 종목만 ANALYST VIEW 한 줄(이름·증권사·날짜·freshness)이 붙고, 누르면 상세(Key view·Key variable·Source·System vs Analyst)가 열린다; 없는 종목은 줄 자체가 없다", async () => {
    const av = (await import("../__fixtures__/analyst_views.json")).default as unknown as import("../api/types").AnalystViews;
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={av} />);
    const lines = screen.getAllByTestId("ck-analyst-view");
    expect(lines.length).toBe(av.views.length);
    expect(lines.length).toBeLessThan(cockpit.radar.length); // 확인 안 된 종목은 숨긴다
    for (const l of lines) expect(l.textContent).toMatch(/Analyst view · \d+D/);
    const first = av.views[0]!;
    const line = lines.find((l) => l.textContent?.includes(first.analyst))!;
    expect(line.textContent).toContain(first.broker);
    expect(line.textContent).toContain(first.summary);
    expect(screen.queryByTestId("ck-analyst-detail")).toBeNull();
    fireEvent.click(line);
    const d = screen.getByTestId("ck-analyst-detail");
    expect(d.textContent).toMatch(/Key view/); expect(d.textContent).toMatch(/Key variable/);
    expect(d.querySelector("a")!.getAttribute("href")).toBe(first.source_url);
    expect(screen.getByTestId("ck-system-vs-analyst").textContent).toMatch(/System vs Analyst/);
    expect(screen.getByTestId("ck-system-vs-analyst").textContent).toMatch(/결론이 아니다/);
    // 시스템 축과 애널리스트 줄은 섞이지 않는다
    const card = screen.getByTestId("ck-radar");
    expect(card.textContent).toMatch(/System/);
  });

  it("WHAT MATTERS NEXT 항목은 한 줄이고, 누르면 Trigger → First-order → Asset → Theme → Stock tier 와 EXPECTED / OBSERVED · What would confirm n/m 이 펼쳐진다", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={null} />);
    expect(screen.queryByTestId("ck-path")).toBeNull();
    const items = screen.getAllByTestId("ck-next-item");
    const withPath = cockpit.what_matters_next.findIndex((n) => n.path);
    fireEvent.click(items[withPath]!);
    const path = screen.getByTestId("ck-path");
    const stages = within(path).getAllByTestId("ck-path-stage").map((e) => e.getAttribute("data-key"));
    expect(stages).toEqual(["trigger", "first_order", "assets", "themes"]);
    expect(path.textContent).toMatch(/Expected/); expect(path.textContent).toMatch(/Observed/);
    expect(path.textContent).toMatch(/CONFIRMED|PARTIAL|UNCONFIRMED|CONTRADICTED|DATA MISSING/);
    expect(screen.getByTestId("ck-path-confirm").textContent).toMatch(/\d+ \/ \d+/);
    const p = cockpit.what_matters_next[withPath]!.path!;
    const shown = within(screen.getByTestId("ck-path-tiers")).getAllByTestId("ck-path-stock").length;
    expect(shown).toBeLessThanOrEqual(p.tiers.length * p.tier_max);
    expect(screen.getByTestId("ck-path-conclusion").textContent).not.toMatch(/확률/);
    // 다시 누르면 닫힌다
    fireEvent.click(items[withPath]!);
    expect(screen.queryByTestId("ck-path")).toBeNull();
  });

  it("radar 의 Related market issues 를 누르면 그 이슈가 열리고, 경로의 RADAR ● 종목은 radar 에도 있는 종목이다", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={null} />);
    const r = cockpit.radar.find((x) => x.related_issues.length)!;
    const box = screen.getAllByTestId("ck-radar-issues")[0]!;
    fireEvent.click(within(box).getAllByRole("button")[0]!);
    const path = screen.getByTestId("ck-path");
    const radarIds = new Set(cockpit.radar.map((x) => x.id));
    const marked = within(path).getAllByTestId("ck-path-stock").filter((e) => e.textContent?.includes("RADAR ●"));
    expect(marked.length).toBeGreaterThan(0);
    for (const m of marked) expect(cockpit.radar.some((x) => m.textContent?.includes(x.name) && radarIds.has(x.id))).toBe(true);
    void r;
  });
});

describe("CockpitView — 표현 층: 영어 상태값 + 한글 의미 (CROSS-ASSET · WHAT MATTERS NEXT)", () => {
  it("CROSS-ASSET 은 목적 설명 → 현재 판단 · n/m 의 뜻 → MARKET READ → RISK / MACRO / COMMODITY 그룹의 대표 지표 + 영어 상태 + 한글 의미 → KEY DIVERGENCE(현상 → 왜 중요 → 근거) → 색상 legend 순", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={null} />);
    const card = screen.getByTestId("ck-cross"); const ca = cockpit.cross_asset;
    expect(screen.getByTestId("ck-cross-purpose").textContent).toMatch(/다른 시장에서도 같은 방향/);
    expect(screen.getByTestId("ck-cross-view").textContent).toBe(ca.current_view);
    expect(screen.getByTestId("ck-cross-confirm-text").textContent).toBe(ca.confirm_text);
    expect(screen.getByTestId("ck-market-read").textContent).toContain(ca.market_read);
    const groups = screen.getAllByTestId("ck-ca-group").map((g) => g.getAttribute("data-group"));
    expect(groups).toEqual(["RISK", "MACRO", "COMMODITY"]);
    const rows = screen.getAllByTestId("ck-ca-row");
    expect(rows.length).toBe(ca.rows.length);
    for (const r of ca.rows) {
      const el = rows.find((x) => x.textContent?.includes(r.key))!;
      expect(el.textContent).toContain(r.instrument_label);   // 대표 지표
      expect(el.textContent).toContain(r.status);             // 영어 상태값 유지
      if (r.meaning) expect(el.textContent).toContain(r.meaning); // 한글 의미
    }
    // 순서: 영어가 먼저, 한글이 뒤
    const gold = rows.find((x) => x.textContent?.includes("GOLD"))!;
    expect(gold.textContent!.indexOf("DIVERGE")).toBeLessThan(gold.textContent!.indexOf("불일치"));
    const divs = screen.getAllByTestId("ck-divergence");
    expect(divs.length).toBeLessThanOrEqual(2);
    const d0 = ca.divergences[0]!; const t = divs[0]!.textContent!;
    expect(t).toContain(d0.phenomenon); expect(t).toContain("Why it matters"); expect(t).toContain("Reference");
    expect(t.indexOf(d0.phenomenon)).toBeLessThan(t.indexOf("Reference"));
    expect(card.textContent).toMatch(/일치 여부/);
    expect(card.textContent).not.toMatch(/확률/);
  });

  it("WHAT MATTERS NEXT 는 닫힌 상태에 목적 · 영어 상태 + 한글 · 1D/5D 기간 · 자동 해석 · Why it matters 만, 열면 SUMMARY → EXPECTED/OBSERVED → 단계별 한글 설명 → DIRECT 4 / SECONDARY 3 / TERTIARY 접기 → n / m conditions confirmed", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={null} />);
    expect(screen.getByTestId("ck-next-purpose").textContent).toMatch(/자산 → 산업 → 종목/);
    const items = screen.getAllByTestId("ck-next-item");
    const i = cockpit.what_matters_next.findIndex((n) => n.path); const n = cockpit.what_matters_next[i]!; const li = items[i]!;
    expect(li.textContent).toContain(n.status);
    expect(li.textContent).toContain(n.why_next);
    const hz = within(li).getByTestId("ck-next-horizons").textContent!;
    expect(hz).toMatch(/1D/); expect(hz).toMatch(/5D/); if (n.horizon_read) expect(hz).toContain(n.horizon_read);
    expect(screen.queryByTestId("ck-path")).toBeNull();
    fireEvent.click(li);
    const path = screen.getByTestId("ck-path"); const pt = path.textContent!;
    const sm = n.path!.summary!;
    expect(screen.getByTestId("ck-path-summary").textContent).toContain(`${sm.stages_confirmed} / ${sm.stages_total} stages confirmed`);
    // 순서: SUMMARY → EXPECTED/OBSERVED → TRANSMISSION PATH → STOCK IMPACT → WHAT WOULD CONFIRM
    const idx = (s: string) => pt.indexOf(s);
    expect(idx("Summary")).toBeLessThan(idx("Expected")); expect(idx("Expected")).toBeLessThan(idx("Transmission path")); expect(idx("Transmission path")).toBeLessThan(idx("Stock impact")); expect(idx("Stock impact")).toBeLessThan(idx("What would confirm?"));
    expect(pt).toContain("일반적으로 예상되는 시장 반응"); expect(pt).toContain("현재 실제 시장에서 나타나는 반응");
    const stages = within(path).getAllByTestId("ck-path-stage");
    expect(stages.map((s) => s.getAttribute("data-key"))).toEqual(["trigger", "first_order", "assets", "themes"]);
    for (let k = 0; k < 4; k++) { const st = [n.path!.trigger, n.path!.first_order, n.path!.assets, n.path!.themes][k]!; expect(stages[k]!.textContent).toContain(st.status); if (st.explain) expect(stages[k]!.textContent).toContain(st.explain); }
    // 종목: EXPECTED / OBSERVED / 영어 상태 + 한글, tier 기본 노출 수
    const tiers = screen.getByTestId("ck-path-tiers");
    const shown = within(tiers).getAllByTestId("ck-path-stock").length;
    const expected = n.path!.tiers.reduce((a, t) => a + Math.min(t.stocks.length, n.path!.tier_show[t.tier] ?? n.path!.tier_max), 0);
    expect(shown).toBe(expected);
    expect(tiers.textContent).toContain("DIRECT"); expect(tiers.textContent).toContain("1차 영향");
    const contra = within(tiers).getAllByTestId("ck-path-stock").find((e) => e.textContent?.includes("CONTRADICTED"));
    if (contra) expect(contra.textContent).toMatch(/오류가 아니라/);
    expect(screen.getByTestId("ck-path-confirm").textContent).toMatch(/\d+ \/ \d+ conditions confirmed/);
    expect(screen.getByTestId("ck-path-confirm").textContent).toMatch(/확률이 아니라 조건 수/);
  });
});

describe("CockpitView — DRIVER HEAT 의미 층 · MARKET LEADERSHIP intelligence", () => {
  it("DRIVER HEAT 행은 경제적 라벨(Credit Stress · 신용 스트레스)과 화살표 옆 현재 의미, 1D/5D 기간, 색/화살표 legend 를 보여준다", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={null} />);
    const rows = screen.getAllByTestId("ck-h-heat-row");
    expect(rows.length).toBe(5);
    const credit = rows.find((r) => r.getAttribute("data-key") === "Credit")!;
    expect(credit.textContent).toContain("Credit Stress"); expect(credit.textContent).toContain("신용 스트레스");
    const meaning = within(credit).getByTestId("ck-h-heat-meaning").textContent!;
    expect(meaning).toMatch(/확대|완화|중립/); expect(meaning).toMatch(/1D/); expect(meaning).toMatch(/5D/);
    const rates = rows.find((r) => r.getAttribute("data-key") === "Rates")!;
    expect(rates.textContent).toContain("Rate Pressure");
    const h = cockpit.history!.drivers.find((d) => d.key === "Rates")!;
    if (h.horizon_read) expect(rates.textContent).toContain(h.horizon_read);
    expect(screen.getByTestId("ck-h-heat-legend").textContent).toMatch(/COLOR.*ARROW/);
  });

  it("MARKET LEADERSHIP 은 LEADERSHIP READ 와 행마다 SYSTEM VIEW 한 줄을 보이고, 테마를 누르면 WHY → CONFIRMATION → SYSTEM VIEW(INTERNAL) → STREET VIEW(EXTERNAL, 있을 때만) → KEY STOCKS(RADAR ●) → WHAT TO WATCH 가 열린다", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={null} />);
    const l = cockpit.leadership;
    expect(screen.getByTestId("ck-lead-read").textContent).toContain(l.read);
    const rows = screen.getAllByTestId("ck-lead-row");
    expect(screen.getAllByTestId("ck-lead-system-view").length).toBe(rows.length);
    expect(screen.queryByTestId("ck-lead-detail")).toBeNull();
    const withStreet = [...l.leaders, ...l.laggards].find((r) => r.detail && r.detail.street.length)!;
    const row = rows.find((r) => r.getAttribute("data-key") === withStreet.key)!;
    fireEvent.click(row);
    const d = screen.getByTestId("ck-lead-detail"); const t = d.textContent!;
    const idx = (s: string) => t.indexOf(s);
    expect(idx("Why leading?")).toBeLessThan(idx("System view")); expect(idx("System view")).toBeLessThan(idx("Market confirmation"));
    expect(idx("Market confirmation")).toBeLessThan(idx("Street view")); expect(idx("Street view")).toBeLessThan(idx("Key stocks")); expect(idx("Key stocks")).toBeLessThan(idx("What to watch"));
    // full-width panel: 카드 안이 아니라 그리드의 형제(leaddet 행) 로 열리고, 맨 위에 Summary 가 온다
    const wrap = screen.getByTestId("ck-lead-detail-wrap");
    expect(screen.getByTestId("ck-leadership").contains(wrap)).toBe(false);
    expect(wrap.style.gridArea).toBe("leaddet");
    expect(screen.getByTestId("cockpit").className).toContain("ck-ldopen");
    const sum = screen.getByTestId("ck-ld-summary").textContent!;
    expect(sum).toContain(withStreet.detail!.quality); expect(sum).toContain(withStreet.detail!.driver); expect(sum).toContain(withStreet.detail!.system_view);
    expect(wrap.textContent!.indexOf(withStreet.detail!.system_view)).toBeLessThan(wrap.textContent!.indexOf("Why leading?"));
    expect(within(row).getByTestId("ck-lead-active").textContent).toBe("ACTIVE");
    expect(t).toContain("INTERNAL"); expect(t).toContain("EXTERNAL");
    expect(screen.getByTestId("ck-ld-street").textContent).toContain(withStreet.detail!.street[0]!.institution);
    expect(within(screen.getByTestId("ck-ld-conf")).getAllByText(/CONFIRMED|PARTIAL|UNCONFIRMED|CONTRADICTED|DATA MISSING/).length).toBeGreaterThanOrEqual(3);
    expect(t).toContain(withStreet.detail!.quality); expect(t).toContain(withStreet.detail!.quality_ko);
    expect(screen.getByTestId("ck-ld-watch").querySelectorAll("li").length).toBeLessThanOrEqual(3);
    const stocks = screen.getAllByTestId("ck-ld-stock");
    expect(stocks.length).toBeLessThanOrEqual(5);
    const radarNames = new Set(cockpit.radar.map((r) => r.name));
    for (const s of stocks) if (s.textContent?.includes("RADAR ●")) expect([...radarNames].some((n) => s.textContent!.includes(n))).toBe(true);
    const noStreet = [...l.leaders, ...l.laggards].find((r) => r.detail && !r.detail.street.length);
    if (noStreet) { fireEvent.click(rows.find((r) => r.getAttribute("data-key") === noStreet.key)!); expect(screen.queryByTestId("ck-ld-street")).toBeNull(); }
    // one selected theme at a time: 다른 테마를 누르면 패널이 교체되고, 다시 누르거나 닫기를 누르면 닫힌다
    const others = [...l.leaders, ...l.laggards].filter((r) => r.detail && r.key !== withStreet.key);
    if (others.length) {
      fireEvent.click(rows.find((r) => r.getAttribute("data-key") === others[0]!.key)!);
      expect(screen.getAllByTestId("ck-lead-detail-wrap").length).toBe(1);
      expect(screen.getByTestId("ck-lead-detail-wrap").getAttribute("data-key")).toBe(others[0]!.key);
      expect(screen.getAllByTestId("ck-lead-active").length).toBe(1);
    }
    fireEvent.click(screen.getByRole("button", { name: /Leadership detail 닫기/ }));
    expect(screen.queryByTestId("ck-lead-detail-wrap")).toBeNull();
    expect(screen.getByTestId("cockpit").className).not.toContain("ck-ldopen");
  });

  it("STREET VIEW 는 기관 · 날짜 · 한글 요약 · View source 를 기본으로 보이고 긴 영어 원문은 접혀 있다가 눌러야 펼쳐진다", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={null} />);
    const l = cockpit.leadership;
    const withLong = [...l.leaders, ...l.laggards].find((r) => r.detail && r.detail.street.some((v) => (v.quote || "").length > 90));
    if (!withLong) return;
    fireEvent.click(screen.getAllByTestId("ck-lead-row").find((r) => r.getAttribute("data-key") === withLong.key)!);
    const items = screen.getAllByTestId("ck-ld-street-item");
    expect(items.length).toBe(withLong.detail!.street.length);
    const v = withLong.detail!.street.find((x) => (x.quote || "").length > 90)!;
    const item = items[withLong.detail!.street.indexOf(v)]!;
    expect(item.textContent).toContain(v.summary); expect(item.textContent).toContain("View source");
    expect(item.querySelector("a")!.getAttribute("href")).toBe(v.source_url);
    const q = within(item).getByTestId("ck-ld-street-quote");
    expect(q.className).toContain("clamp");
    fireEvent.click(q);
    expect(q.className).not.toContain("clamp");
  });
});

describe("CockpitView — TRANSMISSION read · WATCHLIST checkpoints", () => {
  it("전파 카드마다 n / m confirmed 옆에 STRONG/PARTIAL/LIMITED/UNCONFIRMED + 한글, 그리고 TRANSMISSION READ 1~2문장이 있다", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={null} />);
    const chains = screen.getAllByTestId("ck-chain");
    expect(chains.length).toBe(cockpit.transmission.length);
    for (const ch of chains) {
      expect(within(ch).getByTestId("ck-chain-strength").textContent).toMatch(/\d+ \/ \d+ confirmed.*(STRONG|PARTIAL|LIMITED|UNCONFIRMED).*(전파|미확인)/);
      expect(within(ch).getByTestId("ck-chain-read").textContent).toMatch(/Transmission read/);
    }
  });

  it("WATCHLIST 는 목적 설명과 종목마다 테마 · WHY WATCH · KEY DRIVER(≤3) · TRIGGER · 태그, TRANSMISSION ● / RELATED ISSUE 링크가 전파 카드·이슈로 이어지고, 점수 숫자는 보이지 않는다", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} analystViews={null} />);
    expect(screen.getByTestId("ck-watch-purpose").textContent).toMatch(/다음에 무엇이 나타나면/);
    const rows = screen.getAllByTestId("ck-watch-row");
    expect(rows.length).toBe(cockpit.watchlist.length);
    for (let i = 0; i < rows.length; i++) {
      const w = cockpit.watchlist[i]!; const r = rows[i]!;
      expect(within(r).getByTestId("ck-watch-why").textContent).toContain(w.why);
      expect(within(r).getByTestId("ck-watch-trigger").textContent).toContain(w.trigger);
      expect(within(r).getByTestId("ck-watch-drivers").textContent!.split(" · ").length).toBeLessThanOrEqual(3);
      expect(r.textContent).not.toMatch(/\d+점/);
    }
    const withChain = cockpit.watchlist.find((w) => w.transmission.length)!;
    const row = rows[cockpit.watchlist.indexOf(withChain)]!;
    const btn = within(row).getAllByRole("button").find((b) => b.textContent?.includes("TRANSMISSION ●"))!;
    fireEvent.click(btn);
    expect(document.getElementById(`ck-tr-${withChain.transmission[0]!.key}`)!.className).toContain("focus");
    const withIssue = cockpit.watchlist.find((w) => w.issues.length);
    if (withIssue) {
      const r2 = rows[cockpit.watchlist.indexOf(withIssue)]!;
      fireEvent.click(within(r2).getAllByRole("button").find((b) => b.textContent?.includes("RELATED ISSUE"))!);
      expect(screen.getByTestId("ck-path")).toBeInTheDocument();
    }
  });
});

describe("MARKET TONE SNAPSHOT — HISTORY 와 TODAY'S DRIVERS 사이, 실시간 탭의 온도계 화면 그대로", () => {
  it("순서가 MARKET NOW → REGIME HISTORY → MARKET TONE SNAPSHOT → TODAY'S MARKET DRIVERS 이고, 카드 안은 실시간 탭의 SentimentGauge(점수·밴드·눈금·가격/뉴스·재료 스트립·템플릿 문장) 그대로다", () => {
    const { container } = render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} />);
    const titles = Array.from(container.querySelectorAll(".panel-title")).map((e) => e.textContent);
    expect(titles.indexOf("Market Tone Snapshot")).toBe(titles.indexOf("Market Regime History · 1M") + 1);
    expect(titles.indexOf("Market Tone Snapshot")).toBe(titles.findIndex((t) => /Today/i.test(t ?? "")) - 1);
    expect(container.querySelector(".ck")!.className).toContain("ck-tone");
    const sec = screen.getByTestId("ck-tone");
    const gauge = sec.querySelector(".gauge")!;
    expect(gauge).not.toBeNull();
    const t = snapshot.thermometer!;
    expect(gauge.querySelector(".gauge-value")!.textContent).toBe(`${t.composite! > 0 ? "+" : ""}${t.composite!.toFixed(0)}`);
    expect(gauge.querySelector(".gauge-band")!.textContent).toBe(t.band_label);
    expect(gauge.textContent).toContain("△ 가격"); expect(gauge.textContent).toContain("▽ 뉴스");
    for (const c of t.components) expect(gauge.textContent).toContain(c.label);
    expect(gauge.querySelector(".gauge-note")!.textContent).toBe(t.note);
    expect(sec.textContent).toContain("실시간 탭과 같은 온도계");
  });

  it("온도계가 없으면 카드와 ck-tone 그리드 클래스가 없다", () => {
    const { container } = render(<CockpitView cockpit={cockpit} snapshot={{ ...snapshot, thermometer: null }} history={history} />);
    expect(screen.queryByTestId("ck-tone")).toBeNull(); expect(container.querySelector(".ck")!.className).not.toContain("ck-tone");
  });
});
