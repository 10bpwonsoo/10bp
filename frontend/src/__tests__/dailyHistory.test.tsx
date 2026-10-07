/**
 * Daily snapshot history (2026-10-07) — History 는 각 날짜의 판단을 한 번 저장한 뒤 고정한 기록이다.
 * 화면은 저장 sequence 를 그대로 그리고, 날짜마다 출처(Recorded / Backfilled / Live)·계산 시각·모델 버전을 툴팁·상세에서 보인다.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import dhFx from "../__fixtures__/daily_history.json";
import hist from "../__fixtures__/state_history.json";
import ckFx from "../__fixtures__/cockpit.json";
import aiFx from "../__fixtures__/ai_regime.json";
import snap from "../__fixtures__/snapshot.json";
import ratesFx from "../__fixtures__/rates_regime.json";
import checksFx from "../__fixtures__/scenario_check.json";
import type { AiRegime, CkRegimeHistory, DailyHistory, IntelligenceSnapshot, MarketStateHistory, RatesRegime, ScenarioCheck } from "../api/types";
import { DailyHistoryStrip, sourceLine } from "../components/DailyHistoryStrip";
import { StateHistoryStrip } from "../components/StateHistoryStrip";
import { RegimeHistoryCard } from "../components/RegimeHistoryCard";
import { AiSentimentSection } from "../components/AiSentimentSection";

const fx = dhFx as unknown as Record<string, DailyHistory>;
const history = hist as unknown as MarketStateHistory;
const regime = aiFx as unknown as AiRegime;

vi.mock("../api/useDailyHistory", () => ({
  useDailyHistory: (tab: string) => ({ history: (dhFx as unknown as Record<string, DailyHistory>)[tab] ?? null, error: null }),
}));

describe("DailyHistoryStrip — 저장 snapshot sequence", () => {
  it("모든 탭의 fixture 가 저장 sequence 이고(과거는 RECORDED/BACKFILLED·locked, 오늘만 LIVE), 각주와 R/B 집계가 맞는다", () => {
    for (const tab of ["market_regime", "ai_sentiment", "ai_regime", "rates_regime", "oil_regime", "memory_cycle"] as const) {
      const h = fx[tab]!;
      expect(h.tab_id).toBe(tab);
      expect(h.footnote).toBe("각 거래일 최종 snapshot 기준 · 저장 후 고정");
      const past = h.points.slice(0, -1);
      expect(past.every((p) => (p.source === "RECORDED" || p.source === "BACKFILLED") && p.locked)).toBe(true);
      expect(h.points[h.points.length - 1]!.source).toBe("LIVE");
      expect(h.recorded_days).toBe(h.points.filter((p) => p.source === "RECORDED").length);
      expect(h.backfilled_days).toBe(h.points.filter((p) => p.source === "BACKFILLED").length);
      expect(h.points.every((p) => p.model_version && p.logic_version && p.calculated_at)).toBe(true);
      // 파생값은 sequence 에서: streak · changes · share
      const states = h.points.map((p) => p.state);
      let streak = 1; for (let i = states.length - 1; i > 0 && states[i] === states[i - 1]; i--) streak++;
      expect(h.current_streak).toBe(streak);
      expect(h.changes).toBe(states.filter((s, i) => i > 0 && s !== states[i - 1]).length);
      expect(h.current_state).toBe(states[states.length - 1]);
      expect(h.share.reduce((a, s) => a + s.days, 0)).toBe(h.points.length);
    }
  });

  it("날짜 셀은 저장 state 색이고, 툴팁·상세에 Recorded/Backfilled·계산 시각·모델 버전이 있다", () => {
    const h = fx.market_regime!;
    render(<DailyHistoryStrip history={h} />);
    const cells = screen.getAllByTestId("dh-cell");
    expect(cells.length).toBe(h.points.length);
    cells.forEach((c, i) => {
      expect(c.getAttribute("data-state")).toBe(h.points[i]!.state);
      expect(c.getAttribute("data-source")).toBe(h.points[i]!.source);
      expect(c.getAttribute("title")).toContain(h.points[i]!.source === "BACKFILLED" ? "Backfilled · calculated" : h.points[i]!.source === "RECORDED" ? "Recorded" : "Live");
    });
    expect(screen.getByTestId("dh-footnote").textContent).toBe(h.footnote);
    expect(screen.getByTestId("dh-counts").textContent).toContain(`R ${h.recorded_days} · B ${h.backfilled_days}`);
    expect(screen.getByTestId("dh-current").textContent).toBe(h.current_label);
    const bf = h.points.findIndex((p) => p.source === "BACKFILLED");
    fireEvent.click(cells[bf]!);
    const det = screen.getByTestId("dh-detail");
    expect(within(det).getByTestId("dh-source").textContent).toMatch(/^Backfilled · calculated \d\d\/\d\d · market_regime_v/);
    expect(det.textContent).toContain(h.points[bf]!.label);
    expect(screen.getByTestId("dh-spark").querySelectorAll("circle").length).toBe(h.points.filter((p) => p.score !== null).length);
  });

  it("sourceLine 은 BACKFILLED 에만 계산일을 붙이고 RECORDED 는 Recorded 와 버전만", () => {
    expect(sourceLine("BACKFILLED", "2026-10-07T05:00:00Z", "m_v4", "rules_v6", true)).toBe("Backfilled · calculated 10/07 · m_v4 · rules_v6 · locked");
    expect(sourceLine("RECORDED", "2026-10-06T07:40:00Z", "m_v4", "", true)).toBe("Recorded · m_v4 · locked");
    expect(sourceLine("LIVE", null, "m_v4", "rules_v6")).toBe("Live · m_v4 · rules_v6 · 확정 전");
  });
});

describe("기존 History 화면도 저장 sequence 를 쓴다", () => {
  it("실시간 Market State 띠: history_mode=stored, 각주, 날짜 툴팁에 출처", () => {
    expect(history.history_mode).toBe("stored");
    render(<StateHistoryStrip history={history} primary="label" />);
    const foot = screen.getByTestId("sh-footnote");
    expect(foot.textContent).toContain("각 거래일 최종 snapshot 기준 · 저장 후 고정");
    expect(foot.getAttribute("data-mode")).toBe("stored");
    const titles = Array.from(document.querySelectorAll("[title]")).map((e) => e.getAttribute("title") ?? "");
    expect(titles.some((t) => /Backfilled · calculated/.test(t))).toBe(true);
    expect(titles.some((t) => /Recorded/.test(t))).toBe(true);
    expect(history.points.slice(0, -1).every((p) => p.locked)).toBe(true);
  });

  it("실시간2 MARKET REGIME HISTORY: 날짜 툴팁·상세에 출처, 카드 각주", () => {
    const base = (ckFx as unknown as { history: CkRegimeHistory }).history;
    const h: CkRegimeHistory = { ...base, history_mode: "stored", footnote: "각 거래일 최종 snapshot 기준 · 저장 후 고정", recorded_days: 2, backfilled_days: base.days.length - 3,
      days: base.days.map((d, i) => ({ ...d, source: i === base.days.length - 1 ? "LIVE" : i % 5 === 0 ? "RECORDED" : "BACKFILLED", calculated_at: "2026-10-07T05:00:00Z", model_version: "market_regime_v0.1.0", logic_version: "rules_abc", locked: i !== base.days.length - 1 })) };
    render(<RegimeHistoryCard h={h} />);
    expect(screen.getByTestId("ck-h-footnote").textContent).toContain("저장 후 고정");
    const cells = screen.getAllByTestId("ck-h-cell");
    fireEvent.mouseEnter(cells[1]!);
    expect(screen.getByTestId("ck-h-tip-source").textContent).toMatch(/Backfilled · calculated 10\/07/);
    fireEvent.click(cells[0]!);
    expect(screen.getByTestId("ck-h-detail-source").getAttribute("data-source")).toBe("RECORDED");
  });

  it("AI SENTIMENT 1M: 점마다 출처(툴팁), 각주, 저장 sequence 의 1W 변화", () => {
    const s = regime.sentiment!;
    expect(s.history.history_mode).toBe("stored");
    render(<AiSentimentSection regime={regime} />);
    const pts = screen.getAllByTestId("ai-gf-point");
    expect(pts.length).toBe(s.history.points.filter((p) => p.index !== null).length - 1);
    expect(pts.some((p) => p.getAttribute("data-source") === "BACKFILLED")).toBe(true);
    expect(pts[0]!.querySelector("title")!.textContent).toMatch(/Backfilled · calculated|Recorded/);
    expect(screen.getByTestId("ai-gf-footnote").textContent).toContain("저장 후 고정");
    const idx = s.history.points.map((p) => p.index);
    expect(s.history.change_1w).toBe(Math.round((idx[idx.length - 1]! - idx[idx.length - 6]!) * 10) / 10);
  });

  it("물가 탭에 Inflation & Rates State History 패널이 저장 sequence 로 붙는다", async () => {
    const { RatesRegimeView } = await import("../components/RatesRegimeView");
    const check: ScenarioCheck = { ...(checksFx as unknown as ScenarioCheck[]).find((c) => c.name === "inflation_shock")!, focus: "rates_regime" };
    render(<RatesRegimeView regime={ratesFx as unknown as RatesRegime} snapshot={snap as unknown as IntelligenceSnapshot} check={check} />);
    const panel = screen.getByTestId("history-panel-rates_regime");
    expect(within(panel).getByTestId("daily-history").getAttribute("data-tab")).toBe("rates_regime");
    expect(within(panel).getAllByTestId("dh-cell").length).toBe(fx.rates_regime!.points.length);
    expect(panel.textContent).toContain("저장 후 고정");
  });
});
