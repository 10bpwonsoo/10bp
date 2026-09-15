import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchSnapshot } from "./client";
import type { IntelligenceSnapshot } from "./types";

/** 백엔드 TTL 캐시가 4초라 그보다 짧게 폴링해도 얻는 게 없다. */
const POLL_MS = 5000;

export interface SnapshotStore {
  snapshot: IntelligenceSnapshot | null;
  error: string | null;
  loading: boolean;
  lastUpdated: Date | null;
  refresh: () => void;
  /** 서버 캐시를 건너뛰고 지금 새로 수집·계산한다. 화면의 '지금 업데이트'. */
  refreshNow: () => Promise<void>;
  refreshing: boolean;
}

export function useSnapshot(scenario?: string, enabled = true): SnapshotStore {
  const [snapshot, setSnapshot] = useState<IntelligenceSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [tick, setTick] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  const [refreshing, setRefreshing] = useState(false);
  const refreshNow = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await fetchSnapshot(scenario, undefined, { refresh: true });
      if (!mounted.current) return;
      setSnapshot(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof ApiError ? err.message : "알 수 없는 오류가 발생했습니다");
    } finally {
      if (mounted.current) setRefreshing(false);
    }
  }, [scenario]);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let timer: number | undefined;

    const run = async () => {
      try {
        const data = await fetchSnapshot(scenario, controller.signal);
        if (!mounted.current) return;
        setSnapshot(data);
        setLastUpdated(new Date());
        setError(null);
      } catch (err) {
        if ((err as Error)?.name === "AbortError" || !mounted.current) return;
        // 직전 스냅샷은 화면에 남겨둔다. 데이터가 사라지는 것보다
        // 오래된 데이터임을 알리는 편이 낫다.
        setError(
          err instanceof ApiError ? err.message : "알 수 없는 오류가 발생했습니다",
        );
      } finally {
        if (mounted.current) setLoading(false);
      }
    };

    void run();
    timer = window.setInterval(run, POLL_MS);
    return () => {
      controller.abort();
      if (timer) window.clearInterval(timer);
    };
  }, [scenario, tick, enabled]);

  return { snapshot, error, loading, lastUpdated, refresh, refreshNow, refreshing };
}
