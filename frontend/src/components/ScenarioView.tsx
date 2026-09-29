import type { IntelligenceSnapshot, MarketStateHistory, OilRegime, RatesRegime, ScenarioCheck, StateHypothesis, StateLabel } from "../api/types";
import { OilRegimeView } from "./OilRegimeView";
import { RatesRegimeView } from "./RatesRegimeView";
import type { InvestmentIntelligence } from "../api/investment";
import { Panel } from "./Panel";
import { RuleTrace } from "./RuleTrace";
import { SentimentGauge } from "./SentimentGauge";
import { ThemeHeatmap } from "./ThemeHeatmap";
import { DivergencePanel } from "./DivergencePanel";
import { CommodityImpact } from "./CommodityImpact";
import { SemiconductorIntelligence } from "./SemiconductorIntelligence";
import { LABEL_KO, StateHistoryStrip, bandName } from "./StateHistoryStrip";
import { ScenarioCheckPanel, scoreColor } from "./ScenarioCheckPanel";

/**
 * 시나리오 탭의 화면 — 실데이터 화면을 복제하지 않고, 그 탭에 어울리는 판정만 앞세운다.
 *   rule          그 시나리오가 가정하는 판정 라벨의 require/support 룰 (물가 충격 · 유가 급등)
 *   fear_greed    온도계 공포·탐욕 + 한 달 밴드 흐름 (AI 센티)
 *   semiconductor 반도체 인텔리전스 합의 (메모리 업사이클)
 *   calm          평시 여부 — 어느 룰도 걸리지 않았나 (평시)
 * 어느 판정을 앞세울지는 서버 설정(scenario_checks.yaml 의 focus)이 정하고, 숫자는 전부 스냅샷·히스토리·
 * Investment 응답에 이미 있는 값이다. 여기서 새로 계산하는 것은 '며칠' 같은 셈뿐이다.
 */
const sg = (v: number | null, d = 0) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);

export function hypothesisFor(snapshot: IntelligenceSnapshot, label: StateLabel | null): StateHypothesis | null {
  if (!label) return null;
  return snapshot.market_state.hypotheses.find((h) => h.label === label) ?? null;
}

/** 룰 판정 한 줄. require 가 걸렸으면 '해당', 아니면 '아님' — 관측값과 문턱을 그대로 적는다. */
export function ruleHeadline(check: ScenarioCheck, hyp: StateHypothesis | null): { verdict: string; detail: string; on: boolean } {
  const name = check.label ? LABEL_KO[check.label] ?? check.label : check.title;
  if (!hyp) return { verdict: `${name} 판단 불가`, detail: "판정 엔진에 이 라벨의 가설이 없다", on: false };
  const req = hyp.matched_rules.filter((r) => r.kind === "require");
  const reqOk = req.length > 0 && req.every((r) => r.passed);
  const sup = hyp.matched_rules.filter((r) => r.kind === "support");
  const supOk = sup.filter((r) => r.passed).length;
  const reqTxt = req.map((r) => `${r.expression} · 관측 ${r.observed === null ? "없음" : sg(r.observed, 2)}`).join(" / ");
  if (reqOk) {
    return { verdict: `${name} 해당`, detail: `require 통과(${reqTxt}) · 지지 룰 ${supOk}/${sup.length} · 가설 점수 ${hyp.score.toFixed(2)}`, on: true };
  }
  return { verdict: `${name} 아님`, detail: `require 실패(${reqTxt}) · 지지 룰 ${supOk}/${sup.length} 만 통과 · 가설 점수 ${hyp.score.toFixed(2)}`, on: false };
}

export function daysWithLabel(history: MarketStateHistory | null, label: StateLabel | null): { days: number; total: number; dates: string[] } {
  if (!history || !label) return { days: 0, total: history?.points.length ?? 0, dates: [] };
  const dates = history.points.filter((p) => p.label === label).map((p) => p.date);
  return { days: dates.length, total: history.points.length, dates };
}

function FactorSpark({ history, factor }: { history: MarketStateHistory | null; factor: string }) {
  if (!history || history.points.length === 0) return null;
  const vals = history.points.map((p) => p.factors[factor] ?? null);
  const n = vals.length;
  const y = (v: number) => 50 - Math.max(-3, Math.min(3, v)) * (50 / 3);
  const pts = vals.map((v, i) => (v === null ? null : `${((i + 0.5) / n * 100).toFixed(2)},${y(v).toFixed(2)}`)).filter(Boolean).join(" ");
  const last = vals[n - 1] ?? null;
  return (
    <div className="sv-spark" title={`${factor} 팩터의 22거래일 재생값. 눈금 −3 ~ +3, 점선이 문턱 1.0`}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label={`${factor} 팩터 흐름`}>
        <line x1="0" x2="100" y1={y(0)} y2={y(0)} stroke="var(--rule)" strokeWidth="0.6" />
        <line x1="0" x2="100" y1={y(1)} y2={y(1)} stroke="var(--warn)" strokeWidth="0.6" strokeDasharray="2 2" />
        <polyline points={pts} fill="none" stroke="var(--ink)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <span className="mono sv-spark-l">{factor} 팩터 · 최근 22거래일 · 지금 <b className="num">{last === null ? "–" : last.toFixed(2)}</b> (문턱 1.0)</span>
    </div>
  );
}

export function FactorBreakdown({ snapshot, factor }: { snapshot: IntelligenceSnapshot; factor: string }) {
  const f = snapshot.market_state.factors[factor];
  if (!f) return <div className="sv-muted">{factor} 팩터가 이번 스냅샷에 없다.</div>;
  return (
    <div className="sv-factor" data-testid="factor-breakdown">
      <div className="sv-factor-head">
        <b>{factor}</b> <span className="num" style={{ color: f.score >= 0 ? "var(--up)" : "var(--down)" }}>{f.score.toFixed(2)}</span>
        <span className="sv-muted"> · 재료 {f.breakdown.contributions.length}{f.breakdown.missing_inputs.length ? ` · 결측 ${f.breakdown.missing_inputs.join(", ")}` : ""}{f.week_ago !== null ? ` · 1주 전 ${f.week_ago.toFixed(2)}` : ""}</span>
      </div>
      {f.breakdown.contributions.map((c) => (
        <div key={c.key} className="sv-contrib">
          <span className="sv-contrib-k">{c.key}</span>
          <span className="num sv-muted">z {c.raw_value === null ? "–" : sg(c.raw_value, 2)}</span>
          <span className="sv-contrib-bar" aria-hidden="true"><i style={{ width: `${Math.min(100, Math.abs(c.contribution) * 100)}%`, background: c.contribution >= 0 ? "var(--up)" : "var(--down)" }} /></span>
          <span className="num">{sg(c.contribution, 2)}</span>
          <span className="num sv-muted">w {c.weight.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

export function ScenarioView({ check, snapshot, history, investment, oilRegime = null, ratesRegime = null }: {
  check: ScenarioCheck; snapshot: IntelligenceSnapshot; history: MarketStateHistory | null; investment: InvestmentIntelligence | null; oilRegime?: OilRegime | null; ratesRegime?: RatesRegime | null;
}) {
  // 물가 탭 — Inflation & Rates Intelligence. Regime → Rate Driver → Inflation Components → Curve → Yield Decomposition → Confirmation → Divergence → Implication → Triggers → Diagnostics.
  if (check.focus === "rates_regime") {
    if (!ratesRegime) return <div className="grid"><section className="panel span-3"><div className="panel-body" style={{ color: "var(--muted)" }}>금리·물가 원인 판별을 불러오는 중…</div></section></div>;
    return <RatesRegimeView regime={ratesRegime} snapshot={snapshot} check={check} />;
  }
  // 유가 탭 — 시장 원인 판별 화면. 룰 판정·서명 대조는 그 화면의 Diagnostics 안으로 들어간다.
  if (check.focus === "oil_regime") {
    if (!oilRegime) return <div className="grid"><section className="panel span-3"><div className="panel-body" style={{ color: "var(--muted)" }}>유가 원인 판별을 불러오는 중…</div></section></div>;
    return <OilRegimeView regime={oilRegime} snapshot={snapshot} check={check} history={history} />;
  }
  const themeIds = new Set(check.themes.map((t) => t.theme_id));
  const themes = snapshot.themes.filter((t) => themeIds.has(t.theme_id));
  const themeNames = Object.fromEntries(snapshot.themes.map((t) => [t.theme_id, t.name]));
  // 관련 괴리 — 그 탭의 테마에 걸린 것, 그 탭의 원자재가 다리인 것, 물가 탭의 유가↔기대인플레이션. 서명 계열 전체로 넓히면 전부가 '관련' 이 된다.
  const divs = snapshot.divergences.filter((d) => (d.related_theme && themeIds.has(d.related_theme))
    || d.related_assets.some((a) => check.commodities.includes(a))
    || (check.factor === "Inflation" && d.type === "OIL_VS_INFLATION_EXP"));
  const short = check.title.split(" — ")[0] ?? check.title;
  const hyp = hypothesisFor(snapshot, check.label);
  const t = snapshot.thermometer;

  let headline: React.ReactNode;
  if (check.focus === "rule") {
    const h = ruleHeadline(check, hyp);
    const d = daysWithLabel(history, check.label);
    headline = (
      <Panel title={`${short} 판정`} span={3} note={<span className="mono" style={{ color: h.on ? "var(--crit)" : "var(--muted)" }}>{d.total ? `최근 ${d.total}거래일 중 ${d.days}일${d.dates.length ? ` (${d.dates.map((x) => x.slice(5)).join(", ")})` : ""}` : ""}</span>}>
        <div className="sv-head" data-testid="scenario-headline" data-on={h.on ? "1" : "0"}>
          <span className="sv-verdict" style={{ color: h.on ? "var(--crit)" : "var(--ink)" }}>{h.verdict}</span>
          <span className="sv-detail mono">{h.detail}</span>
        </div>
        <div className="sv-cols">
          <div>{hyp ? <RuleTrace hypothesis={hyp} /> : <div className="sv-muted">가설 없음</div>}</div>
          <div>
            {check.factor ? <FactorBreakdown snapshot={snapshot} factor={check.factor} /> : null}
            {check.factor ? <FactorSpark history={history} factor={check.factor} /> : null}
            {!check.factor && snapshot.market_state.main_drivers.length ? (
              <div className="sv-muted">주도 변수: {snapshot.market_state.main_drivers.slice(0, 4).map((m) => `${m.label} ${sg(m.z, 1)}σ`).join(" · ")}</div>
            ) : null}
          </div>
        </div>
      </Panel>
    );
  } else if (check.focus === "fear_greed") {
    const cur = history?.points[history.points.length - 1] ?? null;
    headline = (
      <Panel title={`${short} · 공포·탐욕`} span={3} note={t ? <span className="mono">{t.band_label} · 종합 {sg(t.composite)} · 가격 {sg(t.price)} / 뉴스 {sg(t.news)}</span> : undefined}>
        <div className="sv-head" data-testid="scenario-headline" data-on={t && (t.band === "overheated" || t.band === "frozen") ? "1" : "0"}>
          <span className="sv-verdict">{t ? `시장 온도 ${sg(t.composite)} · ${bandName(t.band, history?.band_labels ?? {})}` : "온도계 없음"}</span>
          <span className="sv-detail mono">
            {t ? `${t.gap_flag === "narrative_hot" ? "뉴스가 가격보다 뜨겁다" : t.gap_flag === "narrative_cold" ? "뉴스가 가격보다 차갑다" : "뉴스와 가격이 같은 온도"} · 격차 ${t.gap === null ? "–" : t.gap.toFixed(0)} · 신뢰도 ${t.confidence.toFixed(0)}%` : ""}
            {history && cur ? ` · 지금 ${bandName(cur.band, history.band_labels)} ${history.current_band_streak}일째, 22일 중 냉각·결빙 ${(history.days_by_band.cool ?? 0) + (history.days_by_band.frozen ?? 0)} · 온기·과열 ${(history.days_by_band.warm ?? 0) + (history.days_by_band.overheated ?? 0)}` : ""}
          </span>
        </div>
        <div className="sv-cols">
          <SentimentGauge t={t} />
          <StateHistoryStrip history={history} primary="band" />
        </div>
      </Panel>
    );
  } else if (check.focus === "semiconductor") {
    const s = investment?.semiconductor ?? null;
    const dirs = s ? [s.memory_direction, s.peer_direction, s.korea_direction, s.eps_direction] : [];
    const known = dirs.filter((d): d is number => d !== null);
    const up = known.filter((d) => d >= 0.5).length, down = known.filter((d) => d <= -0.5).length;
    const verdict = !s ? "반도체 인텔리전스 없음" : known.length === 0 ? "반도체 신호 판단 불가" : up === known.length ? "반도체 업사이클 신호 — 확보된 신호가 전부 상승" : down === known.length ? "반도체 다운사이클 신호 — 확보된 신호가 전부 하락" : `반도체 신호 엇갈림 — 상승 ${up} · 하락 ${down} · 혼조 ${known.length - up - down} (신호 ${known.length}/4)`;
    headline = (
      <Panel title={`${short} · 반도체 합의`} span={3} note={s ? <span className="mono">신호 {known.length}/4 확보{s.missing.length ? ` · 없음 ${s.missing.length}` : ""}</span> : undefined}>
        <div className="sv-head" data-testid="scenario-headline" data-on={s && known.length > 0 && up === known.length ? "1" : "0"}>
          <span className="sv-verdict">{verdict}</span>
          <span className="sv-detail mono">{s?.interpretation ?? "Investment Intelligence 응답이 아직 없다"}</span>
        </div>
        {s ? <SemiconductorIntelligence s={s} /> : null}
      </Panel>
    );
  } else {
    const firing = snapshot.market_state.hypotheses.filter((h) => h.score > 0);
    const d = daysWithLabel(history, "NEUTRAL");
    const calm = snapshot.market_state.primary_label === "NEUTRAL";
    headline = (
      <Panel title={`${short} 여부`} span={3} note={history ? <span className="mono">최근 {d.total}거래일 중 판정 없음 {d.days}일 · 전환 {history.changes}회</span> : undefined}>
        <div className="sv-head" data-testid="scenario-headline" data-on={calm ? "1" : "0"}>
          <span className="sv-verdict" style={{ color: calm ? "var(--ok)" : "var(--crit)" }}>{calm ? "평시 — 어느 판정 룰도 걸리지 않았다" : `평시 아님 — ${LABEL_KO[snapshot.market_state.primary_label] ?? snapshot.market_state.primary_label} ${snapshot.market_state.confidence.toFixed(0)}%`}</span>
          <span className="sv-detail mono">
            {firing.length ? `걸린 가설 ${firing.map((h) => `${LABEL_KO[h.label] ?? h.label} ${h.score.toFixed(2)}`).join(" · ")}` : "걸린 가설 없음"}
            {t ? ` · 온도 ${sg(t.composite)} ${t.band_label}` : ""}
            {snapshot.market_state.main_drivers.length ? ` · 주도 ${snapshot.market_state.main_drivers.slice(0, 3).map((m) => `${m.label} ${sg(m.z, 1)}σ`).join(", ")}` : ""}
          </span>
        </div>
        <StateHistoryStrip history={history} primary="label" />
      </Panel>
    );
  }

  const commodityRows = investment && check.commodities.length ? investment.commodity_impact.filter((r) => check.commodities.includes(r.commodity_id)) : [];

  return (
    <div className="grid" data-testid="scenario-view" data-focus={check.focus}>
      {headline}
      {themes.length > 0 && (
        <Panel title="관련 테마" span={divs.length || commodityRows.length ? 2 : 3} note={`${themes.length}개`} flush>
          <ThemeHeatmap themes={themes} events={snapshot.events} />
        </Panel>
      )}
      {divs.length > 0 && (
        <Panel title="관련 괴리" span={themes.length ? 1 : 3} note={`${divs.length}건`}>
          <DivergencePanel items={divs} themeNames={themeNames} />
        </Panel>
      )}
      {commodityRows.length > 0 && (
        <Panel title="원자재 → 산업 → 종목" span={3} note={commodityRows.some((r) => r.rollover_suspect) ? <span style={{ color: "var(--warn)" }}>롤오버 의심 있음</span> : undefined}>
          <CommodityImpact rows={commodityRows} />
        </Panel>
      )}
      <Panel title={`시나리오 서명 대조 · ${short}`} span={3} note={<span className="num" style={{ color: scoreColor(check.match_score) }}>실데이터 일치도 {check.match_score.toFixed(0)}% · {check.match_label}</span>}>
        <ScenarioCheckPanel check={check} />
      </Panel>
    </div>
  );
}
