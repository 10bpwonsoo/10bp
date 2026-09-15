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
  /** 1주 전(5봉 전) 시점의 z_1d. null 은 히스토리가 짧아 못 잰 것. */
  z_week_ago: number | null;
  /** 장기 백분위 0~100. percentile_observations 가 252 미만이면 '1년' 이 아니다. */
  percentile: number | null;
  percentile_observations: number;
}

/** 지배 축과 한 자산의 연동 — 60일 변화량 상관. 인과가 아니다. */
export interface AxisLink {
  instrument_id: string;
  label: string;
  corr: number;
  prior: number | null;
  z: number | null;
}

export interface DominantAxis {
  instrument_id: string;
  label: string;
  z: number;
  z_week_ago: number | null;
  arrow: string;
  window: number;
  positive: AxisLink[];
  negative: AxisLink[];
  note: string;
}

export interface RuleMatch {
  rule_id: string;
  expression: string;
  kind: "require" | "support";
  weight: number;
  passed: boolean;
  observed: number | null;
  evaluable: boolean;
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
  /** 5봉 전 시점에 같은 식으로 계산한 factor. */
  week_ago: number | null;
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
  /** 지배 축. null 은 축 후보가 조용했거나 상관이 없는 것. */
  dominant_axis: DominantAxis | null;
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
  // null 은 '측정되지 않음'. 0 은 '측정했고 중립'. 화면에서도 구분해야 한다.
  news_sentiment: number | null;
  news_volume: number | null;
  news_momentum: number | null;
  price_momentum: number | null;
  flow_momentum: number | null;
  volatility: number | null;
  cross_asset_confirmation: "HIGH" | "MEDIUM" | "LOW" | "CONFLICT";
  confirmation_score: number | null;
  confidence: number;
  confidence_breakdown: ScoreBreakdown | null;
  last_change: number;
  last_change_window: string;
  /** 약 1주 전 저장 스냅샷의 테마 점수. 저장이 없으면 null — 0 이 아니다. */
  week_ago_score: number | null;
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

export type DivergenceType =
  | "NEWS_VS_PRICE"
  | "NEWS_VS_FLOW"
  | "PRICE_VS_FLOW"
  | "THEME_VS_ASSET"
  | "RISK_VS_VOL"
  | "OIL_VS_INFLATION_EXP"
  | "BREADTH_VS_INDEX"
  | "CORRELATION_REGIME";

export interface Divergence {
  id: string;
  type: DivergenceType;
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

export type AlertType =
  | "THEME_SENTIMENT_SPIKE"
  | "NEWS_VOLUME_SPIKE"
  | "PRICE_ZSCORE_SPIKE"
  | "FLOW_REVERSAL"
  | "VOL_SPIKE"
  | "DIVERGENCE_OPENED"
  | "STATE_CHANGE"
  | "DATA_QUALITY";

export interface Alert {
  id: string;
  as_of: string;
  type: AlertType;
  severity: number;
  severity_band: SeverityBand;
  subject: string;
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

export type NodeType = "EVENT" | "THEME" | "MACRO_FACTOR" | "ASSET" | "SECTOR";

export type Reaction = "confirmed" | "mismatch" | "muted" | "unknown";

export interface RelationshipNode {
  id: string;
  type: NodeType;
  label: string;
  ref_id: string | null;
  /** 뿌리에서 몇 단계 떨어졌는가. 열 배치의 기준이다. */
  hop: number;
  /** 대표 경로의 관계 부호 곱. 0 은 뿌리이거나 판정 불가 */
  expected_sign: -1 | 0 | 1;
  /** 다른 경로가 반대 부호를 준다. 이때는 일치/불일치를 말하지 않는다. */
  sign_conflict: boolean;
  via_edge_id: string | null;
  /** 대표 경로의 가장 약한 고리. 낮으면 예상 부호 자체가 약한 주장이다. */
  path_strength: number | null;
  observed_z: number | null;
  observed_display: string | null;
  reaction: Reaction;
}

export interface RelationshipEdge {
  id: string;
  source_id: string;
  target_id: string;
  direction: "positive" | "negative" | "ambiguous";
  strength: number;
  confidence: number;
  lag: "immediate" | "hours" | "days" | "weeks";
  reason: string;
  origin: "predefined" | "llm_proposed" | "statistical";
  status: "active" | "candidate" | "rejected";
  evidence: string[];
  created_at: string;
  verified_by: string | null;
  /** 실측 상관 대조에 쓴 대표 자산 쌍. 예 "US10Y↔SPX". null 은 대조 못 함. */
  corr_pair: string | null;
  observed_corr: number | null;
  observed_corr_prior: number | null;
  corr_observations: number;
  corr_check: "confirmed" | "weakened" | "reversed" | "unknown";
}

export interface ImpactMap {
  as_of: string;
  root_event_id: string | null;
  nodes: RelationshipNode[];
  edges: RelationshipEdge[];
  max_depth: number;
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
  /** 1주 전(5봉 전) 시점의 z. */
  z_week_ago: number | null;
  /** 장기 백분위 0~100 와 그 계산에 쓰인 봉 수. */
  percentile: number | null;
  percentile_observations: number;
  change_3m: number | null;
  change_3m_display: string;
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
  /** 뉴스를 누가 판단했는가. none 룰 태깅만 / manual Claude 수기 / api 자동. */
  news_judgment: "none" | "manual" | "api";
  news_judgment_note: string;
  engine_timings_ms: Record<string, number>;
  warnings: string[];
}

export interface NewsEventLite {
  id: string;
  event: string;
  event_type: string;
  themes: string[];
  theme_sentiment: Record<string, number>;
  /** 테마 방향. 감성과 다른 축이다 — 호재/악재가 아니라 오르냐 내리냐. */
  theme_direction: Record<string, Direction>;
  sentiment: number;
  impact_score: number;
  reason: string;
  source: string;
  /** 원문 링크. 없으면 헤드라인만 보인다. */
  url: string | null;
  timestamp: string;
  extractor: "llm" | "rule" | "manual";
  confidence: number;
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

export type ThermometerBand =
  | "overheated"
  | "warm"
  | "neutral"
  | "cool"
  | "frozen"
  | "unknown";

/** 온도계 재료 한 줄. 같은 눈금 위의 현재값과 1주 전 값. */
export interface ThermoComponent {
  key: string;
  label: string;
  kind: "factor" | "news";
  value: number | null;
  week_ago: number | null;
  weight: number;
  sign: number;
  quality: string | null;
  note: string;
}

/**
 * 센티멘트 온도계. 바늘이 셋 — 가격·뉴스·종합. null 은 '측정하지 못함'.
 * 두 바늘의 거리(gap)가 곧 "내러티브와 가격이 맞는가" 다.
 */
export interface SentimentThermometer {
  as_of: string;
  composite: number | null;
  price: number | null;
  news: number | null;
  gap: number | null;
  gap_flag: "none" | "narrative_hot" | "narrative_cold";
  band: ThermometerBand;
  band_label: string;
  trend: Direction;
  trend_arrow: string;
  delta: number | null;
  confidence: number;
  composite_breakdown: ScoreBreakdown | null;
  price_breakdown: ScoreBreakdown | null;
  news_breakdown: ScoreBreakdown | null;
  confidence_breakdown: ScoreBreakdown | null;
  /** 1주 전. 가격은 시계열에서, 뉴스·종합은 저장된 스냅샷에서만 온다. */
  price_week_ago: number | null;
  news_week_ago: number | null;
  composite_week_ago: number | null;
  week_ago_source: "none" | "series" | "snapshot";
  week_ago_as_of: string | null;
  components: ThermoComponent[];
  news_events: number;
  llm_events: number;
  note: string;
}

export interface CalendarEvent {
  id: string;
  date: string;
  label: string;
  kind: string;
  region: string | null;
  weight: number;
  /** 1차 출처로 확인한 날짜인가. false 면 '(미확인)'. */
  verified: boolean;
  note: string;
  days_until: number | null;
}

/** 이벤트 창 판정. active 면 지속성 가중과 알림 임계가 조정돼 있다. */
export interface EventWindow {
  as_of: string;
  active: boolean;
  in_window: CalendarEvent[];
  upcoming: CalendarEvent[];
  window_days_before: number;
  window_days_after: number;
  persistence_scale: number;
  alert_threshold_scale: number;
  note: string;
}

export interface IntelligenceSnapshot {
  as_of: string;
  mode: DataMode;
  scenario: string | null;
  market_state: MarketState;
  thermometer: SentimentThermometer | null;
  calendar: EventWindow | null;
  themes: ThemeState[];
  divergences: Divergence[];
  alerts: Alert[];
  impact_maps: ImpactMap[];
  events: NewsEventLite[];
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

/** GET /api/v1/info — 스냅샷보다 먼저, 싸게 모드를 안다. */
export interface ApiInfo {
  status: string;
  version: string;
  mode: DataMode;
  scenario: string | null;
  llm_enabled: boolean;
  zscore_window: number;
}
