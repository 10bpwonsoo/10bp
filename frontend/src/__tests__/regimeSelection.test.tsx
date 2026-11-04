/** MARKET NOW · REGIME v2 블록 — 공식 regime 과 오늘 선택이 다르면 PENDING, 주식 확인 US/KOREA/GLOBAL, coverage 와 confidence 를 따로, 데이터 없음은 EXCLUDED. */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import hist from "../__fixtures__/state_history.json";
import ckFx from "../__fixtures__/cockpit.json";
import type { Cockpit, IntelligenceSnapshot, MarketStateHistory, RegimeSelection, RsMarket } from "../api/types";
import { CockpitView, nm } from "../components/CockpitView";

const snapshot = snap as unknown as IntelligenceSnapshot;
const history = hist as unknown as MarketStateHistory;
const cockpit = ckFx as unknown as Cockpit;

const mkt = (status: RsMarket["status"], excluded = false): RsMarket => ({
  status, score: 0.3, available: 4, total: 5, coverage: 0.8,
  signals: [
    { key: "spx", label: "S&P 500", market: "us", value: 1.2, expected: 1, score: 0.8, state: "AVAILABLE", note: "" },
    { key: "breadth", label: "Breadth", market: "us", value: null, expected: 1, score: null, state: excluded ? "EXCLUDED" : "AVAILABLE", note: "데이터 없음" },
  ],
});

const sel: RegimeSelection = {
  selected_regime: "NEUTRAL", regime_confidence: 52, selection_status: "NO_ELIGIBLE", primary_reason: "어느 regime 도 주요 Trigger 를 넘지 않았다.",
  alternative_candidates: [], us_equity_confirmation: "PARTIAL", korea_equity_confirmation: "CONTRADICTED", global_equity_confirmation: "MIXED",
  persistence_assessment: "공식 Liquidity Stress 유지 · 전환 후보 1/2", data_coverage: 76, selection_rationale: "후보가 없다.",
  commentary: "미국 지수는 반등했지만 한국은 대표 종목 대부분이 내렸다. 어느 regime 도 Trigger 를 넘지 않아 혼재 상태로 본다.",
  source: "session", status: "ok", reason: "", quant_label: "NEUTRAL", candidates: [], neutral_equity: { us: mkt("PARTIAL", true), kr: mkt("CONTRADICTED"), global: mkt("MIXED") },
  primary_signal: "Growth -0.62", coverage_detail: {}, excluded: ["US Breadth", "KOSPI 상승종목 비율"], warnings: [],
};

describe("REGIME v2 · MARKET NOW", () => {
  it("공식과 오늘 선택이 다르면 PENDING · confidence 와 coverage 는 따로 · 주식 확인 3칸", () => {
    const n = { ...cockpit.market_now, label: "LIQUIDITY_STRESS", label_text: "LIQUIDITY STRESS", raw_label: "NEUTRAL", raw_text: "NO REGIME", raw_persistence_days: 1, required_days: 2, selection: sel };
    render(<CockpitView cockpit={{ ...cockpit, market_now: n }} snapshot={snapshot} history={history} />);
    expect(screen.getByTestId("ck-rs-conf").textContent).toBe("52");
    expect(screen.getByTestId("ck-rs-cov").textContent).toBe("76%");
    expect(screen.getByTestId("ck-rs-pending").textContent).toContain("NEUTRAL / MIXED");
    expect(screen.getByTestId("ck-rs-pending").textContent).toContain("1 / 2 DAYS");
    expect(screen.getByTestId("ck-rs-US").textContent).toContain("PARTIAL");
    expect(screen.getByTestId("ck-rs-KOREA").textContent).toContain("CONTRADICTED");
    expect(screen.getByTestId("ck-rs-GLOBAL").textContent).toContain("MIXED");
    expect(screen.getByTestId("ck-rs-why").textContent).toContain("한국은 대표 종목");
    // 화면에 NO REGIME 을 쓰지 않는다
    expect(screen.getByTestId("ck-now").textContent).not.toContain("NO REGIME");
    fireEvent.click(screen.getByText(/Equity read/));
    expect(screen.getByTestId("ck-rs-read").textContent).toContain("UNAVAILABLE · EXCLUDED");
    expect(screen.getByTestId("ck-rs-candidates").textContent).toContain("자격 있는 후보 없음");
  });

  it("v2 이전 저장본(selection 없음)은 블록 없이 그대로", () => {
    render(<CockpitView cockpit={cockpit} snapshot={snapshot} history={history} />);
    expect(screen.queryByTestId("ck-rs")).toBeNull();
  });

  it("nm — 예전 문구의 NO REGIME 을 보일 때만 바꾼다", () => {
    expect(nm("RISK-ON → NO REGIME")).toBe("RISK-ON → NEUTRAL / MIXED");
    expect(nm(null)).toBe("");
  });
});
