/** 유가 탭 — 시장 원인 판별 화면. Regime → Driver → Confirmation → Narrative → Watch → Diagnostics 순서, 원인 단정 없음. */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import hist from "../__fixtures__/state_history.json";
import regimeFx from "../__fixtures__/oil_regime.json";
import checksFx from "../__fixtures__/scenario_check.json";
import type { IntelligenceSnapshot, MarketStateHistory, OilRegime, ScenarioCheck } from "../api/types";
import { OilRegimeView, strengthColor } from "../components/OilRegimeView";
import { ScenarioView } from "../components/ScenarioView";

const snapshot = snap as unknown as IntelligenceSnapshot;
const history = hist as unknown as MarketStateHistory;
const regime = regimeFx as unknown as OilRegime;
const check: ScenarioCheck = { ...(checksFx as unknown as ScenarioCheck[]).find((c) => c.name === "oil_spike")!, focus: "oil_regime" };

describe("OilRegimeView", () => {
  it("What To Watch Next — 사람이 읽는 제목 · 현재 값 · 기준(작게)으로 나누되 엔진 문장·조건은 하나도 버리지 않는다", () => {
    render(<OilRegimeView regime={regime} snapshot={snapshot} check={check} history={history} />);
    const items = screen.getAllByTestId("watch-item");
    items.forEach((li, i) => {
      const w = regime.watch[i]!;
      expect(li.querySelector(".or-watch-now")!.textContent).toBe(`현재 ${w.metric} ${w.current}`);
      expect(li.querySelector(".or-watch-meta")!.textContent).toBe(`기준 ${w.condition}`);
      const head = li.querySelector(".or-watch-head")!.textContent!;
      const rest = li.querySelector(".or-watch-rest")?.textContent ?? "";
      expect(rest ? `${head}: ${rest}` : head).toBe(w.text);
    });
  });

  it("데스크톱 grid 자리 class — 금리·유가 본문 카드가 정보량별 폭(12열)을 받는다", () => {
    const { container } = render(<OilRegimeView regime={regime} snapshot={snapshot} check={check} history={history} />);
    for (const c of ["g-regime", "g-drivers", "g-conf", "g-nar", "g-watch", "g-diag"]) expect(container.querySelectorAll(`.or > .${c}`).length).toBe(1);
  });

  it("최상단 REGIME 카드가 dominant driver 와 상태(CONFIRMED/UNCONFIRMED/CONTRADICTED), 신호 강도를 말한다", () => {
    render(<OilRegimeView regime={regime} snapshot={snapshot} check={check} history={history} />);
    const card = screen.getByTestId("oil-regime-card");
    expect(card.textContent).toContain(regime.regime_label.split(" — ")[0]!);
    const dom = regime.drivers.find((d) => d.id === regime.dominant)!;
    expect(screen.getByTestId("oil-status").textContent).toContain(dom.status);
    expect(card.textContent).toContain(regime.signal_strength_label);
    // 9/29 실데이터 예시: 거시·유동성 위험회피가 지정학 공급 충격보다 우세
    expect(regime.dominant).toBe("macro_liquidity");
    expect(dom.score).toBeLessThan(-50);
    expect(regime.drivers.find((d) => d.id === "geopolitical")!.status).toBe("UNCONFIRMED");
  });

  it("driver 4개가 점수 순으로, 확인표·내러티브·감시 조건이 있고 '아님/require' 식 판정 문구는 메인에 없다", () => {
    const { container } = render(<OilRegimeView regime={regime} snapshot={snapshot} check={check} history={history} />);
    const drivers = screen.getAllByTestId("oil-driver");
    expect(drivers.length).toBe(4);
    const scores = drivers.map((d) => Math.abs(regime.drivers.find((x) => x.id === d.getAttribute("data-id"))!.score));
    expect([...scores].sort((a, b) => b - a)).toEqual(scores);
    expect(container.querySelectorAll('.or-conf[data-status="confirms"]').length).toBe(regime.confirmations.filter((r) => r.status === "confirms").length);
    expect(screen.getAllByTestId("narrative-row").length).toBe(regime.narrative.length);
    const watch = screen.getAllByTestId("watch-item");
    expect(watch.length).toBeGreaterThanOrEqual(3);
    expect(watch.length).toBeLessThanOrEqual(5);
    // 판정 룰 문구는 Diagnostics(details) 안에만
    const diag = screen.getByTestId("oil-diagnostics");
    expect(within(diag).getAllByText(/require/i).length).toBeGreaterThan(0);
    const mainText = Array.from(container.querySelectorAll(".panel:not(details)")).map((e) => e.textContent).join(" ");
    expect(mainText).not.toMatch(/Geopolitical Risk 아님|require 실패/);
    expect(strengthColor("STRONG")).toBe("var(--crit)");
  });

  it("ScenarioView 는 유가 탭(focus=oil_regime)에서 원인 판별 화면을 그린다", () => {
    render(<ScenarioView check={check} snapshot={snapshot} history={history} investment={null} oilRegime={regime} />);
    expect(screen.getByTestId("oil-regime")).toBeInTheDocument();
  });
});
