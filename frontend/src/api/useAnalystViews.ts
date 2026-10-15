import { useEffect, useState } from "react";
import { fetchAnalystViews } from "./client";
import type { AnalystViews } from "./types";

/** STOCK RADAR 의 ANALYST VIEW — radar 종목만, 비동기. 실패하면 이 층만 비고 radar 는 그대로다. pending 이 있으면 잠시 뒤 한 번 더 받는다. */
export function useAnalystViews(scenario: string | undefined, ids: string[], enabled = true) {
  const [data, setData] = useState<AnalystViews | null>(null);
  const key = ids.join(",");
  useEffect(() => {
    if (!enabled || !key) { setData(null); return; }
    const c = new AbortController();
    let alive = true; let timer: ReturnType<typeof setTimeout> | null = null;
    const load = (retries: number) => {
      fetchAnalystViews(scenario, key.split(","), c.signal)
        .then((d) => { if (!alive) return; setData(d); if (d.pending.length && retries > 0) timer = setTimeout(() => load(retries - 1), 20000); })
        .catch(() => { if (alive) setData(null); });
    };
    load(3);
    return () => { alive = false; c.abort(); if (timer) clearTimeout(timer); };
  }, [scenario, key, enabled]);
  return data;
}
