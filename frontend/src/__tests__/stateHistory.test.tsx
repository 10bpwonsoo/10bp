/** Market State · 온도계 한 달 히스토리 (2026-09-23). 서버가 준 것을 그대로, 없는 날은 잇지도 칠하지도 않는다. */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import hist from "../__fixtures__/state_history.json";
import type { MarketStateHistory } from "../api/types";
import { LABEL_KO, StateHistoryStrip, bandName, historyPrimaryFor } from "../components/StateHistoryStrip";

const data = hist as unknown as MarketStateHistory;

describe("StateHistoryStrip", () => {
  it("하루 한 칸의 확신 기둥(보조지표)과 밴드 띠가 있다", () => {
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

  it("기간 내내 결측인 재료는 표에서 빼고 뺐다고 적는다", () => {
    const { container } = render(<StateHistoryStrip history={{ ...data, component_labels: { RiskAppetite: "위험선호" }, excluded_components: { Credit: "신용", KoreaFlow: "한국 수급" } }} />);
    expect(container.querySelectorAll(".sh-heat-row").length).toBe(1);
    expect(container.querySelector(".sh-excluded")?.textContent).toContain("신용 · 한국 수급");
  });

  it("기본(실데이터·물가 충격)은 판정 라벨이 1차 — 지금 라벨·며칠째·직전·전환·세 온도, 띠는 라벨 색", () => {
    const { container } = render(<StateHistoryStrip history={data} />);
    const last = data.points[data.points.length - 1]!;
    const now = container.querySelector(".sh-now") as HTMLElement;
    expect(within(now).getByText(LABEL_KO[last.label]!)).toBeInTheDocument();
    expect(now.textContent).toContain(`${data.current_streak}일째`);
    expect(now.textContent).toContain(`전환 ${data.changes}회`);
    expect(now.textContent).toContain("종합");
    if (data.previous_label) expect(now.textContent).toContain(`직전 ${LABEL_KO[data.previous_label]}`);
    expect(screen.getByTestId("primary-legend").getAttribute("data-primary")).toBe("label");
    const total = Object.values(data.days_by_label).reduce((a, b) => a + b, 0);
    expect(total).toBe(data.points.length);
    const band0 = container.querySelector(".sh-conf .sh-conf-band") as HTMLElement;
    expect(band0.style.background).toContain("--lbl-");
    // 보조 줄은 공포·탐욕
    const sub = screen.getByTestId("secondary");
    expect(sub.getAttribute("data-kind")).toBe("band");
    expect(sub.textContent).toContain("보조 · 공포·탐욕");
    expect(sub.textContent).toContain(`${data.current_band_streak}일째`);
    expect(historyPrimaryFor("inflation_shock")).toBe("label");
    expect(historyPrimaryFor(null)).toBe("label");
  });

  it("AI 센티멘트 뷰만 공포·탐욕 밴드가 1차 — 띠·범례·지금·구간이 밴드, 판정 라벨은 보조 줄", () => {
    expect(historyPrimaryFor("ai_sentiment")).toBe("band");
    const { container } = render(<StateHistoryStrip history={data} primary="band" />);
    const last = data.points[data.points.length - 1]!;
    const now = container.querySelector(".sh-now") as HTMLElement;
    expect(within(now).getByText(bandName(last.band, data.band_labels))).toBeInTheDocument();
    expect(now.textContent).toContain(`${data.current_band_streak}일째`);
    expect(now.textContent).toContain(`밴드 전환 ${data.band_changes}회`);
    if (data.previous_band) expect(now.textContent).toContain(`직전 ${bandName(data.previous_band, data.band_labels)}`);
    const cells = container.querySelectorAll(".sh-conf");
    data.points.forEach((p, i) => {
      expect(cells[i]!.getAttribute("data-band")).toBe(p.band);
      expect((cells[i]!.querySelector(".sh-conf-band") as HTMLElement).style.background).toContain(`--band-${p.band}`);
    });
    const legend = screen.getByTestId("primary-legend");
    expect(legend.getAttribute("data-primary")).toBe("band");
    const total = Object.values(data.days_by_band).reduce((a, b) => a + b, 0);
    expect(total).toBe(data.points.length);
    for (const [k, v] of Object.entries(data.days_by_band)) expect(legend.textContent).toContain(`${bandName(k, data.band_labels)} ${v}`);
    expect(bandName("cool", { cool: "냉각" })).toBe("냉각(공포)");
    expect(bandName("overheated", { overheated: "과열" })).toBe("과열(극단적 탐욕)");
    expect(bandName("neutral", { neutral: "중립" })).toBe("중립");
    const sub = screen.getByTestId("secondary");
    expect(sub.getAttribute("data-kind")).toBe("label");
    expect(within(sub).getByText(LABEL_KO[last.label]!, { selector: "b" })).toBeInTheDocument();
    expect(sub.textContent).toContain(`전환 ${data.changes}회`);
  });

  it("히스토리가 없으면 아무것도 그리지 않고, 점이 없으면 그렇게 말한다", () => {
    const { container } = render(<StateHistoryStrip history={null} />);
    expect(container.querySelector(".sh")).toBeNull();
    render(<StateHistoryStrip history={{ ...data, points: [], segments: [], band_segments: [] }} />);
    expect(screen.getByText(/봉이 없습니다/)).toBeInTheDocument();
  });
});
