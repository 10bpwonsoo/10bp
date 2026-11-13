import { useEffect, useState } from "react";
import { ApiError, fetchRatesRegime } from "./client";
import type { RatesRegime } from "./types";

/** 금리·물가 원인 판별. 물가 탭이 열려 있고 스냅샷 as_of 가 바뀔 때만 받는다. */
export function useRatesRegime(scenario: string | undefined, asOf: string | null, enabled = true) {
  const [data, setData] = useState<RatesRegime | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || !asOf) return;
    const c = new AbortController();
    let alive = true;
    fetchRatesRegime(scenario, c.signal)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((err) => {
        if (!alive || (err as Error)?.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : "금리·물가 원인 판별을 받지 못했습니다");
      });
    return () => { alive = false; c.abort(); };
  }, [scenario, asOf, enabled]);
  return { regime: data, error };
}
