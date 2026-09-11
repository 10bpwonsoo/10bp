/**
 * 백엔드 pydantic 스키마의 TypeScript 대응.
 *
 * marketpulse/models/ 와 수기로 동기화한다. 자동 생성(openapi-typescript)은
 * P4 에서 도입한다 — 지금은 도구 하나를 늘리는 것보다 계약을 눈으로 읽을 수
 * 있게 두는 편이 낫다.
 */

export type DataMode = "LIVE" | "DELAYED" | "MOCK";
export type Direction = "up" | "down" | "flat";

export type StateLabel =
  | "RISK_ON"
  | "RISK_OFF"
  | "GROWTH_SHOCK"
  | "INFLATION_SHOCK"
  | "LIQUIDITY_STRESS"
  | "POLICY_DRIVEN"
  | "GEOPOLITICAL_RISK"
  | "NEUTRAL";

export interface ScoreContribution {
  key: string;
  raw_value: number | null;
  normalized: number;
  weight: number;
  contribution: number;
  note: string;
}

export interface ScoreBreakdown {
  value: number;
  method: string;
  contributions: ScoreContribution[];
  missing_inputs: string[];
  inputs_hash: string;
  computed_at: string;
}

export interface DriverItem {
  instrument_id: string;
  label: string;
  z: number;
  direction: Direction;
  arrow: string;
}

export interface RuleMatch {
  rule_id: string;
  expression: string;
  kind: "require" | "support";
  weight: number;
  passed: boolean;
  observed: number | null;
}

export interface StateHypothesis {
  label: StateLabel;
  score: number;
  matched_rules: RuleMatch[];
}

export interface FactorScore {
  factor: string;
  score: number;
  breakdown: ScoreBreakdown;
  data_quality: "OK" | "PARTIAL" | "INSUFFICIENT";
}

export interface ConfirmationResult {
  expected: Record<string, number>;
  confirmed: string[];
  unconfirmed: string[];
  conflicting: string[];
  score: number;
  verdict: "HIGH" | "MEDIUM" | "LOW";
  note: string;
}

export interface MarketState {
  as_of: string;
  primary_label: StateLabel;
  secondary_label: StateLabel | null;
  confidence: number;
  confidence_breakdown: ScoreBreakdown | null;
  factors: Record<string, FactorScore>;
  hypotheses: StateHypothesis[];
  main_drivers: DriverItem[];
  cross_asset_confirmation: ConfirmationResult;
  narrative: string | null;
  narrative_source: "llm" | "template" | "none";
}

export interface ThemeState {
  theme_id: string;
  name: string;
  as_of: string;
  theme_score: number;
  breakdown: ScoreBreakdown;
  news_sentiment: number;
  news_volume: number;
  news_momentum: number;
  price_momentum: number;
  flow_momentum: number;
  volatility: number;
  cross_asset_confirmation: "HIGH" | "MEDIUM" | "LOW" | "CONFLICT";
  confirmation_score: number;
  confidence: number;
  confidence_breakdown: ScoreBreakdown | null;
  last_change: number;
  last_change_window: string;
  supporting_events: string[];
  supporting_instruments: string[];
  data_quality: "OK" | "PARTIAL" | "INSUFFICIENT";
}

export type SeverityBand = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface DivergenceLeg {
  name: string;
  value: number;
  z: number | null;
  direction: Direction;
}

export interface Divergence {
  id: string;
  type: string;
  as_of: string;
  severity: number;
  severity_band: SeverityBand;
  duration_periods: number;
  first_detected_at: string;
  related_theme: string | null;
  related_assets: string[];
  legs: DivergenceLeg[];
  gap: number;
  rule_id: string;
  explanation: string;
  llm_commentary: string | null;
}

export interface AlertTrigger {
  rule_id: string;
  metric: string;
  current: number;
  baseline: number;
  delta: number;
  delta_pct: number | null;
  threshold: number;
  window: string;
}

export interface Alert {
  id: string;
  as_of: string;
  type: string;
  severity: number;
  severity_band: SeverityBand;
  title: string;
  message: string;
  trigger: AlertTrigger;
  related_theme: string | null;
  related_assets: string[];
  related_events: string[];
  dedupe_key: string;
  first_fired_at: string;
  last_fired_at: string;
  fire_count: number;
  state: "NEW" | "ONGOING" | "RESOLVED";
}

export interface MovingItem {
  key: string;
  label: string;
  kind: "instrument" | "theme";
  z: number | null;
  change: number | null;
  change_display: string;
  direction: Direction;
  arrow: string;
}

export interface DataHealth {
  mode: DataMode;
  coverage: number;
  expected_instruments: number;
  available_instruments: number;
  missing: string[];
  stale: string[];
  max_freshness_sec: number;
  news_items: number;
  llm_status: "disabled" | "ok" | "degraded" | "failed";
  engine_timings_ms: Record<string, number>;
  warnings: string[];
}

export interface RawNewsItem {
  id: string;
  title: string;
  body: string;
  url: string | null;
  publisher: string;
  published_at: string;
  language: string;
}

export interface IntelligenceSnapshot {
  as_of: string;
  mode: DataMode;
  scenario: string | null;
  market_state: MarketState;
  themes: ThemeState[];
  divergences: Divergence[];
  alerts: Alert[];
  impact_maps: unknown[];
  events: unknown[];
  whats_moving: MovingItem[];
  data_health: DataHealth;
  engine_versions: Record<string, string>;
}

export interface ScenarioInfo {
  name: string;
  title: string;
  description: string;
  is_active: boolean;
}
