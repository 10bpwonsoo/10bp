import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./client";
import { activeArchive, resolveArchived } from "./archive";
import type { InvestmentIntelligence } from "./investment";

const BASE = import.meta.env.VITE_API_BASE ?? "";
/** 종목 계층은 일봉이라 자주 바뀌지 않는다. 기존 스냅샷(5초)보다 훨씬 느리게 폴링한다. */
const POLL_MS = 60_000;

async function fetchInvestment(scenario?: string, refresh = false, signal?: AbortSignal): Promise<InvestmentIntelligence> {
  const params = new URLSearchParams();
  if (scenario) params.set("scenario", scenario);
  if (refresh) params.set("refresh", "true");
  const q = params.toString();
  // ARCHIVE MODE — 저장본의 investment 만. 없으면 NOT ARCHIVED (지금 값으로 메우지 않는다)
  const archived = activeArchive();
  if (archived) return resolveArchived(archived, "/api/v1/investment") as InvestmentIntelligence;
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/v1/investment${q ? `?${q}` : ""}`, { signal });
  } catch (cause) {
    if ((cause as Error)?.name === "AbortError") throw cause;
    throw new ApiError("백엔드에 연결할 수 없습니다", 0);
  }
  if (!res.ok) throw new ApiError(`${res.status} ${res.statusText}`, res.status);
  return (await res.json()) as InvestmentIntelligence;
}

export function useInvestment(scenario?: string, enabled = true) {
  const [data, setData] = useState<InvestmentIntelligence | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const c = new AbortController();
    const run = async () => {
      try {
        const d = await fetchInvestment(scenario, false, c.signal);
        if (!mounted.current) return;
        setData(d); setError(null);
      } catch (err) {
        if ((err as Error)?.name === "AbortError" || !mounted.current) return;
        setError(err instanceof ApiError ? err.message : "알 수 없는 오류");
      } finally {
        if (mounted.current) setLoading(false);
      }
    };
    void run();
    // ARCHIVE MODE 는 한 번 읽고 끝 — 폴링하지 않는다
    const t = activeArchive() ? undefined : window.setInterval(run, POLL_MS);
    return () => { c.abort(); if (t) window.clearInterval(t); };
  }, [scenario, enabled]);

  const refreshNow = useCallback(async () => {
    setRefreshing(true);
    try {
      const d = await fetchInvestment(scenario, true);
      if (mounted.current) { setData(d); setError(null); }
    } catch (err) {
      if (mounted.current) setError(err instanceof ApiError ? err.message : "알 수 없는 오류");
    } finally {
      if (mounted.current) setRefreshing(false);
    }
  }, [scenario]);

  return { data, error, loading, refreshing, refreshNow };
}
