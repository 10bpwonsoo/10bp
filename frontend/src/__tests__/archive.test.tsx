/**
 * Daily Full Dashboard Archive · 날짜 탐색 (2026-10-21)
 * A LIVE 폴링 · B ARCHIVE 무폴링 · C 날짜 선택 · D 날짜 검색 · E 토·일 비활성 · F ◀▶ 가 주말을 건너뜀 ·
 * G 모든 탭이 같은 날짜 · H LIVE 복귀 · I 새로고침(?date=) 유지 — 그리고 없는 섹션은 지금 값으로 메우지 않음.
 */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { resolveArchived, setActiveArchive, type DashboardArchive } from "../api/archive";
import { checkDate, isWeekend, nextSaved, prevSaved } from "../components/ArchiveControl";
import snapshotFx from "../__fixtures__/snapshot.json";
import cockpit from "../__fixtures__/cockpit.json";
import stateHistory from "../__fixtures__/state_history.json";
import scenarioCheck from "../__fixtures__/scenario_check.json";
import investment from "../__fixtures__/investment.json";
import analystViews from "../__fixtures__/analyst_views.json";
import aiRegime from "../__fixtures__/ai_regime.json";
import ratesRegime from "../__fixtures__/rates_regime.json";
import oilRegime from "../__fixtures__/oil_regime.json";

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const LIVE_ASOF = "2026-10-20T22:40:00Z"; // = 10/21 07:40 KST
const liveSnapshot = { ...clone(snapshotFx), as_of: LIVE_ASOF };

/** 저장본 — 날짜마다 커버리지를 다르게 해 화면이 어느 날짜를 그리는지 구별한다. 10/15 는 AI·금리·유가가 없는 PARTIAL. */
function archiveFor(date: string): DashboardArchive {
  const n = Number(date.slice(8));
  const snap = { ...clone(snapshotFx), as_of: `${date}T00:00:00Z` } as typeof snapshotFx;
  snap.data_health = { ...snap.data_health, coverage: n / 100, available_instruments: n, expected_instruments: 100 };
  const partial = date === "2026-10-15";
  return {
    schema_version: "1", snapshot_date: date, generated_at: `${date}T00:00:00Z`, cutoff: `${date}T07:30:00+09:00`, archive_status: partial ? "PARTIAL" : "COMPLETE",
    snapshot: snap, cockpit: clone(cockpit), market_state_history: clone(stateHistory), ai_regime: partial ? null : clone(aiRegime),
    rates_regime: partial ? null : clone(ratesRegime), oil_regime: partial ? null : clone(oilRegime),
    investment: clone(investment), scenario_checks: clone(scenarioCheck), analyst_views: clone(analystViews), daily_history: {}, news: [],
    errors: partial ? { ai_regime: "RuntimeError: 실패", rates_regime: "RuntimeError: 실패", oil_regime: "RuntimeError: 실패" } : {},
    meta: { data_mode: "DELAYED", source_asof: snap.as_of, created_by: "test", archive_origin: "historical_backfill" },
  };
}

const SAVED = ["2026-10-19", "2026-10-16", "2026-10-15"];
const INDEX = SAVED.map((d) => ({ date: d, archive_status: d === "2026-10-15" ? "PARTIAL" : "COMPLETE", source_asof: `${d}T00:00:00Z` }));

let calls: string[] = [];
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

function mockFetch() {
  calls = [];
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    const path = url.split("?")[0]!;
    if (path === "/api/v1/info") return json({ status: "ok", version: "t", mode: "DELAYED", scenario: null, llm_enabled: false, zscore_window: 60 });
    if (path === "/api/v1/snapshot") return json(liveSnapshot);
    if (path === "/api/v1/cockpit") return json(cockpit);
    if (path === "/api/v1/market-state/history") return json(stateHistory);
    if (path === "/api/v1/scenario-check") return json(scenarioCheck);
    if (path === "/api/v1/investment") return json(investment);
    if (path === "/api/v1/analyst-views") return json(analystViews);
    if (path === "/api/v1/ai-regime") return json(aiRegime);
    if (path === "/api/v1/rates-regime") return json(ratesRegime);
    if (path === "/api/v1/oil-regime") return json(oilRegime);
    if (path === "/api/v1/archive/index") return json(INDEX);
    const m = /^\/api\/v1\/archive\/(\d{4}-\d{2}-\d{2})$/.exec(path);
    if (m && SAVED.includes(m[1]!)) return json(archiveFor(m[1]!));
    if (m) return json({ detail: { message: `${m[1]} 저장 화면이 없습니다`, nearest: { before: [], after: [] } } }, 404);
    return json({ detail: "not mocked" }, 404);
  }));
}

const network = (p: string) => calls.filter((u) => u.split("?")[0] === p).length;
const coverage = (n: number) => new RegExp(`커버리지 ${n}% \\(${n}/100`);

async function openPop() {
  fireEvent.click(await screen.findByTestId("archive-toggle"));
  return screen.findByTestId("archive-pop");
}

async function pickDay(date: string) {
  await openPop();
  const day = await screen.findByTestId("archive-calendar");
  const btn = within(day).getAllByTestId("archive-day").find((b) => b.getAttribute("data-date") === date)!;
  await act(async () => { fireEvent.click(btn); });
  await screen.findByTestId("archive-banner");
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  mockFetch();
  history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  setActiveArchive(null);
});

describe("date helpers", () => {
  it("E/F: weekends are not snapshot days and prev/next skip them", () => {
    expect(isWeekend("2026-10-17")).toBe(true);
    expect(isWeekend("2026-10-18")).toBe(true);
    expect(isWeekend("2026-10-16")).toBe(false);
    expect(nextSaved(SAVED, "2026-10-16")).toBe("2026-10-19");
    expect(prevSaved(SAVED, "2026-10-19")).toBe("2026-10-16");
    expect(checkDate("2026-10-17", SAVED)).toMatchObject({ kind: "weekend", dayKo: "토요일", prev: "2026-10-16", next: "2026-10-19" });
    expect(checkDate("2026-10-14", SAVED)).toMatchObject({ kind: "missing", prev: undefined, next: "2026-10-15" });
    expect(checkDate("2026/10/15", SAVED)).toMatchObject({ kind: "invalid" });
    expect(checkDate("2026-10-16", SAVED)).toEqual({ kind: "ok", date: "2026-10-16" });
  });
});

describe("Daily archive mode", () => {
  it("A: LIVE keeps the 5s polling and shows LIVE · latest date", async () => {
    render(<App />);
    await waitFor(() => expect(network("/api/v1/snapshot")).toBeGreaterThanOrEqual(1));
    expect(await screen.findByTestId("archive-date")).toHaveTextContent("2026-10-21");
    expect(screen.getByTestId("archive-mode")).toHaveTextContent("LIVE");
    const before = network("/api/v1/snapshot");
    await act(async () => { vi.advanceTimersByTime(5000); });
    await waitFor(() => expect(network("/api/v1/snapshot")).toBeGreaterThan(before));
    expect(screen.getByText("지금 업데이트")).toBeInTheDocument();
  });

  it("B/C: picking a calendar day renders that archive and never polls", async () => {
    render(<App />);
    await screen.findByText(/커버리지 100%/);
    await pickDay("2026-10-16");
    expect(screen.getByTestId("archive-date")).toHaveTextContent("2026-10-16");
    expect(screen.getByTestId("archive-mode")).toHaveTextContent("ARCHIVE");
    await screen.findByText(coverage(16));
    const s = network("/api/v1/snapshot"), inv = network("/api/v1/investment"), ck = network("/api/v1/cockpit");
    await act(async () => { vi.advanceTimersByTime(120_000); });
    expect(network("/api/v1/snapshot")).toBe(s);
    expect(network("/api/v1/investment")).toBe(inv);
    expect(network("/api/v1/cockpit")).toBe(ck);
    expect(new URLSearchParams(location.search).get("date")).toBe("2026-10-16");
    expect(screen.queryByText("지금 업데이트")).toBeNull();
  });

  it("D: date search loads a saved date, explains a missing one and rejects bad input", async () => {
    render(<App />);
    await openPop();
    const input = screen.getByTestId("archive-search");
    fireEvent.change(input, { target: { value: "2026-10-14" } });
    await act(async () => { fireEvent.click(screen.getByTestId("archive-search-go")); });
    expect(screen.getByTestId("archive-missing")).toHaveTextContent("2026-10-14 저장 화면이 없습니다.");
    expect(screen.getByTestId("archive-near-next")).toHaveTextContent("2026-10-15");
    fireEvent.change(input, { target: { value: "20261015" } });
    await act(async () => { fireEvent.click(screen.getByTestId("archive-search-go")); });
    expect(screen.getByTestId("archive-missing")).toHaveTextContent("YYYY-MM-DD");
    fireEvent.change(input, { target: { value: "2026-10-19" } });
    await act(async () => { fireEvent.click(screen.getByTestId("archive-search-go")); });
    await screen.findByTestId("archive-banner");
    await screen.findByText(coverage(19));
  });

  it("E: weekends are disabled in the calendar and a weekend search says it is not a snapshot day", async () => {
    render(<App />);
    await openPop();
    const days = within(screen.getByTestId("archive-calendar")).getAllByTestId("archive-day");
    const byDate = (d: string) => days.find((b) => b.getAttribute("data-date") === d)!;
    expect(byDate("2026-10-17")).toBeDisabled();
    expect(byDate("2026-10-18")).toBeDisabled();
    expect(byDate("2026-10-14")).toBeDisabled(); // 저장 없는 평일
    expect(byDate("2026-10-16")).toBeEnabled();
    fireEvent.change(screen.getByTestId("archive-search"), { target: { value: "2026-10-17" } });
    await act(async () => { fireEvent.click(screen.getByTestId("archive-search-go")); });
    expect(screen.getByTestId("archive-missing")).toHaveTextContent("2026-10-17은 토요일로 Daily Snapshot 생성 대상이 아닙니다.");
    expect(screen.getByTestId("archive-near-prev")).toHaveTextContent("2026-10-16");
    expect(screen.getByTestId("archive-near-next")).toHaveTextContent("2026-10-19");
    expect(network("/api/v1/archive/2026-10-17")).toBe(0);
  });

  it("F: ▶ from 10/16 skips the weekend to 10/19, ◀ goes back to 10/16", async () => {
    render(<App />);
    await pickDay("2026-10-16");
    await act(async () => { fireEvent.click(screen.getByTestId("archive-newer")); });
    await waitFor(() => expect(screen.getByTestId("archive-date")).toHaveTextContent("2026-10-19"));
    await screen.findByText(coverage(19));
    await act(async () => { fireEvent.click(screen.getByTestId("archive-older")); });
    await waitFor(() => expect(screen.getByTestId("archive-date")).toHaveTextContent("2026-10-16"));
    expect(network("/api/v1/archive/2026-10-17")).toBe(0);
    expect(network("/api/v1/archive/2026-10-18")).toBe(0);
  });

  it("G: every tab uses the same selected archive and never fetches live data", async () => {
    render(<App />);
    await pickDay("2026-10-19");
    const tabs = screen.getByTestId("scenario-tabs");
    for (const name of [/^AI 센티2?/, /^물가 충격/, /^유가 급등/, /^평시/]) {
      const btn = within(tabs).getAllByRole("button").find((b) => name.test(b.textContent ?? ""));
      if (!btn) continue;
      await act(async () => { fireEvent.click(btn); });
      expect(screen.getByTestId("archive-date")).toHaveTextContent("2026-10-19");
    }
    expect(network("/api/v1/ai-regime")).toBe(0);
    expect(network("/api/v1/rates-regime")).toBe(0);
    expect(network("/api/v1/oil-regime")).toBe(0);
    // 10/15 는 AI 가 저장되지 않았다 — 지금 값으로 메우지 않는다
    await act(async () => { fireEvent.click(within(tabs).getAllByRole("button")[0]!); });
    await pickDay("2026-10-15");
    expect(screen.getByTestId("archive-missing-sections")).toHaveTextContent("AI 센티");
    const ai = within(screen.getByTestId("scenario-tabs")).getAllByRole("button").find((b) => /^AI 센티/.test(b.textContent ?? ""))!;
    await act(async () => { fireEvent.click(ai); });
    expect(await screen.findByTestId("not-archived")).toHaveTextContent("DATA UNAVAILABLE FOR THIS DATE");
    expect(network("/api/v1/ai-regime")).toBe(0);
    expect(() => resolveArchived(archiveFor("2026-10-15"), "/api/v1/ai-regime")).toThrow(/NOT ARCHIVED/);
  });

  it("H: LIVE로 돌아가기 restores live data, polling and the refresh button", async () => {
    render(<App />);
    await pickDay("2026-10-16");
    const before = network("/api/v1/snapshot");
    await act(async () => { fireEvent.click(screen.getByTestId("archive-back-live")); });
    expect(screen.queryByTestId("archive-banner")).toBeNull();
    expect(screen.getByTestId("archive-mode")).toHaveTextContent("LIVE");
    expect(await screen.findByText("지금 업데이트")).toBeInTheDocument();
    await waitFor(() => expect(network("/api/v1/snapshot")).toBeGreaterThan(before));
    await act(async () => { vi.advanceTimersByTime(5000); });
    await waitFor(() => expect(network("/api/v1/snapshot")).toBeGreaterThan(before + 1));
    expect(new URLSearchParams(location.search).get("date")).toBeNull();
  });

  it("I: a reload with ?date= opens that archive, and back returns to LIVE", async () => {
    history.replaceState(null, "", "/?date=2026-10-19");
    render(<App />);
    await screen.findByTestId("archive-banner");
    expect(screen.getByTestId("archive-date")).toHaveTextContent("2026-10-19");
    await screen.findByText(coverage(19));
    await act(async () => {
      history.replaceState(null, "", "/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    await waitFor(() => expect(screen.queryByTestId("archive-banner")).toBeNull());
    expect(screen.getByTestId("archive-mode")).toHaveTextContent("LIVE");
  });

  it("keeps the compact navigator inside the topbar", async () => {
    render(<App />);
    const control = await screen.findByTestId("archive-control");
    const header = control.closest("header.topbar") as HTMLElement;
    expect(header).not.toBeNull();
    for (const id of ["archive-older", "archive-toggle", "archive-newer", "archive-mode"]) expect(within(header).getByTestId(id)).toBeInTheDocument();
  });
});
