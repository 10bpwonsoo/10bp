import { ApiError } from "./client";

/**
 * Daily Full Dashboard Archive (2026-10-21) — 그날 저장된 화면 전체.
 *
 * ARCHIVE MODE 에서는 대시보드의 모든 API 호출이 네트워크 대신 이 저장본에서 답을 받는다(client.get · useInvestment).
 * 저장본에 없는 섹션은 지금 값으로 메우지 않고 404(NOT ARCHIVED)로 실패한다 — 화면 전체가 같은 날짜를 본다.
 * schema_version 이 바뀌어도 모르는 필드는 무시하고, 없는 필드는 null 로 본다.
 */
export interface DashboardArchive {
  schema_version: string;
  snapshot_date: string;
  generated_at: string;
  archive_status: "COMPLETE" | "PARTIAL" | string;
  errors?: Record<string, string>;
  meta?: {
    data_mode?: string | null;
    coverage?: number | null;
    source_asof?: string | null;
    created_by?: string | null;
    generated_at_basis?: string | null;
    timezone?: string | null;
    sections?: Record<string, string>;
    [k: string]: unknown;
  };
  [section: string]: unknown;
}

export interface ArchiveIndexRow {
  date: string;
  archive_status?: string | null;
  generated_at?: string | null;
  source_asof?: string | null;
  data_mode?: string | null;
  created_by?: string | null;
  missing?: string[];
}

/** 저장본 섹션 이름 — 화면 데이터를 이 이름으로 꺼낸다. */
export const ARCHIVE_SECTIONS = [
  "snapshot", "cockpit", "market_state_history", "ai_regime", "rates_regime", "oil_regime",
  "investment", "scenario_checks", "analyst_views", "daily_history", "news",
] as const;

export const SECTION_LABEL: Record<string, string> = {
  snapshot: "스냅샷", cockpit: "실시간 cockpit", market_state_history: "Market Regime History", ai_regime: "AI 센티",
  rates_regime: "금리", oil_regime: "유가", investment: "Investment", scenario_checks: "시나리오 탭",
  analyst_views: "Analyst View", daily_history: "Daily History", news: "뉴스 원문",
};

let active: DashboardArchive | null = null;

/** 지금 화면이 보고 있는 저장본. null 이면 LIVE. */
export function activeArchive(): DashboardArchive | null {
  return active;
}

export function setActiveArchive(a: DashboardArchive | null): void {
  active = a;
}

/** 저장본에 없는(또는 실패해 null 로 저장된) 섹션. */
export function missingSections(a: DashboardArchive): string[] {
  return ARCHIVE_SECTIONS.filter((s) => a[s] === null || a[s] === undefined || (a.errors && s in a.errors));
}

function notArchived(section: string): never {
  throw new ApiError(`DATA UNAVAILABLE FOR THIS DATE · ${SECTION_LABEL[section] ?? section} 은(는) 이 날짜 저장본에 없습니다 (NOT ARCHIVED)`, 404);
}

function section(a: DashboardArchive, name: string): unknown {
  const v = a[name];
  if (v === null || v === undefined) notArchived(name);
  return v;
}

/**
 * API 경로 → 저장본 섹션. 쿼리(scenario·refresh·days 등)는 무시한다 — 저장본은 그날 한 상태뿐이다.
 * 모르는 경로는 지금 서버로 보내지 않고 NOT ARCHIVED.
 */
export function resolveArchived(a: DashboardArchive, rawPath: string): unknown {
  const path = rawPath.split("?")[0] ?? rawPath;
  const query = rawPath.includes("?") ? new URLSearchParams(rawPath.slice(rawPath.indexOf("?") + 1)) : new URLSearchParams();
  const snap = section(a, "snapshot") as { mode?: string; scenario?: string | null };
  if (path === "/api/v1/info") return { status: "ok", version: `archive-${a.schema_version}`, mode: snap.mode ?? a.meta?.data_mode ?? "DELAYED", scenario: snap.scenario ?? null, llm_enabled: false, zscore_window: 60 };
  if (path === "/api/v1/scenarios") return [];
  if (path === "/api/v1/snapshot") return snap;
  if (path === "/api/v1/market-state/history") return section(a, "market_state_history");
  if (path.startsWith("/api/v1/history/")) {
    const tab = decodeURIComponent(path.slice("/api/v1/history/".length));
    const all = section(a, "daily_history") as Record<string, unknown>;
    if (!all[tab]) notArchived(`daily_history.${tab}`);
    return all[tab];
  }
  if (path === "/api/v1/scenario-check") return section(a, "scenario_checks");
  if (path === "/api/v1/oil-regime") return section(a, "oil_regime");
  if (path === "/api/v1/rates-regime") return section(a, "rates_regime");
  if (path === "/api/v1/ai-regime") return section(a, "ai_regime");
  if (path === "/api/v1/cockpit") return section(a, "cockpit");
  if (path === "/api/v1/analyst-views") return section(a, "analyst_views");
  if (path === "/api/v1/news") return section(a, "news");
  if (path === "/api/v1/investment") return section(a, "investment");
  if (path.startsWith("/api/v1/investment/stocks/")) {
    const inv = section(a, "investment") as { stocks?: Record<string, unknown> };
    const id = decodeURIComponent(path.slice("/api/v1/investment/stocks/".length));
    if (!inv.stocks?.[id]) notArchived(`investment.stocks.${id}`);
    return inv.stocks[id];
  }
  if (path === "/api/v1/investment/alternative") {
    const inv = section(a, "investment") as { alternative?: { group?: string }[] };
    const g = query.get("group");
    return (inv.alternative ?? []).filter((p) => !g || p.group === g);
  }
  return notArchived(path);
}
