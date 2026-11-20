import { useEffect, useState } from "react";
import { ApiError, fetchMarketOverview } from "./client";
import type { MarketOverview } from "./types";

/** MARKET OVERVIEW 종합. 탭이 열려 있고 스냅샷 as_of 가 바뀔 때만 받는다 — 서버도 판정 지문이 같으면 LLM 을 다시 부르지 않는다. */
export function useMarketOverview(scenario: string | undefined, asOf: string | null, enabled = true) {
  const [data, setData] = useState<MarketOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || !asOf) return;
    const c = new AbortController();
    let alive = true;
    fetchMarketOverview(scenario, c.signal)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((err) => {
        if (!alive || (err as Error)?.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : "MARKET OVERVIEW 종합을 받지 못했습니다");
      });
    return () => { alive = false; c.abort(); };
  }, [scenario, asOf, enabled]);
  return { overview: data, error };
}
