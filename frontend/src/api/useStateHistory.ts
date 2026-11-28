import { useEffect, useState } from "react";
import { ApiError, fetchStateHistory } from "./client";
import type { MarketStateHistory } from "./types";

/**
 * Market State 히스토리. 스냅샷의 as_of 가 바뀔 때만 다시 받는다 —
 * 서버도 같은 as_of 면 재생하지 않으므로 폴링할 이유가 없다.
 */
export function useStateHistory(scenario: string | undefined, asOf: string | null, enabled = true) {
  const [data, setData] = useState<MarketStateHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || !asOf) return;
    const c = new AbortController();
    let alive = true;
    fetchStateHistory(scenario, c.signal)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((err) => {
        if (!alive || (err as Error)?.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : "히스토리를 받지 못했습니다");
      });
    return () => { alive = false; c.abort(); };
  }, [scenario, asOf, enabled]);
  return { history: data, error };
}
