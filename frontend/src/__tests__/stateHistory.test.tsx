/** Market State · 온도계 한 달 히스토리 (2026-09-23). 서버가 준 것을 그대로, 없는 날은 잇지도 칠하지도 않는다. */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import hist from "../__fixtures__/state_history.json";
import type { MarketStateHistory } from "../api/types";
import { LABEL_KO, StateHistoryStrip } from "../components/StateHistoryStrip";

const data = hist as unknown as MarketStateHistory;

describe("StateHistoryStrip", () => {
  it("하루 한 칸의 확신 기둥(보조지표)과 라벨 띠가 있다", () => {
    render(<StateHistoryStrip history={data} />);
    const cells = screen.getAllByRole("listitem");
    expect(cells.length).toBe(data.points.length);
    const first = data.points[0]!;
    expect(cells[0]).toHaveAttribute("data-label", first.label);
    expect(cells[0]).toHaveAttribute("data-confidence", first.confidence.toFixed(0));
    const bar = cells[0]!.querySelector(".sh-conf-bar") as HTMLElement;
    expect(bar.style.height).toBe(`${Math.max(2, first.confidence)}%`);
    expect(cells[0]!.querySelector(".sh-conf-band")).not.toBeNull();
  });

  it("종합 온도는 날마다 점과 숫자, 가격·뉴스는 점으로, 없는 날은 빈 채로", () => {
    const { container } = render(<StateHistoryStrip history={data} />);
    for (const p of data.points) {
      const el = container.querySelector(`.sh-pt[data-date="${p.date}"]`)!;
      if (p.composite === null) expect(el.textContent).toBe("–");
      else expect(el.textContent).toMatch(/^[+-]\d+$/);
      expect(el.querySelector(".sh-dot-news") !== null).toBe(p.news_temperature !== null);
      expect(el.querySelector(".sh-dot-price") !== null).toBe(p.price_temperature !== null);
    }
    // 세 선: 종합(굵은)·가격·뉴스 — 값이 없는 구간은 잇지 않는다
    const lines = container.querySelectorAll("polyline");
    expect(lines.length).toBeGreaterThanOrEqual(2);
  });

  it("재료 히트맵은 온도계 스트립 항목을 날짜별로 그리고 결측은 비운다", () => {
    const { container } = render(<StateHistoryStrip history={data} />);
    const rows = container.querySelectorAll(".sh-heat-row");
    expect(rows.length).toBe(Object.keys(data.component_labels).length);
    for (const [k, label] of Object.entries(data.component_labels)) {
      const row = [...rows].find((r) => r.querySelector(".sh-heat-label")?.textContent === label)!;
      expect(row).toBeTruthy();
      const cells = row.querySelectorAll(".sh-heat-cell");
      expect(cells.length).toBe(data.points.length);
      data.points.forEach((p, i) => {
        const v = p.components[k] ?? null;
        if (v === null) { expect(cells[i]!.textContent).toBe(""); expect(cells[i]!.classList.contains("sh-heat-na")).toBe(true); }
        else expect(cells[i]!.textContent).toBe(String(Math.round(v)));
      });
    }
  });

  it("지금이 무엇이고 며칠째인지, 직전 라벨·전환 횟수·세 온도를 쓴다", () => {
    render(<StateHistoryStrip history={data} />);
    const last = data.points[data.points.length - 1]!;
    const now = screen.getByText(/지금/).closest(".sh-now") as HTMLElement;
    expect(within(now).getByText(LABEL_KO[last.label]!)).toBeInTheDocument();
    expect(now.textContent).toContain(`${data.current_streak}일째`);
    expect(now.textContent).toContain(`전환 ${data.changes}회`);
    expect(now.textContent).toContain("종합");
    if (data.previous_label) expect(now.textContent).toContain(`직전 ${LABEL_KO[data.previous_label]}`);
  });

  it("범례의 일수 합은 점 수와 같다", () => {
    render(<StateHistoryStrip history={data} />);
    const total = Object.values(data.days_by_label).reduce((a, b) => a + b, 0);
    expect(total).toBe(data.points.length);
  });

  it("히스토리가 없으면 아무것도 그리지 않고, 점이 없으면 그렇게 말한다", () => {
    const { container } = render(<StateHistoryStrip history={null} />);
    expect(container.querySelector(".sh")).toBeNull();
    render(<StateHistoryStrip history={{ ...data, points: [], segments: [] }} />);
    expect(screen.getByText(/봉이 없습니다/)).toBeInTheDocument();
  });
});
