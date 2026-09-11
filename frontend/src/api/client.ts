import type { IntelligenceSnapshot, RawNewsItem, ScenarioInfo } from "./types";

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

const qs = (scenario?: string) =>
  scenario ? `?scenario=${encodeURIComponent(scenario)}` : "";

export const fetchSnapshot = (scenario?: string, signal?: AbortSignal) =>
  get<IntelligenceSnapshot>(`/api/v1/snapshot${qs(scenario)}`, signal);

export const fetchScenarios = (signal?: AbortSignal) =>
  get<ScenarioInfo[]>("/api/v1/scenarios", signal);

export const fetchNews = (scenario?: string, signal?: AbortSignal) =>
  get<RawNewsItem[]>(`/api/v1/news${qs(scenario)}`, signal);
