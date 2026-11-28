import { useEffect, useState } from "react";
import { ApiError, fetchAiRegime } from "./client";
import type { AiRegime } from "./types";

/** AI Trade Intelligence. AI 탭이 열려 있고 스냅샷 as_of 가 바뀔 때만 받는다 (바스켓 계열 수집이 붙어 있어 다른 판별보다 느리다). */
export function useAiRegime(scenario: string | undefined, asOf: string | null, enabled = true) {
  const [data, setData] = useState<AiRegime | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || !asOf) return;
    const c = new AbortController();
    let alive = true;
    fetchAiRegime(scenario, c.signal)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((err) => {
        if (!alive || (err as Error)?.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : "AI 트레이드 판별을 받지 못했습니다");
      });
    return () => { alive = false; c.abort(); };
  }, [scenario, asOf, enabled]);
  return { regime: data, error };
}
