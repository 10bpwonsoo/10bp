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
  /** 가장 오래된 재료의 나이를 거래일(평일)로 센 값. 주말 제외, 휴장일 미반영이라 상한. 옛 캡처에는 없다 */
  max_freshness_trading_days?: number;
  oldest_instruments?: string[];
  freshness_note?: string;
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

// ── Market State 히스토리 (2026-09-23) ─────────────────────────────
export interface StateHistoryPoint {
  date: string;
  as_of: string;
  label: StateLabel;
  secondary_label: StateLabel | null;
  confidence: number;
  /** 온도계와 같은 식의 세 온도. null 은 못 잰 것 — 뉴스는 그 시점까지 캡처된 기사가 있어야 나온다 */
  price_temperature: number | null;
  news_temperature: number | null;
  composite: number | null;
  news_events: number;
  thermo_confidence: number;
  /** 온도계 재료 스트립과 같은 항목. null 은 결측 */
  components: Record<string, number | null>;
  /** 온도계 밴드(공포·탐욕): frozen | cool | neutral | warm | overheated | unknown */
  band: string;
  band_label: string;
  coverage: number;
  factors: Record<string, number>;
  hypotheses: Record<string, number>;
  drivers: string[];
}
export interface BandSegment { band: string; band_label: string; start: string; end: string; days: number; mean_composite: number | null }
export interface StateSegment { label: StateLabel; start: string; end: string; days: number; mean_confidence: number }
export interface MarketStateHistory {
  as_of: string;
  days_requested: number;
  points: StateHistoryPoint[];
  segments: StateSegment[];
  changes: number;
  days_by_label: Record<string, number>;
  band_segments: BandSegment[];
  days_by_band: Record<string, number>;
  band_labels: Record<string, string>;
  band_changes: number;
  current_band_streak: number;
  previous_band: string | null;
  current_streak: number;
  previous_label: StateLabel | null;
  confidence_first_half: number | null;
  confidence_second_half: number | null;
  temperature_first_half: number | null;
  temperature_second_half: number | null;
  component_labels: Record<string, string>;
  /** 기간 내내 결측이라 표에서 뺀 재료 (키 → 라벨) */
  excluded_components: Record<string, string>;
  summary: string;
  /** 같은 요약을 공포·탐욕(온도 밴드) 기준으로 */
  band_summary: string;
  note: string;
}

/** 시나리오 점검 — 모의 시나리오의 충격 서명을 실데이터에 대어 본 결과 (모의 탭을 실데이터로 바꾼 것) */
export type ScenarioRowStatus = "agree" | "weak" | "oppose" | "quiet_ok" | "quiet_broken" | "missing";
export interface ScenarioCheckRow {
  instrument_id: string;
  label: string;
  expected_z: number;
  actual_z_1d: number | null;
  actual_z_5d: number | null;
  used_z: number | null;
  used_window: number | null;
  ratio: number;
  weight: number;
  status: ScenarioRowStatus;
  layer: "market" | "alternative" | "stock" | "theme";
}
export interface ScenarioThemeRef { theme_id: string; name: string; theme_score: number; news_sentiment: number | null }
export interface ScenarioCheck {
  name: string;
  title: string;
  description: string;
  as_of: string;
  label: StateLabel | null;
  /** 탭이 앞세우는 판정 — 설정(scenario_checks.yaml)에서 온다 */
  focus: "rule" | "oil_regime" | "rates_regime" | "ai_regime" | "ai_regime_full" | "fear_greed" | "semiconductor" | "calm";
  factor: string | null;
  commodities: string[];
  match_score: number;
  match_label: string;
  evaluated: number;
  agree: number;
  weak: number;
  oppose: number;
  quiet_ok: number;
  quiet_broken: number;
  missing: string[];
  rows: ScenarioCheckRow[];
  hypothesis_score: number | null;
  require_expression: string | null;
  require_passed: boolean | null;
  require_observed: number | null;
  current_label: StateLabel;
  current_confidence: number;
  themes: ScenarioThemeRef[];
  verdict: string;
  note: string;
}

/** 유가 시장 원인 판별 — 판정 룰이 아니라 증거 집계. 서버(oil_regime.yaml)가 만든다 */
export type DriverStatus = "CONFIRMED" | "UNCONFIRMED" | "CONTRADICTED";
export type ConfirmStatus = "confirms" | "contradicts" | "neutral" | "missing";
export interface OilEvidenceItem { id: string; label: string; kind: "price" | "news"; layer: "market" | "alternative" | "theme"; value: number | null; window: number | null; sign: number; weight: number; contribution: number; available: boolean; note: string }
export interface OilDriverScore { id: string; label: string; label_ko: string; score: number; strength: string; status: DriverStatus; status_reason: string; coverage: number; evidence: OilEvidenceItem[]; implication: string }
export interface OilMove { brent_z: number | null; wti_z: number | null; oil_z: number | null; direction: "up" | "down" | "flat" | "unknown"; suspect: boolean; note: string }
export interface OilConfirmationRow { key: string; label: string; instruments: string[]; values: Record<string, number | null>; expected_sign: number | null; status: ConfirmStatus; note: string }
export interface OilNarrativeRow { theme_id: string; name: string; news: number | null; price: number | null; sentence: string; divergence_severity: number | null }
export interface OilWatchItem { text: string; metric: string; current: string; condition: string; effect: string }
export interface OilRegime {
  as_of: string; oil_move: OilMove; drivers: OilDriverScore[]; dominant: string; runner_up: string | null; margin: number;
  signal_strength: number; signal_strength_label: string; regime_label: string; headline: string; implication: string;
  confirmations: OilConfirmationRow[]; narrative: OilNarrativeRow[]; watch: OilWatchItem[]; note: string;
}

/** 금리·물가 원인 판별(Inflation & Rates Intelligence) — 판정 룰이 아니라 증거 집계. 서버(rates_regime.yaml)가 만든다 */
export type RatesConfirmStatus = "CONFIRMED" | "MIXED" | "NOT_CONFIRMED" | "MISSING";
export interface RatesEvidenceItem { id: string; label: string; kind: "price" | "news"; layer: "market" | "alternative" | "theme"; value: number | null; window: number | null; sign: number; weight: number; contribution: number; available: boolean; note: string }
export interface RatesDriverScore { id: string; label: string; label_ko: string; headline: string; score: number; strength: string; status: DriverStatus; status_reason: string; coverage: number; evidence: RatesEvidenceItem[]; implication: string }
export interface RateMove { instrument: string; z: number | null; window: number | null; direction: "up" | "down" | "flat" | "unknown"; change_5d_bp: number | null; level: number | null }
export interface InflationComponent { key: string; label: string; label_ko: string; score: number | null; status: "up" | "down" | "flat" | "missing"; coverage: number; evidence: RatesEvidenceItem[]; note: string }
export interface TenorPoint { id: string; label: string; level: number | null; z_1d: number | null; z_5d: number | null; z: number | null; change_5d_bp: number | null }
export interface CurveView { tenors: TenorPoint[]; spread_z: number | null; shape: "bear_steepening" | "bear_flattening" | "bull_steepening" | "bull_flattening" | "parallel_up" | "parallel_down" | "flat" | "unknown"; lead: "front" | "long" | "parallel" | "none"; sentence: string }
export interface YieldDecomposition { tenor: string; window_days: number; nominal_bp: number | null; breakeven_bp: number | null; real_implied_bp: number | null; real_measured_bp: number | null; dominant: "real" | "breakeven" | "mixed" | "unknown"; sentence: string; missing: string[] }
export interface RatesConfirmationRow { key: string; label: string; instruments: string[]; values: Record<string, number | null>; expected_sign: number | null; status: RatesConfirmStatus; note: string }
export interface KeyDivergence { key: string; label: string; why: string; severity: number; values: Record<string, number | null> }
export interface ImplicationRow { key: string; label: string; pressure: -1 | 0 | 1 | 2 }
export interface MarketImplication { driver: string; why: string; rows: ImplicationRow[] }
export interface TriggerItem { text: string; metric: string; current: string; condition: string; met: boolean; measurable: boolean }
export interface RatesRegime {
  as_of: string; rate_move: RateMove; drivers: RatesDriverScore[]; dominant: string; runner_up: string | null; margin: number;
  signal_strength: number; signal_strength_label: string; inflation_status: DriverStatus; regime_label: string; headline: string; implication: string;
  inflation_components: InflationComponent[]; curve: CurveView; decomposition: YieldDecomposition[]; confirmations: RatesConfirmationRow[];
  divergences: KeyDivergence[]; market_implication: MarketImplication; triggers: TriggerItem[]; release: TriggerItem[]; note: string;
}

/** AI Trade Intelligence — AI 트레이드 자체의 상태. 시장 온도가 아니다. 서버(ai_regime.yaml)가 만든다 */
export type AiRegimeKey = "ai_specific_derisking" | "macro_dragged" | "leadership_narrowing" | "narrative_ahead" | "confirmed_risk_on" | "confirmed_risk_off" | "price_resilience" | "mixed" | "unknown";
export interface AiEvidenceItem { id: string; label: string; kind: "price" | "news"; layer: "market" | "alternative" | "theme" | "basket" | "narrative"; value: number | null; window: number | null; sign: number; weight: number; contribution: number; available: boolean; note: string }
export interface AiDriverScore { id: string; label: string; label_ko: string; headline: string; score: number; strength: string; status: DriverStatus; status_reason: string; coverage: number; evidence: AiEvidenceItem[]; implication: string }
export interface AiMemberRow { id: string; name: string; group: string; available: boolean; last_date: string | null; ret_1d: number | null; ret_5d: number | null; ret_21d: number | null; rel_5d: number | null; above_ma5: boolean | null; above_ma20: boolean | null; advancing: boolean | null; note: string }
export interface AiGroupMomentum { key: string; label: string; label_ko: string; benchmark: string; in_basket: boolean; members: number; available: number; ret_1d: number | null; ret_5d: number | null; ret_21d: number | null; rel_1d: number | null; rel_5d: number | null; rel_21d: number | null; rel_z_1d: number | null; rel_z_5d: number | null; above_ma20_pct: number | null; down_1w: number; rank_1w: number | null; role: "leader" | "strong" | "neutral" | "lagging" | "laggard" | "unknown"; note: string }
export interface AiLeadership { groups: AiGroupMomentum[]; leader_1d: string | null; leader_1w: string | null; leader_1m: string | null; laggard_1w: string | null; rotation: "none" | "rotating" | "early" | "unknown"; sentence: string }
export interface AiVsMarket {
  members_used: number; members_total: number; last_date: string | null;
  basket_ret_1d: number | null; basket_ret_5d: number | null; basket_ret_21d: number | null; basket_z_1d: number | null; basket_z_5d: number | null; basket_z: number | null; basket_window: number | null;
  ndx_ret_1d: number | null; ndx_ret_5d: number | null; ndx_ret_21d: number | null; spx_ret_5d: number | null; spx_ret_21d: number | null;
  rel_ndx_1d: number | null; rel_ndx_5d: number | null; rel_ndx_21d: number | null; rel_ndx_z_1d: number | null; rel_ndx_z_5d: number | null; rel_ndx_z: number | null; rel_spx_5d: number | null; rel_spx_z_5d: number | null;
  abs_direction: "up" | "down" | "flat" | "unknown"; rel_verdict: "outperform" | "inline" | "underperform" | "unknown"; sentence: string;
}
export interface AiBreadth { members: number; above_ma5_pct: number | null; above_ma20_pct: number | null; advancing_pct: number | null; above_ma20_pct_1w_ago: number | null; change_1w_pts: number | null; trend: "widening" | "narrowing" | "stable" | "unknown"; narrowing_with_index_up: boolean; by_group: Record<string, number | null>; sentence: string }
export interface AiNarrativeDriver { key: string; label: string; label_ko: string; tone: number | null; count: number; samples: string[] }
export interface AiNarrativePrice { news_tone: number | null; news_count: number; news_momentum: number | null; price_z: number | null; price_window: number | null; quadrant: "confirmed" | "narrative_ahead" | "price_resilience" | "confirmed_risk_off" | "unclear"; label: string; sentence: string; drivers: AiNarrativeDriver[]; method: string }
export interface AiMacroRow { key: string; label: string; instrument: string; z: number | null; window: number | null; expected_sign: number; status: "EXPLAINS" | "DOES_NOT_EXPLAIN" | "NEUTRAL" | "MISSING"; note: string }
export interface AiMacroConfirmation { rows: AiMacroRow[]; explains: number; evaluated: number; verdict: "macro_driven" | "ai_specific" | "mixed" | "not_weak" | "unknown"; sentence: string }
export interface AiStressComponent { key: string; label: string; value: number | null; display: string; points: number; max_points: number; note: string }
export interface AiStress { level: "LOW" | "MODERATE" | "HIGH" | "UNKNOWN"; score: number; max_score: number; components: AiStressComponent[]; sentence: string }
export interface AiRegimeCheck { key: AiRegimeKey; label: string; passed: boolean; detail: string }
export interface AiGlobalContext { market_label: string; market_confidence: number; thermometer: number | null; band: string | null; note: string }
export type AiArrow = "↑↑" | "↑" | "→" | "↓" | "↓↓" | "?";
export interface AiStatusItem { key: string; label: string; value: string; tone: "good" | "warn" | "bad" | "muted"; detail: string }
export interface AiFundamentalConfirmation { level: "STRONG" | "PARTIAL" | "WEAK" | "UNCONFIRMED"; confirming: string[]; lagging: string[]; sentence: string }
export interface AiTransmissionStage { key: string; label: string; status: "ACCELERATING" | "POSITIVE" | "STRONG" | "IMPROVING" | "STABLE" | "MIXED" | "DETERIORATING" | "UNCONFIRMED"; score: number | null; evidence: string }
export interface AiTransmission { stages: AiTransmissionStage[]; sentence: string }
export interface AiSegmentRow { key: string; label: string; label_ko: string; exposure: string; members: number; available: number; ret_1d: number | null; ret_5d: number | null; ret_21d: number | null; rel_1d: number | null; rel_5d: number | null; rel_21d: number | null; rel_z_5d: number | null; above_ma20_pct: number | null; eps: number | null; eps_note: string; arrow_1w: AiArrow; arrow_rel: AiArrow; arrow_eps: AiArrow; rank_1w: number | null; role: "leading" | "neutral" | "lagging" | "unknown"; macro_score: number | null }
export interface AiValueChain { segments: AiSegmentRow[]; leadership: string[]; lagging: string[]; sentence: string }
export interface AiSemiArea { key: string; label: string; status: "STRONG" | "LEADING" | "IMPROVING" | "MIXED" | "NEUTRAL" | "WEAK" | "UNCONFIRMED"; price_momentum: AiArrow; relative_strength: AiArrow; breadth: AiArrow; news_evidence: AiArrow; eps: AiArrow; detail: string }
export interface AiMemoryRow { id: string; label: string; structural: boolean; value: number | null; unit: string; change_1d: number | null; change_1w: number | null; change_1m: number | null; z: number | null; observations: number; frequency: string; freshness_days: number | null; quality: string; status: "STRONG" | "IMPROVING" | "NEUTRAL" | "DETERIORATING" | "N/A"; note: string }
export interface AiSemiConfirmation { areas: AiSemiArea[]; memory: AiMemoryRow[]; sentence: string }
export interface AiStockAxis { key: "theme" | "fundamental" | "market" | "macro"; value: number | null; arrow: AiArrow; detail: string }
export interface AiStockImpactRow { id: string; name: string; segments: string[]; region: string; available: boolean; theme_exposure: string; axes: AiStockAxis[]; ai_demand: string; semiconductor: string; relative_strength: string; news_flow: string; eps_revision: string; rates_sensitivity: string; overall: "STRONG" | "CONFIRMED" | "MIXED" | "UNCONFIRMED" | "NEGATIVE PRESSURE" | "NO DATA"; confirmation: string; ret_5d: number | null; rel_5d: number | null; ret_21d: number | null; mentions: number; interpretation: string }
export interface AiRadarBucket { key: "strongest" | "improving" | "narrative_ahead" | "fundamentals_ahead" | "macro_pressure"; label: string; items: { id: string; name: string; reason: string }[] }
export interface AiNewsImpact { event: string; source: string; url: string | null; tone: number; drivers: string[]; primary: string[]; secondary: string[]; infrastructure: string[]; primary_stocks: string[]; secondary_stocks: string[]; infrastructure_stocks: string[]; confirmation: string }
export interface AiGapRow { key: string; label: string; market_pricing: number | null; fundamental: number | null; gap: number | null; note: string }
export interface AiMattersItem { key: string; text: string; status: "CONFIRMING" | "WATCH" | "DETERIORATING" | "N/A"; metric: string; current: string; detail: string }
export interface AiRegime {
  as_of: string; regime: AiRegimeKey; regime_label: string; regime_label_ko: string; headline: string; implication: string; checks: AiRegimeCheck[];
  ai_vs_market: AiVsMarket; drivers: AiDriverScore[]; dominant: string | null; runner_up: string | null; margin: number; signal_strength: number; signal_strength_label: string;
  leadership: AiLeadership; breadth: AiBreadth; narrative: AiNarrativePrice; macro: AiMacroConfirmation; stress: AiStress; triggers: TriggerItem[]; release: TriggerItem[];
  context: AiGlobalContext; members: AiMemberRow[]; missing: string[]; note: string;
  regime_subtitle: string; status_strip: AiStatusItem[]; fundamental_confirmation: AiFundamentalConfirmation; summary: string;
  transmission: AiTransmission; value_chain: AiValueChain; semi_confirmation: AiSemiConfirmation; stocks: AiStockImpactRow[]; radar: AiRadarBucket[];
  news_impact: AiNewsImpact[]; expectation_gap: AiGapRow[]; what_matters: AiMattersItem[];
}

/** 실시간 메인 탭 — decision cockpit. 서버(cockpit.yaml)가 기존 층의 값을 우선순위대로 고른 것 */
export type CkArrow = "↑↑" | "↑" | "→" | "↓" | "↓↓" | "?";
export interface CkKeyVariable { id: string; label: string; z: number; arrow: CkArrow; change_display: string }
export interface CkMarketNow { label: string; secondary: string | null; label_text: string; conviction: "HIGH" | "MEDIUM" | "LOW"; confidence: number; persistence_days: number; previous_label: string | null; change_text: string; key_variables: CkKeyVariable[]; sentence: string; interpretation: string; spark: { date: string; label: string }[]; last_update: string; coverage: string; latency: string }
export interface CkEvidence { id: string; label: string; z: number | null; display: string; context: boolean; available: boolean }
export interface CkDriver { key: string; label: string; label_ko: string; direction: "up" | "down"; arrow: CkArrow; strength: number; importance: number; coverage: number; confirmed_by_regime: boolean; persistent: boolean; news_tone: number | null; evidence: CkEvidence[]; why: string; source: "market" | "alternative" }
export interface CkCrossAssetRow { key: string; label: string; instrument: string; z: number | null; arrow: CkArrow; status: "CONFIRM" | "DIVERGE" | "HEADWIND" | "FLAT" | "NEUTRAL" | "MISSING"; note: string; instrument_label: string; group: "RISK" | "MACRO" | "COMMODITY"; meaning: string }
export interface CkKeyDivergence { title: string; meaning: string; severity: number; source: string; assets: string[]; phenomenon: string; why: string; reference: string[] }
export interface CkCrossAsset { rows: CkCrossAssetRow[]; confirm: number; evaluated: number; sentence: string; divergences: CkKeyDivergence[]; total_divergences: number; current_view: string; regime_short: string; confirm_text: string; market_read: string }
export interface CkConfirmRow { key: string; label: string; value: string; status: CkPathStatus; meaning: string }
export interface CkStreetView { institution: string; analyst: string; published_date: string; source_url: string; source_title: string; quote: string; summary: string; stance: "constructive" | "cautious" | "neutral" | "mixed"; key_variables: string[]; age_days: number; freshness: string; retrieved_by: "manual" | "llm_web" }
export interface CkKeyStock { id: string; name: string; role: string; note: string; in_radar: boolean; z: number | null }
export interface CkLeadershipDetail { why: string[]; confirmation: CkConfirmRow[]; system_view: string; driver: string; quality: string; quality_ko: string; quality_detail: string; risk: string; street: CkStreetView[]; street_read: string; key_stocks: CkKeyStock[]; watch: string[] }
export interface CkLeaderRow { key: string; label: string; kind: "theme" | "sector"; z_1d: number | null; rel_1w: number | null; breadth: number | null; arrow: CkArrow; instruments: number; available: number; system_view: string; detail: CkLeadershipDetail | null }
export interface CkThemePulseRow { theme_id: string; name: string; price: CkArrow; news: CkArrow; rel: CkArrow; theme_score: number; news_sentiment: number | null; price_momentum: number | null; rel_1w: number | null; why: string }
export interface CkLeadership { leaders: CkLeaderRow[]; laggards: CkLeaderRow[]; all_rows: CkLeaderRow[]; pulse: CkThemePulseRow[]; sentence: string; read: string }
export interface CkTransmissionStock { id: string; name: string; status: "CONFIRMED" | "UNCONFIRMED" | "CONTRADICTED" | "NO DATA"; z: number | null; change_1d: number | null; note: string; industry: string }
export interface CkTransmissionChain { driver_key: string; driver_label: string; arrow: CkArrow; mechanism: string; industries: string[]; stocks: CkTransmissionStock[]; confirmed: number; source: "driver" | "commodity"; evaluated: number; strength: "STRONG" | "PARTIAL" | "LIMITED" | "UNCONFIRMED"; strength_ko: string; read: string }
export type CkPathStatus = "CONFIRMED" | "PARTIAL" | "UNCONFIRMED" | "CONTRADICTED" | "DATA MISSING";
export interface CkPathCheck { label: string; id: string; kind: "instrument" | "segment" | "theme"; expect: number; observed: number | null; observed_text: string; status: CkPathStatus }
export interface CkPathStage { key: string; label: string; text: string[]; checks: CkPathCheck[]; status: CkPathStatus; explain: string }
export interface CkPathStock { id: string; name: string; expect: number; arrow: "↑" | "↓"; z: number | null; change_1d: number | null; status: CkPathStatus; segment: string; in_radar: boolean; note: string; expected_text: string; priority: number }
export interface CkPathTier { tier: "DIRECT" | "SECONDARY" | "TERTIARY"; stocks: CkPathStock[] }
export interface CkPathSummary { main_impact: string[]; stages_confirmed: number; stages_total: number; stages_text: string; most_exposed: string[]; exception: string[]; observed_read: string; confirm_read: string }
export interface CkIssuePath { trigger: CkPathStage; first_order: CkPathStage; assets: CkPathStage; themes: CkPathStage; tiers: CkPathTier[]; tier_max: number; expected: string; observed: string; conclusion: string; confirm: CkPathCheck[]; confirm_count: number; source: "config" | "ai_value_chain"; summary: CkPathSummary | null; tier_show: Record<string, number> }
export interface CkSystemAxis { key: string; label: string; arrow: CkArrow; detail: string }
export interface AnalystView { stock_id: string; stock_name: string; analyst: string; broker: string; published_date: string; source_url: string; source_title: string; summary: string; key_view: string; key_variables: string[]; stance: "constructive" | "cautious" | "neutral" | "mixed"; rating: string; target_change: string; retrieved_at: string; retrieved_by: "manual" | "llm_web"; age_days: number; freshness: string }
export interface AnalystViews { as_of: string; views: AnalystView[]; requested: string[]; pending: string[]; missing: string[]; provider: string; note: string }
export interface CkRadarStock { id: string; name: string; change_1d: number | null; tag: string; why: string; kind: "why" | "watch"; score: number; signals: string[]; system_axes: CkSystemAxis[]; related_issues: string[] }
export interface CkCatalyst { id: string; time: string; tag: string; headline: string; level: "CRITICAL" | "HIGH" | "MEDIUM"; kind: "news" | "alert"; impact: string; confidence: string; cluster_size: number; cluster_titles: string[]; why: string; related_assets: string[]; related_stocks: string[]; price_confirmation: string; url: string | null; source: string; importance: number }
export interface CkEarnings { rows: Record<string, string>[]; note: string }
export interface CkHorizon { key: "1D" | "5D" | "1M"; z: number | null; arrow: CkArrow }
export interface CkNextItem { text: string; status: "CONFIRMING" | "WATCH" | "REVERSING"; metric: string; current: string; driver_key: string; id: string; path: CkIssuePath | null; horizons: CkHorizon[]; horizon_read: string; why_next: string }
export interface CkUpcoming { date: string; label: string; days_until: number | null; verified: boolean }
export interface CkWatchLink { key: string; label: string }
export interface CkWatchRow { id: string; name: string; change_1d: number | null; watch: string; indicators: string[]; theme: string; why: string; key_drivers: string[]; trigger: string; reasons: string[]; priority: "HIGH" | "MEDIUM"; transmission: CkWatchLink[]; issues: CkWatchLink[]; commentary: string; eps_revision: number | null }
export interface CkDataStatus { line: string; warnings: string[]; coverage: number; available: number; expected: number; stale: number; max_lag_days: number; news_judgment: string }
export interface CkRegimeDay { date: string; raw_state: string; raw_secondary: string | null; dominant_regime: string; end_regime: string; display_regime: string; display_label: string; evidence_strength: number; dominant_driver: string; top_driver_1: string; top_driver_2: string; top_evidence: string[]; dominant_regime_dwell: number | null; observations: number; transition_count: number; key_change: string; data_quality: string; coverage: number; composite: number | null; factors: Record<string, number | null>; bridged: boolean; is_transition: boolean }
export interface CkRegimeBlock { regime: string; label: string; start: string; end: string; days: number; current: boolean }
export interface CkRegimeTransition { date: string; from_regime: string; from_label: string; to_regime: string; to_label: string; primary_driver: string; confirmation: string; evidence: string[]; evidence_strength: number }
export interface CkDriverHeat { key: string; label: string; values: (number | null)[]; current: number | null; arrow: CkArrow; label_ui: string; label_ko: string; meaning: string; horizon_label: string; horizons: CkHorizon[]; horizon_read: string }
export interface CkRegimeShare { regime: string; label: string; days: number; share: number }
export interface CkHistoryRange { key: string; days: number; available: boolean; reason: string }
export interface CkRegimeHistory {
  range: string; ranges: CkHistoryRange[]; current_regime: string; current_label: string; duration_days: number; previous_regime: string | null; previous_label: string | null;
  transitions_1m: number; share_pct: number; raw_today: string | null; days: CkRegimeDay[]; blocks: CkRegimeBlock[]; composite: (number | null)[]; composite_current: number | null;
  composite_slope: number | null; composite_slope_days: number; drivers: CkDriverHeat[]; share: CkRegimeShare[]; transitions: CkRegimeTransition[]; total_transitions: number; palette: Record<string, string>; note: string;
}
export interface Cockpit {
  as_of: string; market_now: CkMarketNow; history: CkRegimeHistory | null; drivers: CkDriver[]; cross_asset: CkCrossAsset; leadership: CkLeadership; transmission: CkTransmissionChain[]; radar: CkRadarStock[];
  catalysts: CkCatalyst[]; earnings: CkEarnings | null; what_matters_next: CkNextItem[]; upcoming: CkUpcoming[]; watchlist: CkWatchRow[]; data_status: CkDataStatus; note: string;
}
