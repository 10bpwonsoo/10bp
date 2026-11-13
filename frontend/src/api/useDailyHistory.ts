import { useEffect, useState } from "react";
import { ApiError, fetchDailyHistory } from "./client";
import type { DailyHistory, HistoryTab } from "./types";

/**
 * Daily snapshot history (2026-10-07). 스냅샷 as_of 가 바뀔 때만 다시 받는다 — 과거 날짜는 서버에 저장된 값이라 폴링할 이유가 없다.
 * 첫 요청은 서버가 빈 과거 날짜를 1회 채우느라(BACKFILLED) 몇 초 걸릴 수 있다.
 */
export function useDailyHistory(tab: HistoryTab, scenario: string | undefined, asOf: string | null, enabled = true) {
  const [data, setData] = useState<DailyHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || !asOf) return;
    const c = new AbortController();
    let alive = true;
    fetchDailyHistory(tab, scenario, c.signal)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((err) => {
        if (!alive || (err as Error)?.name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : "히스토리를 받지 못했습니다");
      });
    return () => { alive = false; c.abort(); };
  }, [tab, scenario, asOf, enabled]);
  return { history: data, error };
}
