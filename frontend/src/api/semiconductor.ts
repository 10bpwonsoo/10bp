/**
 * 반도체 사이클 탭 (2026-10-23) — GET /api/v1/semiconductor-cycle. 다른 탭 타입·훅과 따로 둔다.
 * 숫자는 서버가 만들고 화면은 그리기만 한다. 없는 값은 null / "NO DATA" — 0 으로 그리지 않는다.
 */
import { useEffect, useState } from "react";
import { ApiError, fetchSemiconductorCycle } from "./client";
import type { DailyHistory } from "./types";

export type Num = number | null;

export interface SemiPoint { t: string; v: number }
/** 평일 Daily State 한 칸 — [날짜, 값, 'R'(그날 원천 관측) | 'C'(CARRIED_FORWARD), 그 값의 원천 관측일] */
export type SemiDaily = [string, number, "R" | "C", string];
export interface SemiCoverage { status: "GOOD" | "PARTIAL" | "UNAVAILABLE" | string; available_from: string | null; raw: number; max_gap?: number | null }
export interface SemiProduct {
  id: string; label: string; spec: string; family: "DDR5" | "DDR4" | "NAND" | string; tier: "main" | "ett" | string; selector: boolean; available: boolean;
  current: Num; updated_at: string | null; change_1d: Num; change_1w: Num; change_1m: Num; change_3m: Num; change_1y: Num;
  since_first: Num; since_first_from: string | null; observations: number; momentum: Num; momentum_basis: "WINDOWS" | "SINCE_FIRST" | "NONE" | string;
  momentum_state: string | null; history: SemiPoint[];
  // 2026-10-23 과거 DB — 없으면(옛 저장본) 화면은 RAW history 로 그린다
  daily?: SemiDaily[]; source_date?: string | null; current_origin?: "RAW" | "CARRIED_FORWARD" | null; change_6m?: Num; raw_obs_1y?: number; raw_obs_1m?: number;
  frequency?: "daily" | "weekly"; momentum_confidence?: "HIGH" | "MEDIUM" | "LOW"; freshness?: { days_since_source: number | null; state: string };
  ma20?: Num; ma60?: Num; coverage?: Record<string, SemiCoverage>; turning?: { spot_momentum: string | null; mom_1m_now?: Num; mom_1m_before?: Num };
  sources?: Record<string, number>;
}
export interface SemiPremiumPoint { t: string; spot: number; contract: number; anchor: string; premium: number; origin?: "RAW" | "CARRIED_FORWARD"; src?: string }
export interface SemiPremium {
  spot: string; spot_label: string; contract: string | null; contract_label?: string | null; comparability: "HIGH" | "LOW" | "NONE" | string; weight: number; note: string;
  available: boolean; reason?: string; current?: number; spot_price?: number; contract_equiv?: number; spot_date?: string; contract_anchor?: string; contract_anchor_label?: string;
  contract_age_days?: number | null; contract_stale?: boolean; change_1w_pp?: Num; change_1m_pp?: Num; change_since_first_pp?: Num; direction?: string;
  zscore?: Num; percentile_1y?: Num; observations?: number; zscore_min_obs?: number; state?: string | null; series?: SemiPremiumPoint[]; proxy?: boolean;
  z_status?: "OK" | "NOT ENOUGH HISTORY" | string; mean_1y?: Num; raw_premium_obs?: number; premium_history_months?: number; contract_months?: number;
  contract_published?: string | null; contract_source?: string | null; conversion?: string; z_cross?: string | null;
}
export interface SemiCoverageRow {
  id: string; label: string; frequency: string; spot_history_months: number; spot_from: string | null; contract_history_months: number | null; premium_history_months: number | null;
  premium_type: string; raw_obs: number; latest_update: string | null; days_since: number | null; windows: Record<string, string>; coverage: string; available_from: string | null;
  sources: Record<string, number>; reason: string | null;
}
export interface SemiChip { key: string; label: string; value: string }
export interface SemiComponent { key: string; label: string; score: Num; weight: number; tone: string }
export interface SemiRegime {
  state: string; label: string; composite: Num; confidence: number; coverage: number; components: SemiComponent[]; chips: SemiChip[]; note: string;
  has_core?: boolean; min_coverage?: number;
}
export interface SemiMarketRead {
  read: string; source: "llm" | "rule" | string; status: string; generator: string; reason: string; themes: string[]; themes_ko: string[]; data_caveat: string;
  rule_read: string; warnings: string[]; generated_at: string | null;
}
export interface SemiStage { stage: string; status: "CONFIRMED" | "PARTIAL" | "WATCH" | "NOT CONFIRMED" | "NO DATA" | string; evidence: string }
export interface SemiMapRow {
  id: string; label: string; tier: string; available: boolean; spot: Num; change_1w: Num; change_1m: Num; since_first: Num; since_first_from: string | null;
  premium: Num; premium_proxy: boolean; zscore: Num; momentum: Num; momentum_basis: string; strength: string;
}
export interface SemiNormalized { id: string; label: string; base_date: string; points: SemiPoint[]; last: number; coverage?: string | null }
export interface SemiExportProgress {
  scope: string; label: string; available: boolean; value: Num; yoy: Num; daily_avg_yoy?: Num; days?: Num; days_prev?: Num; source?: string | null; release_at?: string | null; note?: string;
}
export interface SemiExport {
  available: boolean; note?: string; unit?: string; month?: string; latest_scope?: string; latest_scope_label?: string; latest_yoy?: Num; latest_daily_avg_yoy?: Num;
  nowcast?: { mid: number; low: number; high: number; yoy_mid?: Num; yoy_low?: Num; yoy_high?: Num; daily_avg_yoy_mid?: Num } | null;
  previous?: { basis: string; mid: number; yoy_mid: Num } | null; revision_pp?: Num; prev_month?: string; prev_month_yoy?: Num; momentum?: string;
  drivers?: { key: string; label: string; value: string; note?: string }[]; price_vs_volume?: string; price_vs_volume_note?: string;
  ratios?: { period: string; ratio: number; derived?: boolean }[]; ratio_mid?: number; working_days?: Num; working_days_basis?: string;
  confidence?: number; confidence_label?: string; accuracy?: { rows: unknown[]; note: string }; method?: string; progress?: SemiExportProgress[];
  base?: { period: string; semis: number; semis_yoy: number; days: number } | null;
}
export interface SemiEquityRow {
  id: string; label: string; ret_1d: Num; ret_1w: Num; ret_1m: Num; rel_1m: Num; bench: string | null; arrow: string; confirmation: string; last: string | null;
}
export interface SemiEquity { stocks: SemiEquityRow[]; index: { id: string; label: string; ret_1d: Num; ret_1w: Num; ret_1m: Num }; status: string; read: string; score: Num }
export interface SemiStockImpact {
  id: string; label: string; memory_pricing: string; hbm: string; export: string; eps_revision: string; price_confirmation: string; overall: string; return_1m: Num;
}
export interface SemiNews {
  id: string; headline: string; published_at: string; categories: string[]; category: string; direction: string; sentiment: number; importance: number;
  why: string; transmission: string; products: string[]; stocks: string[]; source: string; url: string;
}
export interface SemiNext { title: string; current: string; trigger: string; confirmation: string; implication: string }
export interface SemiQuality {
  item: string; tier: string | null; source: string | null; frequency: string | null; last: string | null; status: "FRESH" | "STALE" | "UNAVAILABLE" | string;
  observations?: number; note?: string; accuracy_note?: string;
}
export interface SemiHbm {
  pricing: string; capacity: string; lead_time: string; supplier_commentary: string; note: string; transmission: SemiStage[];
  anchors: { id: string; label: string; available: boolean; value?: number; date?: string; period?: string; confidence?: string; source?: string; prev?: Num; prev_date?: string | null; change_pct?: Num }[];
}

export interface SemiconductorCycle {
  as_of: string; version: string; regime: SemiRegime; market_read: SemiMarketRead; memory_prices: SemiProduct[]; spot_premium: SemiPremium[];
  momentum: { products: Partial<SemiProduct>[] };
  breadth: { products_in_premium: [number, number]; expanding_premium: [number, number]; positive_momentum: [number, number]; state: string; note: string };
  normalized: Partial<Record<"1M" | "3M" | "6M" | "1Y", SemiNormalized[]>>; dram_map: SemiMapRow[]; nand_map: SemiMapRow[];
  contract: { rows: { id: string; label: string; avg: number; period: string; change_pct: number; age_days: number; stale: boolean }[]; trend: string; stale: boolean };
  memory_history: DailyHistory | null; spot_to_contract: { stages: SemiStage[] }; hbm_supply: SemiHbm; export_nowcast: SemiExport; price_to_export: { stages: SemiStage[] };
  fundamental_confirmation: { rows: { key: string; label: string; value: string; basis: string }[]; companies: { id: string; label: string; status: string; note: string }[]; state: string };
  equity_confirmation: SemiEquity; stock_impact: SemiStockImpact[]; news: SemiNews[]; what_matters_next: SemiNext[]; data_quality: SemiQuality[]; not_supported?: string[];
  coverage_table?: SemiCoverageRow[]; history_note?: string;
  turning?: { signal: string; tightening: string[]; softening: string[]; breadth_trend: string | null; note: string };
}

/** 탭이 열려 있고 스냅샷 as_of 가 바뀔 때만 받는다. 과거 날짜는 저장본(archive.semiconductor_cycle)에서만 — 없으면 NOT ARCHIVED. */
export function useSemiconductorCycle(scenario: string | undefined, asOf: string | null, enabled = true) {
  const [data, setData] = useState<SemiconductorCycle | null>(null);
  const [error, setError] = useState<{ message: string; status: number } | null>(null);
  useEffect(() => {
    if (!enabled || !asOf) return;
    const c = new AbortController();
    let alive = true;
    fetchSemiconductorCycle(scenario, c.signal)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((err) => {
        if (!alive || (err as Error)?.name === "AbortError") return;
        setError(err instanceof ApiError ? { message: err.message, status: err.status } : { message: "반도체 사이클을 받지 못했습니다", status: 0 });
      });
    return () => { alive = false; c.abort(); };
  }, [scenario, asOf, enabled]);
  return { cycle: data, error };
}
