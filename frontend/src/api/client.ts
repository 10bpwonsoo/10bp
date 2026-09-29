import type {
  MarketStateHistory, ApiInfo, IntelligenceSnapshot, RawNewsItem, ScenarioInfo, ScenarioCheck, OilRegime, RatesRegime } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { signal });
  } catch (cause) {
    if ((cause as Error)?.name === "AbortError") throw cause;
    throw new ApiError("백엔드에 연결할 수 없습니다", 0);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* 본문이 JSON 이 아니면 상태 문자열을 그대로 쓴다 */
    }
    throw new ApiError(detail, res.status);
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
