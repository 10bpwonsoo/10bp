/**
 * Investment Intelligence 타입 (2026-09-16 신설). marketpulse/models/intelligence.py 와 수기 동기화.
 * 기존 types.ts 는 손대지 않는다.
 */
import type { DataMode, Direction, ScoreBreakdown } from "./types";

export type SourceType = "OFFICIAL" | "EXCHANGE" | "MARKET_DATA" | "RESEARCH" | "NEWS" | "ALTERNATIVE" | "UNKNOWN";
export type Confidence = "HIGH" | "MEDIUM" | "LOW";
export type CauseKind = "CONFIRMED_DATA" | "CONFIRMED_NEWS" | "ANALYST_VIEW" | "MARKET_INFERENCE" | "CLAUDE_INTERPRETATION" | "UNKNOWN";
export type Quality = "OK" | "STALE" | "PARTIAL" | "MISSING";
export type Agreement = "confirmed" | "muted" | "mismatch" | "unknown";

export interface StockMeta {
  id: string; name: string; symbol: string; market: string; sector: string; industry: string;
  peers: string[]; drivers: string[]; themes: string[]; mock_base: number; mock_vol: number;
}
export interface FundamentalExposure { driver_id: string; kind: "revenue" | "cost" | "demand" | "financial"; direction: -1 | 1; importance: "high" | "medium" | "low"; rationale: string }
export interface ExposureWindow { window: number; beta: number | null; corr: number | null; observations: number }
export interface ExposureRow { driver_id: string; driver_label: string; windows: ExposureWindow[]; beta: number | null; corr: number | null; fundamental: FundamentalExposure | null; sign_agreement: boolean | null; note: string }
export interface StockExposure { stock_id: string; rows: ExposureRow[]; primary_window: number }
export interface StockImpact {
  stock_id: string; stock_name: string; driver_id: string; driver_label: string; shock_z: number; exposure: number;
  stat_confidence: number; fund_relevance: number; current_relevance: number; score: number; direction: Direction;
  sign_conflict: boolean; breakdown: ScoreBreakdown; rationale: string;
}
export interface DriverCard {
  instrument_id: string; label: string; value: number; unit: string; change_1d_display: string; change_1w: number | null;
  change_3m: number | null; z: number; percentile: number | null; percentile_observations: number; affected_sectors: string[];
  top_stocks: StockImpact[]; source: string; freshness_sec: number; stale: boolean; note: string;
}
export interface AltDataPoint {
  id: string; label: string; group: string; value: number | null; unit: string; change_1d: number | null; change_1w: number | null;
  change_1m: number | null; change_3m: number | null; z: number | null; percentile: number | null; percentile_observations: number;
  quality: Quality; stale: boolean; rollover_suspect: boolean; source: string | null; source_type: SourceType; proxy_for: string | null;
  why: string; affected: string[]; affected_names: string[]; as_of: string | null; note: string;
}
export interface Evidence { key: string; label: string; value: number | null; display: string; source: string }
export interface CauseCandidate { kind: CauseKind; confidence: Confidence; text: string; evidence: Evidence[]; weight: number }
export interface StockExplanation {
  stock_id: string; stock_name: string; as_of: string; return_1d: number | null; return_z: number | null; volume_z: number | null;
  market_return_1d: number | null; sector_return_1d: number | null; relative_return_1d: number | null; causes: CauseCandidate[]; unexplained: boolean; summary: string;
}
export type AnomalyLabel = "NONE" | "UNEXPLAINED_ACTIVITY" | "VOLUME_SPIKE" | "RELATIVE_MOVE" | "RETURN_SPIKE" | "NEWS_DRIVEN_MOVE";
export interface StockAnomaly {
  stock_id: string; stock_name: string; as_of: string; return_z: number | null; volume_z: number | null; relative_z: number | null;
  news_events: number; flags: string[]; label: AnomalyLabel; severity: number; note: string; missing: string[];
}
export interface DivergenceSide { name: string; value: number; display: string }
export interface StockDivergence {
  id: string; kind: string; stock_id: string; stock_name: string; as_of: string; left: DivergenceSide; right: DivergenceSide;
  severity: number; duration_periods: number; first_detected_at: string; explanation: string;
}
export interface AnalystSnapshot {
  stock_id: string; stock_name: string; as_of: string | null; rating: string | null; rating_change: string | null; target_price: number | null;
  tp_change_1w: number | null; tp_change_1m: number | null; tp_change_3m: number | null; eps_fy1: number | null;
  eps_revision_1w: number | null; eps_revision_1m: number | null; eps_revision_3m: number | null; brokers: number; price_change_1m: number | null;
  quadrant: "PRICE_UP_EPS_UP" | "PRICE_DOWN_EPS_UP" | "PRICE_UP_EPS_DOWN" | "PRICE_DOWN_EPS_DOWN" | "UNKNOWN";
  source: string | null; source_type: SourceType; available: boolean; note: string;
}
export interface LeadLag { lead_id: string; lag_id: string; label: string; best_lag_days: number | null; corr_at_best: number | null; corr_at_zero: number | null; observations: number; verdict: "tends_to_lead" | "coincident" | "no_relationship" | "insufficient"; note: string }
export interface StockRow { stock_id: string; name: string; sector: string; price: number | null; change_1d: number | null; change_1w: number | null; change_1m: number | null; z: number | null; volume_z: number | null; relative_z: number | null; percentile: number | null; stale: boolean; source: string | null }
export interface SemiconductorIntelligence { memory: AltDataPoint[]; peers: AltDataPoint[]; korea: StockRow[]; peer_direction: number | null; korea_direction: number | null; memory_direction: number | null; eps_direction: number | null; interpretation: string; missing: string[] }
export interface CommodityStockLink { stock_id: string; stock_name: string; kind: "revenue" | "cost" | "demand" | "financial"; direction: -1 | 1; importance: "high" | "medium" | "low"; rationale: string; stat_corr: number | null; price_reaction_z: number | null; expected_effect: Direction; agreement: Agreement }
export interface CommodityImpactRow { commodity_id: string; label: string; z: number; change_1d_display: string; change_1w: number | null; industries: string[]; links: CommodityStockLink[]; rollover_suspect: boolean; note: string }
export interface ThemeStockRow { theme_id: string; theme_name: string; theme_score: number; news_sentiment: number | null; stocks: StockRow[]; agreement: Agreement }
export interface CommentarySections { fact: string[]; news: string[]; analyst: string[]; interpretation: string[]; unknown: string[] }
export interface Commentary { kind: "market" | "stock" | "alternative" | "analyst"; entity: string; date: string; as_of: string; created_at: string; source_mode: "manual" | "api" | "none"; confidence: Confidence; sections: CommentarySections; evidence: Evidence[]; what_next: string[]; stale: boolean }
export interface StockIntelligence {
  meta: StockMeta; feature: unknown; row: StockRow; headline_what: string; headline_why: string; headline_changed: string; headline_next: string;
  exposure: StockExposure | null; impacts: StockImpact[]; explanation: StockExplanation | null; anomaly: StockAnomaly | null;
  divergences: StockDivergence[]; analyst: AnalystSnapshot | null; peers: AltDataPoint[]; alternative: AltDataPoint[];
  theme_scores: Record<string, number>; lead_lag: LeadLag[]; commentary: Commentary | null; missing: string[];
}
export type Badge = "NEW_EVENT" | "FLOW_INFLECTION" | "EPS_REVISION" | "ANALYST_CHANGE" | "ALTERNATIVE_DATA_SIGNAL" | "COMMODITY_IMPACT" | "UNUSUAL_MOVE" | "THEME_STRENGTHENING" | "THEME_WEAKENING";
export interface WatchlistRow {
  stock_id: string; name: string; sector: string; price: number | null; change_1d: number | null; change_1w: number | null; volume_z: number | null; flow_z: number | null;
  theme: string | null; theme_score: number | null; macro_impact: number | null; macro_driver: string | null; alt_signal: string | null;
  eps_revision_1m: number | null; analyst_change: string | null; unusual: AnomalyLabel; badges: Badge[]; commentary_excerpt: string | null;
}
export interface IntelligenceHealth { mode: DataMode; stocks_expected: number; stocks_available: number; alt_expected: number; alt_available: number; stale: string[]; not_available: string[]; warnings: string[]; timings_ms: Record<string, number> }
export interface InvestmentIntelligence {
  as_of: string; mode: DataMode; scenario: string | null; drivers: DriverCard[]; alternative: AltDataPoint[]; market_stock_impact: StockImpact[];
  semiconductor: SemiconductorIntelligence; commodity_impact: CommodityImpactRow[]; unusual_movers: StockAnomaly[]; theme_stocks: ThemeStockRow[];
  analyst: AnalystSnapshot[]; fundamental_divergences: StockDivergence[]; stocks: Record<string, StockIntelligence>; watchlist: WatchlistRow[];
  lead_lag: LeadLag[]; commentary: Commentary[]; health: IntelligenceHealth; engine_versions: Record<string, string>;
}
