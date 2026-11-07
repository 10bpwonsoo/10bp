/**
 * History 날짜 기준 (2026-10-21) — x축은 KST Daily Snapshot 날짜 한 기준. 같은 날짜 라벨은 한 번,
 * 폭이 모자라면 라벨만 솎고(칸은 그대로), 장중 LIVE 는 daily 띠가 아니라 따로 보인다.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ckFx from "../__fixtures__/cockpit.json";
import type { CkRegimeDay, CkRegimeHistory } from "../api/types";
import { RegimeHistoryCard } from "../components/RegimeHistoryCard";
import { duplicateDates, maxLabelsFor, thinLabels } from "../lib/historyDates";

const base = (ckFx as unknown as { history: CkRegimeHistory }).history;
const weekdays = (from: string, n: number): string[] => {
  const out: string[] = []; const d = new Date(`${from}T00:00:00Z`);
  while (out.length < n) { if (d.getUTCDay() % 6 !== 0) out.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); }
  return out;
};
function kstHistory(n = 22, extra: Partial<CkRegimeHistory> = {}): CkRegimeHistory {
  const dates = weekdays("2026-09-22", n);
  const tpl = base.days[0] as CkRegimeDay;
  const days = dates.map((date, i) => ({ ...tpl, date, market_date: dates[i - 1] ?? "2026-09-21", storage_date: dates[i - 1] ?? "2026-09-21", is_transition: i === n - 2 || i === n - 4, source: "RECORDED" as const, locked: true }));
  return { ...base, days, composite: days.map(() => 0), drivers: base.drivers.map((d) => ({ ...d, values: days.map(() => 0) })), date_basis: "kst_snapshot", snapshot_time: "07:30 KST", gaps: [], intraday: null, ...extra };
}

afterEach(() => { vi.unstubAllGlobals(); });

describe("thinLabels / duplicateDates", () => {
  it("모두 들어가면 전부, 아니면 첫·끝을 두고 고르게 — 이웃 간격이 너무 가깝지 않다", () => {
    expect(thinLabels(5, 10)).toEqual([0, 1, 2, 3, 4]);
    for (const [n, m] of [[22, 8], [22, 5], [22, 2], [10, 3], [23, 9]] as const) {
      const ix = thinLabels(n, m);
      expect(ix[0]).toBe(0); expect(ix[ix.length - 1]).toBe(n - 1);
      expect(ix.length).toBeLessThanOrEqual(m + 1);
      const step = Math.ceil((n - 1) / (Math.max(2, m) - 1));
      for (let k = 1; k < ix.length; k++) expect(ix[k]! - ix[k - 1]!).toBeGreaterThanOrEqual(step);
    }
    expect(maxLabelsFor(320)).toBe(7); expect(maxLabelsFor(600, 18)).toBe(18);
  });
  it("같은 날짜는 중복으로 잡는다", () => {
    expect(duplicateDates(["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-21 LIVE"])).toEqual(["2026-10-21"]);
    expect(duplicateDates(["2026-10-19", "2026-10-20"])).toEqual([]);
  });
});

describe("Market Regime History x축", () => {
  it("데스크톱: 22거래일 라벨 전부 · 중복 없음 · 전환 ▲ 는 날짜 글자 없이", () => {
    render(<RegimeHistoryCard h={kstHistory()} />);
    const labels = screen.getAllByTestId("ck-h-axis-label").map((e) => e.textContent);
    expect(labels.length).toBe(22);
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels[labels.length - 1]).toBe("10/21");
    expect(screen.getAllByTestId("ck-h-mark").every((e) => e.textContent === "▲")).toBe(true);
    expect(screen.queryByTestId("ck-h-dupes")).toBeNull();
  });

  it("모바일: 라벨만 솎는다 — 칸 22개는 그대로, 첫·끝 날짜는 남는다", () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("max-width"), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false }));
    render(<RegimeHistoryCard h={kstHistory()} />);
    expect(screen.getAllByTestId("ck-h-cell").length).toBe(22);
    const labels = screen.getAllByTestId("ck-h-axis-label").map((e) => e.textContent);
    expect(labels.length).toBeLessThanOrEqual(8);
    expect(labels[0]).toBe("09/22"); expect(labels[labels.length - 1]).toBe("10/21");
    fireEvent.mouseEnter(screen.getAllByTestId("ck-h-cell")[5]!);
    expect(screen.getByTestId("ck-h-tip").textContent).toContain("2026-09-29"); // 라벨이 없는 칸도 툴팁에서 정확한 날짜
  });

  it("Snapshot 날짜와 미국 장 날짜를 따로 적고, 장중 LIVE 는 daily 띠 밖에 보인다", () => {
    const h = kstHistory(22, { intraday: { date: "2026-10-21", as_of: "2026-10-21T07:00:21Z", market_date: "2026-10-20", raw_state: "NEUTRAL", raw_regime: "neutral", raw_label: "Neutral / Mixed", evidence_strength: 34, official_regime: "neutral", official_label: "Neutral / Mixed", transition_status: "CHANGED", transition_status_ko: "", calculated_at: "", source: "LIVE" }, gaps: ["2026-10-14"] });
    render(<RegimeHistoryCard h={h} />);
    const snap = screen.getByTestId("ck-h-snapshot").textContent ?? "";
    expect(snap).toContain("2026-10-21"); expect(snap).toContain("07:30 KST"); expect(snap).toContain("2026-10-20 close");
    expect(screen.getByTestId("ck-h-intraday").textContent).toContain("10/21 16:00 KST");
    expect(screen.getAllByTestId("ck-h-cell").length).toBe(22);
    expect(screen.getByTestId("ck-h-gaps").textContent).toContain("10/14");
  });

  it("데이터에 같은 날짜가 두 번 오면 라벨은 한 번만, 경고를 띄운다(숨기지 않고 알린다)", () => {
    const h = kstHistory();
    const days = [...h.days.slice(0, -1), { ...(h.days[h.days.length - 2] as CkRegimeDay) }];
    render(<RegimeHistoryCard h={{ ...h, days, composite: days.map(() => 0) }} />);
    expect(screen.getByTestId("ck-h-dupes").textContent).toContain("2026-10-20");
    const labels = screen.getAllByTestId("ck-h-axis-label").map((e) => e.textContent);
    expect(new Set(labels).size).toBe(labels.length);
  });
});
