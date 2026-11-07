import { useEffect, useState } from "react";
import { ApiError, fetchScenarioChecks } from "./client";
import type { ScenarioCheck } from "./types";

/** 시나리오 점검. 스냅샷 as_of 가 바뀔 때만 다시 받는다 — 서버도 같은 as_of 면 다시 계산하지 않는다. */
export function useScenarioChecks(scenario: string | undefined, asOf: string | null, enabled = true) {
  const [data, setData] = useState<ScenarioCheck[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || !asOf) return;
    const c = new AbortController();
    let alive = true;
    fetchScenarioChecks(scenario, c.signal)
      .then((d) => { if (alive) { setData(Array.isArray(d) ? d : []); setError(null); } })
      .catch((err) => {
        if (!alive || (err as Error)?.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : "시나리오 점검을 받지 못했습니다");
      });
    return () => { alive = false; c.abort(); };
  }, [scenario, asOf, enabled]);
  return { checks: data, error };
}
