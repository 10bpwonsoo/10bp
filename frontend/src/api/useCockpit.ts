import { useEffect, useState } from "react";
import { ApiError, fetchCockpit } from "./client";
import type { Cockpit } from "./types";

/** 실시간 메인 탭의 decision cockpit. 스냅샷 as_of 가 바뀔 때만 받는다. 실패하면 화면은 기존 대시보드로 떨어진다. */
export function useCockpit(scenario: string | undefined, asOf: string | null, enabled = true) {
  const [data, setData] = useState<Cockpit | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || !asOf) return;
    const c = new AbortController();
    let alive = true;
    fetchCockpit(scenario, c.signal)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((err) => {
        if (!alive || (err as Error)?.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : "메인 화면 집계를 받지 못했습니다");
      });
    return () => { alive = false; c.abort(); };
  }, [scenario, asOf, enabled]);
  return { cockpit: data, error };
}
