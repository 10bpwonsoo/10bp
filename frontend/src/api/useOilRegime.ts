import { useEffect, useState } from "react";
import { ApiError, fetchOilRegime } from "./client";
import type { OilRegime } from "./types";

/** 유가 시장 원인 판별. 유가 탭이 열려 있고 스냅샷 as_of 가 바뀔 때만 받는다. */
export function useOilRegime(scenario: string | undefined, asOf: string | null, enabled = true) {
  const [data, setData] = useState<OilRegime | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || !asOf) return;
    const c = new AbortController();
    let alive = true;
    fetchOilRegime(scenario, c.signal)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((err) => {
        if (!alive || (err as Error)?.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : "유가 원인 판별을 받지 못했습니다");
      });
    return () => { alive = false; c.abort(); };
  }, [scenario, asOf, enabled]);
  return { regime: data, error };
}
