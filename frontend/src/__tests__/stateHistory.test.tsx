/** Market State 한 달 히스토리 띠 (2026-09-23). 서버가 준 것을 그대로, 없는 날은 잇지 않는다. */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import hist from "../__fixtures__/state_history.json";
import type { MarketStateHistory } from "../api/types";
import { LABEL_KO, StateHistoryStrip } from "../components/StateHistoryStrip";

const data = hist as unknown as MarketStateHistory;

describe("StateHistoryStrip", () => {
  it("하루 한 칸, 확신이 높이가 된다", () => {
    render(<StateHistoryStrip history={data} />);
    const cells = screen.getAllByRole("listitem");
    expect(cells.length).toBe(data.points.length);
    const first = data.points[0]!;
    expect(cells[0]).toHaveAttribute("data-label", first.label);
    expect(cells[0]).toHaveAttribute("data-date", first.date);
    const bar = cells[0]!.querySelector(".sh-bar") as HTMLElement;
    expect(bar.style.height).toBe(`${Math.max(12, first.confidence)}%`);
  });

  it("지금이 무엇이고 며칠째인지, 직전 라벨과 전환 횟수를 쓴다", () => {
    render(<StateHistoryStrip history={data} />);
    const last = data.points[data.points.length - 1]!;
    const now = screen.getByText(/지금/).closest(".sh-now") as HTMLElement;
    expect(within(now).getByText(LABEL_KO[last.label]!)).toBeInTheDocument();
    expect(now.textContent).toContain(`${data.current_streak}일째`);
    expect(now.textContent).toContain(`전환 ${data.changes}회`);
    if (data.previous_label) expect(now.textContent).toContain(`직전 ${LABEL_KO[data.previous_label]}`);
  });

  it("범례의 일수 합은 점 수와 같다", () => {
    render(<StateHistoryStrip history={data} />);
    const total = Object.values(data.days_by_label).reduce((a, b) => a + b, 0);
    expect(total).toBe(data.points.length);
    for (const [k, v] of Object.entries(data.days_by_label)) {
      const leg = screen.getAllByText(new RegExp(`^${LABEL_KO[k]}`)).find((el) => el.classList.contains("sh-leg"));
      expect(leg?.textContent).toContain(String(v));
    }
  });

  it("가격 온도가 없는 날은 선을 잇지 않는다", () => {
    const pts = data.points.map((p, i) => (i === 5 ? { ...p, price_temperature: null } : p));
    const { container } = render(<StateHistoryStrip history={{ ...data, points: pts }} />);
    const lines = container.querySelectorAll("polyline");
    expect(lines.length).toBe(2);
    expect(container.querySelector(".sh-note")?.textContent).toContain("뉴스 온도");
  });

  it("히스토리가 없으면 아무것도 그리지 않고, 점이 없으면 그렇게 말한다", () => {
    const { container } = render(<StateHistoryStrip history={null} />);
    expect(container.querySelector(".sh")).toBeNull();
    render(<StateHistoryStrip history={{ ...data, points: [], segments: [] }} />);
    expect(screen.getByText(/봉이 없습니다/)).toBeInTheDocument();
  });
});
