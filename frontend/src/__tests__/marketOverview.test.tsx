/** MARKET OVERVIEW · 시장 종합 (2026-11-12) — 13개 섹션 순서, 판단(LLM) 먼저 · 숫자는 기존 섹션, 상세 탭 연결, 종합이 없는 날짜도 숫자 칸은 그 날짜 데이터로. */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import ckFx from "../__fixtures__/cockpit.json";
import aiFx from "../__fixtures__/ai_regime.json";
import moFx from "../__fixtures__/market_overview.json";
import neFx from "../__fixtures__/neutral_equity_1113.json";
import type { AiRegime, CkRegimeState, Cockpit, MarketOverview, RsSignal } from "../api/types";
import { MarketOverviewView, eqTerms } from "../components/MarketOverviewView";

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
    expect(within(screen.getByTestId("mo-labels")).getByText("ELEVATED")).toBeTruthy();
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

  it("REGIME & MARKET STATE — 공식 → 후보 + 진행일, 전환 상태 한 줄, 주식 확인 한 줄(8칸 블록 없음)", () => {
    const st: CkRegimeState = {
      logic_version: "exit_entry_v2", snapshot_date: "2026-11-13", date: "2026-11-12", official: "neutral", official_label: "Neutral / Mixed", previous_official: "neutral", previous_official_label: "Neutral / Mixed",
      candidate: "policy", candidate_label: "Policy Driven", candidate_state: "POLICY_DRIVEN", raw_signal: "POLICY_DRIVEN", raw_signal_label: "Policy Driven", raw_persistence_days: 1, support: "NA", support_reasons: [],
      equity: { us: "PARTIAL", kr: "PARTIAL", global: "PARTIAL" }, exit_streak: 0, exit_required: 2, exit_confirmed: false, exited_regime: null, exited_label: null,
      entry_regime: "policy", entry_label: "Policy Driven", entry_streak: 1, entry_required: 2, entry_confirmed: false, changed: false, change_kind: null, counted: true,
    };
    const sel = cockpit.market_now.selection ? { ...cockpit.market_now.selection, us_equity_confirmation: "PARTIAL", korea_equity_confirmation: "PARTIAL", global_equity_confirmation: "CONTRADICTED" } : null;
    const c = { ...cockpit, market_now: { ...cockpit.market_now, state: st, selection: sel } } as Cockpit;
    render(<MarketOverviewView cockpit={c} overview={mo} rates={null} oil={null} ai={ai} semi={null} />);
    const box = screen.getByTestId("mo-regime");
    expect(screen.getByTestId("mo-state-summary").textContent).toBe(mo.view!.state_summary);
    expect(screen.getByTestId("mo-regime-flow").textContent).toMatch(/NEUTRAL \/ MIXED.*→.*POLICY/);
    expect(screen.getByTestId("mo-regime-transition").textContent).toMatch(/TRANSITION WATCH.*1 \/ 2 DAYS/);
    expect(screen.getByTestId("mo-regime-days").textContent).toBe("1 / 2 DAYS");
    expect(within(box).getAllByText(/1 \/ 2 DAYS/)).toHaveLength(1); // 진행일은 한 번만
    expect(within(box).queryByText("CURRENT CANDIDATE")).toBeNull(); // 8칸 블록 제거
    expect(within(box).queryByText("STATUS")).toBeNull();
    if (sel) {
      const eq = screen.getByTestId("mo-regime-equity").textContent ?? "";
      expect(eq).toMatch(/US.*△ 부분 확인.*KOREA.*△ 부분 확인.*GLOBAL.*✕ 반대/);
      expect(screen.getByTestId("mo-regime-conf").textContent).toBe(`CONF ${sel.regime_confidence}`);
    }
    const order = ["mo-regime-state", "mo-regime-strip", "mo-regime-read"].map((id) => box.querySelector(`[data-testid='${id}']`));
    expect(order.every(Boolean)).toBe(true);
    expect(order[0]!.compareDocumentPosition(order[1]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(order[1]!.compareDocumentPosition(order[2]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("후보가 없으면 OFFICIAL 만, 화살표 없음", () => {
    const st = { logic_version: "exit_entry_v2", official: "neutral", official_label: "Neutral / Mixed", candidate: "neutral", candidate_label: "Neutral / Mixed", entry_regime: null, entry_streak: 0, entry_required: 2,
      exit_streak: 0, exit_required: 2, changed: false, change_kind: null, previous_official: "neutral", exited_regime: null } as unknown as CkRegimeState;
    render(<MarketOverviewView cockpit={{ ...cockpit, market_now: { ...cockpit.market_now, state: st } } as Cockpit} overview={mo} rates={null} oil={null} ai={ai} semi={null} />);
    expect(screen.getByTestId("mo-regime-flow").textContent).not.toContain("→");
    expect(screen.queryByTestId("mo-regime-days")).toBeNull();
    expect(screen.getByTestId("mo-regime-state").getAttribute("data-status")).toBe("STABLE");
  });

});

describe("EQUITY MARKET — 해석 먼저, 미국 vs 한국 같은 형식", () => {
  const ne = neFx as unknown as { us: RsSignal[]; kr: RsSignal[] };
  const mk = (s: RsSignal[]) => ({ status: "PARTIAL", score: 0, available: 6, total: 7, coverage: 0.8, signals: s });
  const sel = { ...(cockpit.market_now.selection ?? {}), us_equity_confirmation: "PARTIAL", korea_equity_confirmation: "PARTIAL", global_equity_confirmation: "PARTIAL",
    neutral_equity: { us: mk(ne.us), kr: mk(ne.kr), global: mk([]) } };
  const c = { ...cockpit, market_now: { ...cockpit.market_now, selection: sel } } as unknown as Cockpit;

  it("지수 값 → 시장 성격 단어(백엔드 equity_terms 와 같은 문턱)", () => {
    const us = eqTerms(ne.us, "us"); const kr = eqTerms(ne.kr, "kr");
    expect([us.trend, us.breadth, us.style[0]]).toEqual(["POSITIVE", "UNAVAILABLE", "LARGE > SMALL"]);
    expect(us.trendSub).toBe("S&P 500 ↑ · Nasdaq 100 ↑ · Russell 2000 →");
    expect([kr.trend, kr.breadth]).toEqual(["NEUTRAL", "WEAK"]);
    expect(kr.breadthSub).toBe("상승 참여율 31% · 대표 36종목 기준");
  });

  it("GLOBAL READ → US | KOREA(headline · 작은 status · why · 4개 핵심) → US ↔ KOREA, 지수 목록 없음", () => {
    const { container } = render(<MarketOverviewView cockpit={c} overview={mo} rates={null} oil={null} ai={ai} semi={null} />);
    const box = screen.getByTestId("mo-equity"); const ev = mo.view!.equity_view;
    expect(screen.getByTestId("mo-eq-global").textContent).toContain(ev.global_read!);
    for (const m of ["us", "kr"] as const) {
      const side = (m === "us" ? ev.us : ev.korea) as { headline: string; why: string; leadership: string[] };
      expect(screen.getByTestId(`mo-eq-${m}-headline`).textContent).toBe(side.headline);
      expect(screen.getByTestId(`mo-eq-${m}-status`).textContent).toBe("PARTIAL");
      expect(screen.getByTestId(`mo-eq-${m}-why`).textContent).toContain(side.why);
      expect(screen.getByTestId(`mo-eq-${m}-lead`).textContent).toContain(side.leadership.join(" / "));
    }
    expect(screen.getByTestId("mo-eq-us-breadth").className).toContain("muted");
    expect(screen.getByTestId("mo-eq-us-breadth").textContent).toMatch(/Unavailable/);
    expect(screen.getByTestId("mo-eq-kr-breadth").textContent).toMatch(/WEAK.*상승 참여율 31%/);
    expect(box.textContent).not.toMatch(/EXCLUDED/);
    expect(box.textContent).not.toMatch(/한국 대표 종목 상승 비율/);
    expect(container.querySelectorAll("[data-testid='mo-equity'] table")).toHaveLength(0);
    const ids = ["mo-eq-global", "mo-eq-us", "mo-eq-kr", "mo-divergence"].map((id) => box.querySelector(`[data-testid='${id}']`)!);
    for (let i = 1; i < ids.length; i++) expect(ids[i - 1]!.compareDocumentPosition(ids[i]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByTestId("mo-divergence").textContent).toMatch(/US ↔ KOREA.*US > KOREA/);
  });

  it("예전 저장본(us · korea 가 한 줄 문자열) — 그 문장을 그대로, GLOBAL READ 는 '없음'", () => {
    const old = { ...mo, view: { ...mo.view!, equity_view: { us: "미국 한 줄", korea: "한국 한 줄", divergence_label: "MIXED", divergence: "차이 한 줄" } } } as MarketOverview;
    render(<MarketOverviewView cockpit={c} overview={old} rates={null} oil={null} ai={ai} semi={null} />);
    expect(screen.getByTestId("mo-eq-global").textContent).toMatch(/종합 코멘트 없음/);
    expect(screen.getByTestId("mo-eq-us-headline").textContent).toBe("미국 한 줄");
    expect(screen.queryByTestId("mo-eq-us-why")).toBeNull();
    expect(screen.getByTestId("mo-eq-us-lead").textContent).toBe("LEADERSHIP–");
    expect(screen.getByTestId("mo-eq-us-trend").textContent).toMatch(/POSITIVE/);
  });
});
