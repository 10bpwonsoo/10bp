import type {
  MarketStateHistory, ApiInfo, IntelligenceSnapshot, RawNewsItem, ScenarioInfo, ScenarioCheck, OilRegime, RatesRegime, AiRegime, Cockpit, AnalystViews,
  DailyHistory,
  HistoryTab,
} from "./types";
import { activeArchive, resolveArchived, type ArchiveIndexRow, type DashboardArchive } from "./archive";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** 서버가 detail 에 구조를 담아 보낸 경우(예: archive 404 의 nearest). */
    readonly detail: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  // ARCHIVE MODE — 네트워크로 가지 않는다. 저장본에 없으면 지금 값으로 메우지 않고 실패한다.
  const archived = activeArchive();
  if (archived) return resolveArchived(archived, path) as T;
  return getNetwork<T>(path, signal);
}

async function getNetwork<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { signal });
  } catch (cause) {
    if ((cause as Error)?.name === "AbortError") throw cause;
    throw new ApiError("백엔드에 연결할 수 없습니다", 0);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    let extra: unknown = null;
    try {
      const body = (await res.json()) as { detail?: string | { message?: string } };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail && typeof body.detail === "object") { extra = body.detail; if (body.detail.message) detail = body.detail.message; }
    } catch {
      /* 본문이 JSON 이 아니면 상태 문자열을 그대로 쓴다 */
    }
    throw new ApiError(detail, res.status, extra);
  }
  return (await res.json()) as T;
}

const qs = (scenario?: string, extra: Record<string, string> = {}) => {
  const params = new URLSearchParams(extra);
  if (scenario) params.set("scenario", scenario);
  const text = params.toString();
  return text ? `?${text}` : "";
};

export const fetchSnapshot = (
  scenario?: string,
  signal?: AbortSignal,
  opts: { refresh?: boolean } = {},
) =>
  get<IntelligenceSnapshot>(
    `/api/v1/snapshot${qs(scenario, opts.refresh ? { refresh: "true" } : {})}`,
    signal,
  );

/**
 * 정적 배포본이면 참. 배포본의 fetch 가로채기가 이 플래그를 세운다.
 * 서버가 없으므로 '지금 업데이트' 는 새 수집을 할 수 없고, 버튼이 그 사실을 말한다.
 */
export function staticBundle(): { collected: string } | null {
  const w = window as unknown as { __MP_STATIC__?: { collected: string } };
  return w.__MP_STATIC__ ?? null;
}

/**
 * 가벼운 상태 조회. 스냅샷을 받기 전에 **모드**를 알아야 한다 —
 * 시나리오 전환은 MOCK 에서만 의미가 있고, 실데이터 모드에서 시나리오를
 * 보내면 무엇을 보고 있는지 화면이 거짓말을 한다.
 */
export const fetchInfo = (signal?: AbortSignal) =>
  get<ApiInfo>("/api/v1/info", signal);

export const fetchScenarios = (signal?: AbortSignal) =>
  get<ScenarioInfo[]>("/api/v1/scenarios", signal);

export const fetchNews = (scenario?: string, signal?: AbortSignal) =>
  get<RawNewsItem[]>(`/api/v1/news${qs(scenario)}`, signal);

/** Market State 한 달 히스토리. 스냅샷과 별도 엔드포인트 — 재생 비용이 있어 서버가 as_of 별로 캐시한다. */
export const fetchStateHistory = (scenario?: string, signal?: AbortSignal, days?: number) => {
  const params = new URLSearchParams();
  if (scenario) params.set("scenario", scenario);
  if (days) params.set("days", String(days));
  const q = params.toString();
  return get<MarketStateHistory>(`/api/v1/market-state/history${q ? `?${q}` : ""}`, signal);
};

export const fetchScenarioChecks = (scenario?: string, signal?: AbortSignal) => {
  const q = scenario ? `?scenario=${encodeURIComponent(scenario)}` : "";
  return get<ScenarioCheck[]>(`/api/v1/scenario-check${q}`, signal);
};

export const fetchOilRegime = (scenario?: string, signal?: AbortSignal) => {
  const q = scenario ? `?scenario=${encodeURIComponent(scenario)}` : "";
  return get<OilRegime>(`/api/v1/oil-regime${q}`, signal);
};

export const fetchRatesRegime = (scenario?: string, signal?: AbortSignal) => {
  const q = scenario ? `?scenario=${encodeURIComponent(scenario)}` : "";
  return get<RatesRegime>(`/api/v1/rates-regime${q}`, signal);
};

export const fetchAiRegime = (scenario?: string, signal?: AbortSignal) => {
  const q = scenario ? `?scenario=${encodeURIComponent(scenario)}` : "";
  return get<AiRegime>(`/api/v1/ai-regime${q}`, signal);
};

/** Daily snapshot history — 탭 하나. 과거 날짜는 저장 snapshot 그대로(고정), 오늘만 LIVE. */
export const fetchDailyHistory = (tab: HistoryTab, scenario?: string, signal?: AbortSignal) => {
  const q = scenario ? `?scenario=${encodeURIComponent(scenario)}` : "";
  return get<DailyHistory>(`/api/v1/history/${tab}${q}`, signal);
};

export const fetchCockpit = (scenario?: string, signal?: AbortSignal) => {
  const q = scenario ? `?scenario=${encodeURIComponent(scenario)}` : "";
  return get<Cockpit>(`/api/v1/cockpit${q}`, signal);
};

/** STOCK RADAR 의 외부 ANALYST VIEW — radar 종목만. 실패해도 radar 는 그대로다. */
export const fetchAnalystViews = (scenario: string | undefined, ids: string[], signal?: AbortSignal): Promise<AnalystViews> => {
  const q = new URLSearchParams();
  if (scenario) q.set("scenario", scenario);
  if (ids.length) q.set("ids", ids.join(","));
  return get<AnalystViews>(`/api/v1/analyst-views?${q.toString()}`, signal);
};

/* ── Daily Full Dashboard Archive (2026-10-21) — 저장본 자체는 늘 네트워크(정적 배포본은 가로채기)에서 받는다 ── */
export const fetchArchiveIndex = (signal?: AbortSignal) => getNetwork<ArchiveIndexRow[]>("/api/v1/archive/index", signal);

/** 그날 저장된 화면 전체. 없으면 ApiError(404) 의 detail.nearest 에 가장 가까운 저장일. */
export const fetchArchive = (date: string, signal?: AbortSignal) => getNetwork<DashboardArchive>(`/api/v1/archive/${encodeURIComponent(date)}`, signal);
