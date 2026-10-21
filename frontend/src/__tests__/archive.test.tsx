/** Daily Full Dashboard Archive(2026-10-21) — LIVE 폴링 · ARCHIVE 무폴링 · 날짜 선택 · 지금 업데이트 숨김 · LIVE 복귀 · 없는 섹션은 지금 값으로 메우지 않음. */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { resolveArchived, setActiveArchive, type DashboardArchive } from "../api/archive";
import snapshot from "../__fixtures__/snapshot.json";
import cockpit from "../__fixtures__/cockpit.json";
import stateHistory from "../__fixtures__/state_history.json";
import scenarioCheck from "../__fixtures__/scenario_check.json";
import investment from "../__fixtures__/investment.json";
import analystViews from "../__fixtures__/analyst_views.json";

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

/** 저장본 — 지금 값과 구별되도록 커버리지를 27/54 로 바꿔 둔다. AI 섹션은 일부러 없다(PARTIAL). */
function archiveFor(date: string): DashboardArchive {
  const snap = clone(snapshot) as typeof snapshot;
  snap.data_health = { ...snap.data_health, coverage: 0.5, available_instruments: 27, expected_instruments: 54 };
  return {
    schema_version: "1", snapshot_date: date, generated_at: `${date}T00:00:00Z`, archive_status: "PARTIAL",
    snapshot: snap, cockpit: clone(cockpit), market_state_history: clone(stateHistory), ai_regime: null, rates_regime: null, oil_regime: null,
    investment: clone(investment), scenario_checks: clone(scenarioCheck), analyst_views: clone(analystViews), daily_history: {}, news: [],
    errors: { ai_regime: "RuntimeError: 실패", rates_regime: "RuntimeError: 실패", oil_regime: "RuntimeError: 실패" },
    meta: { data_mode: "DELAYED", source_asof: snapshot.as_of, created_by: "test" },
  };
}

const INDEX = [
  { date: "2026-10-15", archive_status: "PARTIAL", source_asof: "2026-10-14T23:31:59Z" },
  { date: "2026-10-13", archive_status: "COMPLETE", source_asof: "2026-10-13T00:12:16Z" },
];

let calls: string[] = [];

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

function mockFetch() {
  calls = [];
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    const path = url.split("?")[0]!;
    if (path === "/api/v1/info") return json({ status: "ok", version: "t", mode: "DELAYED", scenario: null, llm_enabled: false, zscore_window: 60 });
    if (path === "/api/v1/snapshot") return json(snapshot);
    if (path === "/api/v1/cockpit") return json(cockpit);
    if (path === "/api/v1/market-state/history") return json(stateHistory);
    if (path === "/api/v1/scenario-check") return json(scenarioCheck);
    if (path === "/api/v1/investment") return json(investment);
    if (path === "/api/v1/analyst-views") return json(analystViews);
    if (path === "/api/v1/archive/index") return json(INDEX);
    if (path === "/api/v1/archive/2026-10-15") return json(archiveFor("2026-10-15"));
    if (path === "/api/v1/archive/2026-10-13") return json(archiveFor("2026-10-13"));
    if (path.startsWith("/api/v1/archive/")) return json({ detail: { message: "2026-10-14 저장 화면이 없습니다", nearest: { before: ["2026-10-13"], after: ["2026-10-15"] } } }, 404);
    return json({ detail: "not mocked" }, 404);
  }));
}

const network = (p: string) => calls.filter((u) => u.split("?")[0] === p).length;

async function openArchive(date: string) {
  fireEvent.click(await screen.findByTestId("archive-toggle"));
  const row = await screen.findByText(date, { selector: ".arc-row-d" });
  await act(async () => { fireEvent.click(row); });
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

describe("Daily archive mode", () => {
  it("LIVE mode keeps the 5s snapshot polling", async () => {
    render(<App />);
    await waitFor(() => expect(network("/api/v1/snapshot")).toBeGreaterThanOrEqual(1));
    const before = network("/api/v1/snapshot");
    await act(async () => { vi.advanceTimersByTime(5000); });
    await waitFor(() => expect(network("/api/v1/snapshot")).toBeGreaterThan(before));
    expect(screen.getByText("지금 업데이트")).toBeInTheDocument();
  });

  it("selecting a date renders the archived snapshot and never polls", async () => {
    render(<App />);
    await screen.findByText(/커버리지 100%/);
    await openArchive("2026-10-15");
    expect(screen.getByTestId("archive-toggle")).toHaveTextContent("ARCHIVE2026-10-15");
    expect(screen.getByTestId("archive-banner")).toHaveTextContent("PARTIAL");
    await screen.findByText(/커버리지 50% \(27\/54/); // 저장본의 당시 커버리지
    const snapshotCalls = network("/api/v1/snapshot");
    const invCalls = network("/api/v1/investment");
    await act(async () => { vi.advanceTimersByTime(120_000); });
    expect(network("/api/v1/snapshot")).toBe(snapshotCalls);
    expect(network("/api/v1/investment")).toBe(invCalls);
    expect(network("/api/v1/cockpit")).toBe(1); // LIVE 때의 한 번뿐 — 과거 화면은 저장본에서
    expect(location.hash).toBe("#2026-10-15");
  });

  it("hides the refresh button in archive mode and returns to LIVE", async () => {
    render(<App />);
    await openArchive("2026-10-13");
    expect(screen.queryByText("지금 업데이트")).toBeNull();
    const liveBefore = network("/api/v1/snapshot");
    await act(async () => { fireEvent.click(screen.getByTestId("archive-back-live")); });
    expect(screen.queryByTestId("archive-banner")).toBeNull();
    expect(await screen.findByText("지금 업데이트")).toBeInTheDocument();
    await waitFor(() => expect(network("/api/v1/snapshot")).toBeGreaterThan(liveBefore));
    await screen.findByText(/커버리지 100%/);
    expect(location.hash).toBe("");
  });

  it("does not fill a missing archived section with current data", async () => {
    render(<App />);
    await openArchive("2026-10-15");
    expect(screen.getByTestId("archive-missing-sections")).toHaveTextContent("AI 센티");
    const tabs = screen.getByTestId("scenario-tabs");
    await act(async () => { fireEvent.click(within(tabs).getByText(/^AI 센티$/)); });
    expect(await screen.findByTestId("not-archived")).toHaveTextContent("DATA UNAVAILABLE FOR THIS DATE");
    expect(network("/api/v1/ai-regime")).toBe(0);
    expect(() => resolveArchived(archiveFor("2026-10-15"), "/api/v1/ai-regime")).toThrow(/NOT ARCHIVED/);
    expect(() => resolveArchived(archiveFor("2026-10-15"), "/api/v1/unknown")).toThrow(/NOT ARCHIVED/);
  });

  it("a date without an archive shows the nearest saved dates instead of current data", async () => {
    render(<App />);
    fireEvent.click(await screen.findByTestId("archive-toggle"));
    const input = await screen.findByTestId("archive-date-input");
    await act(async () => { fireEvent.change(input, { target: { value: "2026-10-14" } }); });
    const box = await screen.findByTestId("archive-missing");
    expect(box).toHaveTextContent("2026-10-14 저장 화면이 없습니다.");
    expect(within(box).getByText("2026-10-13")).toBeInTheDocument();
    expect(within(box).getByText("2026-10-15")).toBeInTheDocument();
    expect(screen.queryByTestId("archive-banner")).toBeNull(); // 여전히 LIVE
  });

  it("puts the compact date control inside the topbar next to the data badge", async () => {
    render(<App />);
    const control = await screen.findByTestId("archive-control");
    const header = control.closest("header.topbar");
    expect(header).not.toBeNull();
    expect(within(header as HTMLElement).getByTestId("archive-toggle")).toHaveTextContent("LIVE");
  });
});
