/** 공식 regime Exit / Entry 표시 (exit_entry_v2, 2026-11-12 요청) — 공식 · 후보 · support · 이탈 · 진입 · raw 를 섞지 않는다. legacy 저장본은 예전 표시 그대로. */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import hist from "../__fixtures__/state_history.json";
import ckFx from "../__fixtures__/cockpit.json";
import type { Cockpit, CkRegimeState, IntelligenceSnapshot, MarketStateHistory } from "../api/types";
import { CockpitView } from "../components/CockpitView";
import { entryText, exitText } from "../components/RegimeStatePanel";

const snapshot = snap as unknown as IntelligenceSnapshot;
const history = hist as unknown as MarketStateHistory;
const cockpit = ckFx as unknown as Cockpit;

const base: CkRegimeState = {
  logic_version: "exit_entry_v2", snapshot_date: "2026-11-10", date: "2026-11-09", official: "liquidity_stress", official_label: "Liquidity Stress / Risk-Off",
  previous_official: "liquidity_stress", previous_official_label: "Liquidity Stress / Risk-Off", candidate: "risk_on", candidate_label: "Risk-On", candidate_state: "RISK_ON",
  raw_signal: "RISK_ON", raw_signal_label: "Risk-On", raw_persistence_days: 1, support: "WEAKENING", support_reasons: ["핵심 조건: Liquidity ≤ -1.0 미충족(지금 +1.30)"],
  equity: { us: "CONTRADICTED", kr: "CONFIRMED", global: "MIXED" }, exit_streak: 1, exit_required: 2, exit_confirmed: false, exited_regime: null, exited_label: null,
  entry_regime: "risk_on", entry_label: "Risk-On", entry_streak: 1, entry_required: 2, entry_confirmed: false, changed: false, change_kind: null, counted: true,
};

function withState(st: CkRegimeState, label: string, labelText: string, hKey: string, hLabel: string): Cockpit {
  const h = cockpit.history ? { ...cockpit.history, state: st, logic_version: "exit_entry_v2", current_regime: hKey, current_label: hLabel, previous_label: "Liquidity Stress / Risk-Off", transition_status: st.changed ? "CHANGED" : "TRANSITION_WATCH" } : null;
  return { ...cockpit, history: h, market_now: { ...cockpit.market_now, state: st, label, label_text: labelText, transition_status: st.changed ? "CHANGED" : "TRANSITION_WATCH" } };
}

describe("Exit / Entry 상태 — MARKET NOW", () => {
  it("예시 1: 기존 레짐 유지 중 — 공식 · 후보 · support · EXIT 1/2 · ENTRY Risk-On 1/2 가 따로 보인다", () => {
    render(<CockpitView cockpit={withState(base, "LIQUIDITY_STRESS", "LIQUIDITY STRESS", "liquidity_stress", "Liquidity Stress / Risk-Off")} snapshot={snapshot} history={history} />);
    const box = screen.getByTestId("ck-now-state");
    expect(screen.getByTestId("ck-now-official-k").textContent).toMatch(/Official regime/i);
    expect(screen.getByTestId("ck-now-label").textContent).toBe("LIQUIDITY STRESS");
    expect(within(box).getByTestId("ck-now-candidate").textContent).toContain("RISK-ON");
    expect(within(box).getByTestId("ck-now-support").textContent).toContain("WEAKENING");
    expect(within(box).getByTestId("ck-now-exit").textContent).toContain("1 / 2 DAYS");
    expect(within(box).getByTestId("ck-now-entry").textContent).toMatch(/RISK-ON.*1 \/ 2 DAYS/);
    expect(within(box).getByTestId("ck-now-rawsig").textContent).toContain("RISK-ON");
    expect(screen.queryByTestId("ck-rs-pending")).toBeNull(); // 진입 후보는 상태 표가 보인다 — 선택 블록에서 겹쳐 쓰지 않는다
  });

  it("예시 2: 기존 레짐 해제 · 새 레짐 미확정 — 공식 NEUTRAL / MIXED, 직전 공식, EXIT CONFIRMED", () => {
    const st: CkRegimeState = { ...base, snapshot_date: "2026-11-11", date: "2026-11-10", official: "neutral", official_label: "Neutral / Mixed", candidate: "neutral", candidate_label: "Neutral / Mixed",
      raw_signal: "NEUTRAL", support: "BROKEN", exit_streak: 2, exit_confirmed: true, exited_regime: "liquidity_stress", exited_label: "Liquidity Stress / Risk-Off",
      entry_regime: null, entry_label: null, entry_streak: 0, changed: true, change_kind: "exit" };
    render(<CockpitView cockpit={withState(st, "NEUTRAL", "NEUTRAL / MIXED", "neutral", "Neutral / Mixed")} snapshot={snapshot} history={history} />);
    expect(screen.getByTestId("ck-now-label").textContent).toBe("NEUTRAL / MIXED");
    expect(screen.getByTestId("ck-now-exit").textContent).toContain("LIQUIDITY STRESS EXIT CONFIRMED");
  });

  it("다음 날: 공식 Neutral 에 Risk-On 진입 1/2 — 직전 공식과 해제 기록이 남는다", () => {
    const st: CkRegimeState = { ...base, snapshot_date: "2026-11-12", date: "2026-11-11", official: "neutral", official_label: "Neutral / Mixed", previous_official: "neutral",
      support: "NA", exit_streak: 0, released_label: "Liquidity Stress / Risk-Off", released_on: "2026-11-10" };
    render(<CockpitView cockpit={withState(st, "NEUTRAL", "NEUTRAL / MIXED", "neutral", "Neutral / Mixed")} snapshot={snapshot} history={history} />);
    expect(screen.getByTestId("ck-now-prev-official").textContent).toContain("LIQUIDITY STRESS");
    expect(screen.getByTestId("ck-now-exit").textContent).toMatch(/LIQUIDITY STRESS EXIT CONFIRMED · 11\/10/);
    expect(screen.getByTestId("ck-now-entry").textContent).toMatch(/RISK-ON.*1 \/ 2 DAYS/);
    expect(screen.queryByTestId("ck-now-support")).toBeNull();
  });

  it("legacy 저장본(state 없음)은 예전 RAW SIGNAL 줄 그대로", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} />);
    expect(screen.queryByTestId("ck-now-state")).toBeNull();
    expect(screen.getByTestId("ck-now-raw").textContent).toMatch(/RAW SIGNAL/i);
  });
});

describe("Exit / Entry 상태 — MARKET REGIME HISTORY 우측 요약", () => {
  it("CURRENT 는 공식 기준, PENDING · ENTRY · EXIT · RAW · TRANSITION STATUS 는 따로", () => {
    const st: CkRegimeState = { ...base, official: "neutral", official_label: "Neutral / Mixed", support: "NA", exit_streak: 0, released_label: "Liquidity Stress / Risk-Off", released_on: "2026-11-10" };
    const c = withState(st, "NEUTRAL", "NEUTRAL / MIXED", "neutral", "Neutral / Mixed");
    if (!c.history) return;
    render(<CockpitView cockpit={c} snapshot={snapshot} history={history} />);
    const ctx = screen.getByTestId("ck-h-ctx");
    expect(within(ctx).getByText(/Current official/i)).toBeTruthy();
    expect(within(ctx).getByTestId("ck-h-current").textContent).toBe("Neutral / Mixed");
    expect(within(ctx).getByTestId("ck-h-pending").textContent).toContain("RISK-ON");
    expect(within(ctx).getByTestId("ck-h-entry").textContent).toContain("1 / 2 DAYS");
    expect(within(ctx).getByTestId("ck-h-tstatus").textContent).toContain("WATCH");
    expect(within(ctx).queryByTestId("ck-h-raw")).toBeNull();
  });
});

describe("exit / entry 문구", () => {
  it("공식 확정 · 진행 · 없음", () => {
    expect(exitText({ ...base, exit_streak: 0 }).text).toBe("0 / 2 DAYS");
    expect(entryText({ ...base, changed: true, change_kind: "entry", official: "risk_on" }).text).toBe("CONFIRMED");
    expect(entryText({ ...base, entry_regime: null, candidate: "liquidity_stress" }).text).toMatch(/진입 대기 후보 없음/);
  });
});
