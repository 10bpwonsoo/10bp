/** AI THEME VIEW (2026-11-12) — 레짐 이름 바로 아래, 헤드라인 · 요약 · DRIVER · STRENGTH · WEAK POINT · NEXT. 생성되지 않았으면 그렇다고만(규칙 문장으로 채우지 않는다). */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import snap from "../__fixtures__/snapshot.json";
import hist from "../__fixtures__/state_history.json";
import regimeFx from "../__fixtures__/ai_regime.json";
import checksFx from "../__fixtures__/scenario_check.json";
import type { AiRegime, AiThemeView, IntelligenceSnapshot, MarketStateHistory, ScenarioCheck } from "../api/types";
import { AiRegimeView } from "../components/AiRegimeView";

const regime = regimeFx as unknown as AiRegime;
const snapshot = snap as unknown as IntelligenceSnapshot;
const history = hist as unknown as MarketStateHistory;
const check = (checksFx as unknown as ScenarioCheck[])[0]!;
const view: AiThemeView = { headline: "반등은 넓어졌지만 가격이 앞서는 랠리", summary: "소프트웨어와 전력이 반등을 이끌었습니다. 다만 반도체 펀더멘털이 이를 확인하지 못했습니다.",
  driver: "소프트웨어 · 전력", strength: "상대강도 회복", weak_point: "펀더멘털 미확인", next_watch: "메모리 가격", source: "session", status: "ok", reason: "", generated_at: "2026-11-12T00:00:00Z" };

describe("AI THEME VIEW", () => {
  it("레짐 이름 바로 아래(엔진 헤드라인보다 먼저) 헤드라인 · 요약 · 네 줄", () => {
    const { container } = render(<AiRegimeView regime={{ ...regime, theme_view: view }} snapshot={snapshot} check={check} history={history} extended />);
    const tv = screen.getByTestId("ai-theme-view");
    expect(within(tv).getByTestId("ai-tv-headline").textContent).toBe(view.headline);
    expect(within(tv).getByTestId("ai-tv-summary").textContent).toBe(view.summary);
    for (const id of ["driver", "strength", "weak", "next"]) expect(within(tv).getByTestId(`ai-tv-${id}`)).toBeTruthy();
    const card = within(screen.getByTestId("ai-regime-card")).getByTestId("ai-theme-view");
    const head = container.querySelector(".ai-headline")!;
    expect(card.compareDocumentPosition(head) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("생성되지 않았으면 문장 없이 그렇다고만", () => {
    render(<AiRegimeView regime={{ ...regime, theme_view: { ...view, headline: "", summary: "", status: "unavailable", source: "none", reason: "API 인증 실패" } }} snapshot={snapshot} check={check} history={history} extended />);
    const tv = screen.getByTestId("ai-theme-view");
    expect(tv.textContent).toMatch(/생성되지 않음/);
    expect(within(tv).queryByTestId("ai-tv-headline")).toBeNull();
  });

  it("이 기능 이전 저장본(theme_view 없음)은 영역을 그리지 않는다", () => {
    render(<AiRegimeView regime={regime} snapshot={snapshot} check={check} history={history} extended />);
    expect(screen.queryByTestId("ai-theme-view")).toBeNull();
  });
});
