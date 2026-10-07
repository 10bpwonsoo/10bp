import type { RatesRegime, RatesDriverScore, RatesConfirmationRow, InflationComponent, IntelligenceSnapshot, ScenarioCheck, RatesEvidenceItem } from "../api/types";
import { RuleTrace } from "./RuleTrace";
import { ScenarioCheckPanel, scoreColor } from "./ScenarioCheckPanel";
import { FactorBreakdown, hypothesisFor } from "./ScenarioView";
import { strengthColor } from "./OilRegimeView";
import { DailyHistoryPanel } from "./DailyHistoryStrip";

/**
 * 물가 탭 — Inflation & Rates Intelligence.
 * 순서: REGIME → WHAT IS DRIVING RATES? → INFLATION PRESSURE → TREASURY CURVE → NOMINAL YIELD DECOMPOSITION
 *       → MARKET CONFIRMATION → KEY DIVERGENCE → MARKET IMPLICATION → WHAT CHANGES THE VIEW → Diagnostics(접이식).
 * 5초 안에 (1) 금리를 움직이는 driver, (2) 물가 리프라이싱이 확인됐는지, (3) 무엇이 바뀌면 판단이 바뀌는지가 읽혀야 한다.
 * 숫자는 서버가 만들고 화면은 그리기만 한다. 확률이 아니라 증거 크기다. 추천이 아니라 전이 방향이다.
 */
const STATUS: Record<string, { ko: string; color: string }> = {
  CONFIRMED: { ko: "확인됨", color: "var(--ok)" },
  UNCONFIRMED: { ko: "미확인", color: "var(--warn)" },
  CONTRADICTED: { ko: "반박됨", color: "var(--down)" },
};
const CONF: Record<string, { ko: string; mark: string; color: string }> = {
  CONFIRMED: { ko: "확인", mark: "✓", color: "var(--ok)" },
  MIXED: { ko: "혼재", mark: "~", color: "var(--warn)" },
  NOT_CONFIRMED: { ko: "불확인", mark: "✗", color: "var(--down)" },
  MISSING: { ko: "결측", mark: "–", color: "var(--faint)" },
};
const COMP: Record<string, { ko: string; color: string }> = {
  up: { ko: "상승", color: "var(--up)" }, down: { ko: "하락", color: "var(--down)" }, flat: { ko: "보합", color: "var(--muted)" }, missing: { ko: "계열 없음", color: "var(--faint)" },
};
const SHAPE_KO: Record<string, string> = {
  bear_steepening: "Bear steepening", bear_flattening: "Bear flattening", bull_steepening: "Bull steepening", bull_flattening: "Bull flattening",
  parallel_up: "Parallel up", parallel_down: "Parallel down", flat: "Flat / range", unknown: "Unknown",
};
const LEAD_KO: Record<string, string> = { front: "단기 구간 주도", long: "장기 구간 주도", parallel: "전 구간 비슷", none: "" };
const PRESSURE: Record<number, { mark: string; ko: string; color: string }> = {
  1: { mark: "↑", ko: "상승 압력", color: "var(--up)" }, [-1]: { mark: "↓", ko: "하락 압력", color: "var(--down)" },
  0: { mark: "→", ko: "중립", color: "var(--muted)" }, 2: { mark: "⇅", ko: "양방향(상쇄)", color: "var(--warn)" },
};
const sg = (v: number | null, d = 1) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);
const bp = (v: number | null) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(0)}bp`);
const evText = (e: RatesEvidenceItem) => e.kind === "news" ? `${e.label} ${sg(e.value, 0)}` : `${e.label} ${sg(e.value)}σ${e.window === 5 ? " (5일)" : ""}`;

function ScoreBar({ score, testid }: { score: number; testid?: string }) {
  const w = Math.min(100, Math.abs(score));
  return (
    <div className="rr-bar" aria-label={sg(score, 0)} data-testid={testid}>
      <i className="rr-zero" />
      <i className="rr-fill" style={{ width: `${w / 2}%`, [score >= 0 ? "left" : "right"]: "50%", background: score >= 0 ? "var(--up)" : "var(--down)" } as React.CSSProperties} />
      <b className="num" style={{ color: score >= 0 ? "var(--up)" : "var(--down)" }}>{sg(score, 0)}</b>
    </div>
  );
}

function DriverRow({ d, dominant }: { d: RatesDriverScore; dominant: boolean }) {
  const st = STATUS[d.status] ?? STATUS.UNCONFIRMED!;
  const top = d.evidence.filter((e) => e.available).slice(0, 3);
  return (
    <div className={`rr-drv${dominant ? " on" : ""}`} data-testid="rates-driver" data-id={d.id} data-status={d.status} title={d.status_reason}>
      <div className="rr-drv-head">
        <span className="rr-drv-name">{d.label}<small> {d.label_ko}</small></span>
        <span className="rr-drv-status mono" style={{ color: st.color }}>{d.status} · {st.ko}</span>
      </div>
      <ScoreBar score={d.score} />
      <div className="rr-ev mono">{top.map(evText).join(" · ")}{d.coverage < 1 ? <span style={{ color: "var(--faint)" }}> · 확보 {(d.coverage * 100).toFixed(0)}%</span> : null}</div>
    </div>
  );
}

function ComponentRow({ c }: { c: InflationComponent }) {
  const st = COMP[c.status] ?? COMP.missing!;
  const top = c.evidence.filter((e) => e.available).slice(0, 3);
  return (
    <div className={`rr-comp ${c.status}`} data-testid="inflation-component" data-key={c.key} data-status={c.status}>
      <div className="rr-comp-head">
        <span className="rr-comp-name">{c.label}<small> {c.label_ko}</small></span>
        <span className="mono" style={{ color: st.color }}>{st.ko}</span>
      </div>
      {c.score === null ? <div className="rr-ev" style={{ color: "var(--faint)" }}>{c.note || "계열 없음 — 0 이 아니라 결측"}</div> : (
        <>
          <ScoreBar score={c.score} />
          <div className="rr-ev mono">{top.map(evText).join(" · ")}{c.note ? <span style={{ color: "var(--faint)" }}> · {c.note}</span> : null}</div>
        </>
      )}
    </div>
  );
}

function ConfRow({ r }: { r: RatesConfirmationRow }) {
  const c = CONF[r.status] ?? CONF.MIXED!;
  const vals = Object.entries(r.values).filter(([, v]) => v !== null).map(([k, v]) => `${k} ${sg(v)}σ`).join(" · ");
  return (
    <div className={`rr-conf ${r.status}`} role="row" data-status={r.status} title={r.note}>
      <span className="rr-conf-mark" style={{ color: c.color }} aria-hidden="true">{c.mark}</span>
      <span className="rr-conf-label">{r.label}</span>
      <span className="num rr-conf-val" style={{ color: r.status === "MISSING" ? "var(--faint)" : "var(--ink-2)" }}>{r.status === "MISSING" ? r.note : vals}</span>
      <span className="rr-conf-exp mono" style={{ color: "var(--faint)" }}>{r.expected_sign === null ? "" : `기대 ${r.expected_sign > 0 ? "+" : "−"}`}</span>
      <span className="rr-conf-st mono" style={{ color: c.color }}>{r.status.replace("_", " ")}</span>
    </div>
  );
}

export function RatesRegimeView({ regime, snapshot, check }: { regime: RatesRegime; snapshot: IntelligenceSnapshot; check: ScenarioCheck }) {
  const dom = regime.drivers.find((d) => d.id === regime.dominant) ?? regime.drivers[0]!;
  const domSt = STATUS[dom.status] ?? STATUS.UNCONFIRMED!;
  const inflSt = STATUS[regime.inflation_status] ?? STATUS.UNCONFIRMED!;
  const ordered = [...regime.drivers].sort((a, b) => (a.status === "CONFIRMED" ? 0 : 1) - (b.status === "CONFIRMED" ? 0 : 1) || Math.abs(b.score) - Math.abs(a.score));
  const counts = { CONFIRMED: 0, MIXED: 0, NOT_CONFIRMED: 0, MISSING: 0 } as Record<string, number>;
  for (const r of regime.confirmations) counts[r.status] = (counts[r.status] ?? 0) + 1;
  const hyp = hypothesisFor(snapshot, check.label);
  const [main, sub] = regime.regime_label.split(" — ");
  const rm = regime.rate_move;
  const dirKo = { up: "상승", down: "하락", flat: "보합", unknown: "미상" }[rm.direction];
  const divs = [...regime.divergences].sort((a, b) => b.severity - a.severity);
  return (
    <div className="rr" data-testid="rates-regime">
      {/* 1. INFLATION & RATES REGIME */}
      <section className="panel span-3 rr-regime" data-testid="rates-regime-card">
        <header className="panel-head"><h2 className="panel-title">Inflation &amp; Rates Regime</h2><div className="panel-note mono">{new Date(regime.as_of).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "medium", timeStyle: "short" })} KST · FRED 하루 지연</div></header>
        <div className="panel-body">
          <div className="rr-head">
            <div className="rr-title">
              <span className="rr-k mono">REGIME · DOMINANT RATE DRIVER</span>
              <span className="rr-label">{main}</span>
              <span className="rr-sub mono" data-testid="inflation-status" style={{ color: inflSt.color }}>{sub ?? `Inflation Repricing ${regime.inflation_status}`} · {inflSt.ko}</span>
            </div>
            <div className="rr-side">
              <div className="rr-move mono" data-testid="rate-move">
                <span className="rr-k">US 10Y YIELD</span>
                <span><b className="num">{rm.level === null ? "–" : `${rm.level.toFixed(2)}%`}</b> · 5일 <b className="num" style={{ color: rm.change_5d_bp !== null && rm.change_5d_bp >= 0 ? "var(--up)" : "var(--down)" }}>{bp(rm.change_5d_bp)}</b> · <b className="num">{sg(rm.z)}σ</b>{rm.window === 5 ? " (5일)" : ""} · {dirKo}</span>
              </div>
              <div className="rr-strength" title={`|driver 점수| ${regime.signal_strength.toFixed(0)} · 2위와 격차 ${regime.margin.toFixed(0)}`}>
                <span className="rr-k mono">EVIDENCE STRENGTH</span>
                <span className="rr-strength-bar"><i style={{ width: `${regime.signal_strength}%`, background: strengthColor(regime.signal_strength_label) }} /></span>
                <span className="mono" style={{ color: strengthColor(regime.signal_strength_label) }}>{regime.signal_strength_label} <b className="num">{regime.signal_strength.toFixed(0)}</b><span style={{ color: "var(--faint)" }}> · 2위와 {regime.margin.toFixed(0)} 차 · {dom.status} <span style={{ color: domSt.color }}>{domSt.ko}</span></span></span>
              </div>
            </div>
          </div>
          <p className="rr-headline">{regime.headline}</p>
          <p className="rr-impl"><span className="rr-k mono">TRANSMISSION</span> {regime.implication}</p>
          <div className="rr-chips">
            {ordered.map((d) => (
              <span key={d.id} className={`rr-chip${d.id === regime.dominant ? " on" : ""}`} style={{ borderColor: (STATUS[d.status] ?? STATUS.UNCONFIRMED!).color }} title={d.status_reason}>
                {d.label} <b className="num">{sg(d.score, 0)}</b> <small>{d.status}</small>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* 1a. STATE HISTORY · 1M — 저장된 daily snapshot 의 sequence (지배 driver · 점수 · 확신). 과거 고정, 오늘 LIVE */}
      <DailyHistoryPanel tab="rates_regime" title="Inflation & Rates State History · 1M" scenario={snapshot.scenario ?? undefined} asOf={snapshot.as_of} />

      {/* 2. WHAT IS DRIVING RATES? */}
      <section className="panel span-2">
        <header className="panel-head"><h2 className="panel-title">What Is Driving Rates?</h2><div className="panel-note mono">evidence score · −100 장기금리 하락 압력 … +100 상승 압력 · 상태는 10Y 방향과의 일치</div></header>
        <div className="panel-body rr-drivers">
          {ordered.map((d) => <DriverRow key={d.id} d={d} dominant={d.id === regime.dominant} />)}
        </div>
      </section>

      {/* 3. INFLATION PRESSURE */}
      <section className="panel">
        <header className="panel-head"><h2 className="panel-title">Inflation Pressure</h2><div className="panel-note mono">구성별 · 결측은 0 이 아니다</div></header>
        <div className="panel-body rr-comps">
          {regime.inflation_components.map((c) => <ComponentRow key={c.key} c={c} />)}
        </div>
      </section>

      {/* 4. TREASURY CURVE */}
      <section className="panel span-2" data-testid="curve">
        <header className="panel-head"><h2 className="panel-title">Treasury Curve</h2><div className="panel-note mono">{SHAPE_KO[regime.curve.shape]}{regime.curve.lead !== "none" ? ` · ${LEAD_KO[regime.curve.lead]}` : ""} · 2s10s {sg(regime.curve.spread_z)}σ</div></header>
        <div className="panel-body">
          <div className="rr-tenors" role="table" aria-label="테너별 금리">
            {regime.curve.tenors.map((t) => (
              <div key={t.id} className="rr-tenor" role="row" data-tenor={t.label} title={`${t.id} · 하루 ${sg(t.z_1d)}σ · 5일 ${sg(t.z_5d)}σ`}>
                <span className="rr-tenor-l mono">{t.label}</span>
                <b className="num rr-tenor-lvl">{t.level === null ? "–" : `${t.level.toFixed(2)}%`}</b>
                <span className="num rr-tenor-bp" style={{ color: t.change_5d_bp !== null && t.change_5d_bp >= 0 ? "var(--up)" : "var(--down)" }}>{bp(t.change_5d_bp)}</span>
                <span className="rr-tenor-z"><i style={{ width: `${Math.min(100, Math.abs(t.z ?? 0) / 3 * 50)}%`, [(t.z ?? 0) >= 0 ? "left" : "right"]: "50%", background: (t.z ?? 0) >= 0 ? "var(--up)" : "var(--down)" } as React.CSSProperties} /><b className="num">{sg(t.z)}σ</b></span>
              </div>
            ))}
          </div>
          <p className="rr-sent">{regime.curve.sentence}</p>
        </div>
      </section>

      {/* 5. NOMINAL YIELD DECOMPOSITION */}
      <section className="panel" data-testid="decomposition">
        <header className="panel-head"><h2 className="panel-title">Nominal Yield Decomposition</h2><div className="panel-note mono">명목 = <span style={{ color: "var(--accent)" }}>실질</span> + <span style={{ color: "var(--muted)" }}>기대인플레</span> · {regime.decomposition[0]?.window_days ?? 5}일 변화</div></header>
        <div className="panel-body rr-decomp">
          {regime.decomposition.map((d) => (
            <div key={d.tenor} className="rr-dec" data-dominant={d.dominant}>
              <div className="rr-dec-head mono"><b>{d.tenor}</b> 명목 <b className="num">{bp(d.nominal_bp)}</b> = 실질 <b className="num" style={{ color: d.dominant === "real" ? "var(--accent)" : undefined }}>{bp(d.real_implied_bp)}</b> + 기대인플레 <b className="num" style={{ color: d.dominant === "breakeven" ? "var(--accent)" : undefined }}>{bp(d.breakeven_bp)}</b>{d.real_measured_bp !== null ? <span style={{ color: "var(--muted)" }}> · TIPS 실측 {bp(d.real_measured_bp)}</span> : null}</div>
              {d.nominal_bp !== null && d.breakeven_bp !== null && d.real_implied_bp !== null ? (
                <div className="rr-dec-bar" aria-hidden="true">
                  <i style={{ flex: Math.abs(d.real_implied_bp) || 0.0001, background: "var(--accent)" }} title={`실질 ${bp(d.real_implied_bp)}`} />
                  <i style={{ flex: Math.abs(d.breakeven_bp) || 0.0001, background: "var(--muted)" }} title={`기대인플레 ${bp(d.breakeven_bp)}`} />
                </div>
              ) : null}
              <div className="rr-sent">{d.sentence}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 6. MARKET CONFIRMATION */}
      <section className="panel span-2">
        <header className="panel-head"><h2 className="panel-title">Market Confirmation</h2><div className="panel-note mono"><span style={{ color: "var(--ok)" }}>CONFIRMED {counts.CONFIRMED}</span> · <span style={{ color: "var(--warn)" }}>MIXED {counts.MIXED}</span> · <span style={{ color: "var(--down)" }}>NOT CONFIRMED {counts.NOT_CONFIRMED}</span> · {dom.label} 기준</div></header>
        <div className="panel-body rr-confs" role="table" aria-label="시장 확인">
          {regime.confirmations.map((r) => <ConfRow key={r.key} r={r} />)}
        </div>
      </section>

      {/* 7. KEY DIVERGENCE */}
      <section className="panel" data-testid="key-divergence">
        <header className="panel-head"><h2 className="panel-title">Key Divergence</h2><div className="panel-note mono">자동 탐지 {divs.length}건 · 심각도 = 관련 z 중 작은 쪽</div></header>
        <div className="panel-body rr-divs">
          {divs.length === 0 ? <div className="sv-muted">설정된 괴리 짝 중 지금 걸린 것이 없다.</div> : divs.map((d) => (
            <div key={d.key} className="rr-div" data-testid="divergence-row">
              <div className="rr-div-head"><b>{d.label}</b><span className="mono num" style={{ color: "var(--warn)" }}>{d.severity.toFixed(1)}σ</span></div>
              <div className="rr-div-vals mono">{Object.entries(d.values).filter(([, v]) => v !== null).map(([k, v]) => `${k} ${sg(v)}σ`).join(" · ")}</div>
              <div className="rr-sent">{d.why}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 8. MARKET IMPLICATION */}
      <section className="panel span-3" data-testid="market-implication">
        <header className="panel-head"><h2 className="panel-title">Market Implication</h2><div className="panel-note mono">{dom.label} 아래서의 전이 방향 — 추천이 아니다</div></header>
        <div className="panel-body">
          <div className="rr-imp-grid">
            {regime.market_implication.rows.map((r) => {
              const p = PRESSURE[r.pressure] ?? PRESSURE[0]!;
              return (
                <div key={r.key} className="rr-imp" data-pressure={r.pressure}>
                  <span className="rr-imp-mark" style={{ color: p.color }} aria-label={p.ko}>{p.mark}</span>
                  <span className="rr-imp-label">{r.label}</span>
                  <span className="rr-imp-ko mono" style={{ color: p.color }}>{p.ko}</span>
                </div>
              );
            })}
          </div>
          <p className="rr-sent" style={{ marginTop: 8 }}>{regime.market_implication.why}</p>
        </div>
      </section>

      {/* 9. WHAT CHANGES THE VIEW */}
      <section className="panel span-3 rr-watch" data-testid="what-changes">
        <header className="panel-head"><h2 className="panel-title">What Changes The View</h2><div className="panel-note mono">{dom.id === "inflation_repricing" ? "물가 리프라이싱 판단이 깨지는 조건" : "물가 리프라이싱으로 넘어가는 조건"} · 그리고 지배 driver 해제 조건</div></header>
        <div className="panel-body rr-watch-cols">
          <ol className="rr-watch-list">
            {regime.triggers.map((t, i) => (
              <li key={i} data-testid="trigger-item" data-met={t.met} className={t.met ? "met" : ""}>
                <span className="rr-watch-text">{t.text}</span>
                <span className="rr-watch-meta mono">{t.measurable ? <>{t.metric} 지금 <b className="num">{t.current}</b> · 조건 {t.condition} · {t.met ? <span style={{ color: "var(--ok)" }}>충족</span> : <span style={{ color: "var(--muted)" }}>미충족</span>}</> : <span style={{ color: "var(--faint)" }}>{t.metric} 계열 없음 — 지금은 못 잰다</span>}</span>
              </li>
            ))}
          </ol>
          <ul className="rr-release-list">
            {regime.release.map((t, i) => (
              <li key={i} data-testid="release-item">
                <span className="rr-watch-text">{t.text}</span>
                <span className="rr-watch-meta mono">{t.metric} 지금 <b className="num">{t.current}</b> · 조건 {t.condition}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 10. Diagnostics */}
      <details className="panel span-3 rr-diag" data-testid="rates-diagnostics">
        <summary className="panel-head"><h2 className="panel-title">Diagnostics</h2><div className="panel-note mono">판정 룰(require/support) · 팩터 원점수 · 시나리오 서명 대조 · driver 증거 전체 — 접어 둔 내부 진단</div></summary>
        <div className="panel-body">
          <div className="rr-diag-grid">
            <div>
              <div className="rr-k mono">판정 룰 — {check.label ?? "라벨 없음"}</div>
              {hyp ? <RuleTrace hypothesis={hyp} /> : <div className="sv-muted">가설 없음</div>}
              <div className="sv-muted" style={{ marginTop: 6 }}>지금 판정 {snapshot.market_state.primary_label} {snapshot.market_state.confidence.toFixed(0)}% · 가설 점수 {check.hypothesis_score === null ? "–" : check.hypothesis_score.toFixed(2)}</div>
              {check.factor ? <div style={{ marginTop: 10 }}><div className="rr-k mono">팩터 원점수 — {check.factor}</div><FactorBreakdown snapshot={snapshot} factor={check.factor} /></div> : null}
            </div>
            <div>
              <div className="rr-k mono">driver 증거 전체</div>
              {regime.drivers.map((d) => (
                <div key={d.id} className="rr-diag-ev mono">
                  <b>{d.label}</b> {sg(d.score, 0)} · {d.evidence.map((e) => e.available ? `${evText(e)} → ${sg(e.contribution, 2)}` : `${e.label} 결측`).join(" · ")}
                </div>
              ))}
              <div className="rr-k mono" style={{ marginTop: 8 }}>물가 구성 증거</div>
              {regime.inflation_components.map((c) => (
                <div key={c.key} className="rr-diag-ev mono"><b>{c.label}</b> {c.score === null ? "결측" : sg(c.score, 0)} · {c.evidence.map((e) => e.available ? `${evText(e)} → ${sg(e.contribution, 2)}` : `${e.label} 결측`).join(" · ") || c.note}</div>
              ))}
            </div>
          </div>
          <div className="rr-k mono" style={{ marginTop: 12 }}>시나리오 서명 대조 · 실데이터 일치도 <span style={{ color: scoreColor(check.match_score) }}>{check.match_score.toFixed(0)}%</span></div>
          <ScenarioCheckPanel check={check} />
          <div className="sh-note" style={{ marginTop: 8 }}>{regime.note}</div>
        </div>
      </details>
    </div>
  );
}
