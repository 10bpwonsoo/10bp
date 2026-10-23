import type { OilRegime, OilDriverScore, OilConfirmationRow, IntelligenceSnapshot, ScenarioCheck, MarketStateHistory } from "../api/types";
import { RuleTrace } from "./RuleTrace";
import { ScenarioCheckPanel, scoreColor } from "./ScenarioCheckPanel";
import { hypothesisFor } from "./ScenarioView";
import { DailyHistoryPanel } from "./DailyHistoryStrip";

/**
 * 유가 탭 — 시장 원인 판별 화면.
 * 순서: REGIME → DRIVER → CONFIRMATION → NARRATIVE vs PRICE (market implication) → WHAT TO WATCH NEXT → Diagnostics.
 * 5초 안에 (1) 지금 유가를 움직이는 driver, (2) 지지/반박하는 데이터, (3) 무엇이 바뀌면 판단이 바뀌는지가 읽혀야 한다.
 * 숫자는 서버가 만들고 화면은 그리기만 한다. 원인을 단정하지 않는다 — CONFIRMED / UNCONFIRMED / CONTRADICTED.
 */
const STATUS: Record<string, { ko: string; color: string }> = {
  CONFIRMED: { ko: "확인됨", color: "var(--ok)" },
  UNCONFIRMED: { ko: "미확인", color: "var(--warn)" },
  CONTRADICTED: { ko: "반박됨", color: "var(--down)" },
};
const CONF: Record<string, { ko: string; mark: string; color: string }> = {
  confirms: { ko: "확인", mark: "✓", color: "var(--ok)" },
  contradicts: { ko: "반박", mark: "✗", color: "var(--down)" },
  neutral: { ko: "중립", mark: "·", color: "var(--muted)" },
  missing: { ko: "결측", mark: "–", color: "var(--faint)" },
};
const sg = (v: number | null, d = 1) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);
const evText = (e: OilDriverScore["evidence"][number]) => e.kind === "news" ? `${e.label} ${sg(e.value, 0)}` : `${e.label} ${sg(e.value)}σ${e.window === 5 ? " (5일)" : ""}`;

export function strengthColor(label: string): string {
  return label === "STRONG" ? "var(--crit)" : label === "MODERATE" ? "var(--warn)" : "var(--muted)";
}

function DriverBar({ d, dominant }: { d: OilDriverScore; dominant: boolean }) {
  const w = Math.min(100, Math.abs(d.score));
  const st = STATUS[d.status] ?? STATUS.UNCONFIRMED!;
  const top = d.evidence.filter((e) => e.available).slice(0, 3);
  return (
    <div className={`or-drv${dominant ? " on" : ""}`} data-testid="oil-driver" data-id={d.id} data-status={d.status}>
      <div className="or-drv-head">
        <span className="or-drv-name">{d.label}<small> {d.label_ko}</small></span>
        <span className="or-drv-status mono" style={{ color: st.color }}>{d.status} · {st.ko}</span>
      </div>
      <div className="or-drv-bar" aria-label={`${d.label} ${sg(d.score, 0)}`}>
        <i className="or-drv-zero" />
        <i className="or-drv-fill" style={{ width: `${w / 2}%`, [d.score >= 0 ? "left" : "right"]: "50%", background: d.score >= 0 ? "var(--up)" : "var(--down)" } as React.CSSProperties} />
        <b className="num" style={{ color: d.score >= 0 ? "var(--up)" : "var(--down)" }}>{sg(d.score, 0)}</b>
      </div>
      <div className="or-drv-ev mono">{top.map((e) => evText(e)).join(" · ")}{d.coverage < 1 ? <span style={{ color: "var(--faint)" }}> · 확보 {(d.coverage * 100).toFixed(0)}%</span> : null}</div>
    </div>
  );
}

function ConfRow({ r }: { r: OilConfirmationRow }) {
  const c = CONF[r.status] ?? CONF.neutral!;
  const vals = Object.entries(r.values).filter(([, v]) => v !== null).map(([k, v]) => `${k} ${sg(v)}σ`).join(" · ");
  return (
    <div className={`or-conf ${r.status}`} role="row" data-status={r.status} title={r.note}>
      <span className="or-conf-mark" style={{ color: c.color }} aria-hidden="true">{c.mark}</span>
      <span className="or-conf-label">{r.label}</span>
      <span className="num or-conf-val" style={{ color: r.status === "missing" ? "var(--faint)" : "var(--ink-2)" }}>{r.status === "missing" ? r.note : vals}</span>
      <span className="or-conf-exp mono" style={{ color: "var(--faint)" }}>{r.expected_sign === null ? "" : `기대 ${r.expected_sign > 0 ? "+" : "−"}`}</span>
      <span className="or-conf-st mono" style={{ color: c.color }}>{c.ko}</span>
    </div>
  );
}

export function OilRegimeView({ regime, snapshot, check, history }: { regime: OilRegime; snapshot: IntelligenceSnapshot; check: ScenarioCheck; history: MarketStateHistory | null }) {
  const dom = regime.drivers.find((d) => d.id === regime.dominant) ?? regime.drivers[0]!;
  const st = STATUS[dom.status] ?? STATUS.UNCONFIRMED!;
  const ordered = [...regime.drivers].sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  const confirms = regime.confirmations.filter((r) => r.status === "confirms").length;
  const contradicts = regime.confirmations.filter((r) => r.status === "contradicts").length;
  const hyp = hypothesisFor(snapshot, check.label);
  void history;
  return (
    <div className="or" data-testid="oil-regime">
      {/* 1. OIL MARKET REGIME */}
      <section className="panel span-3 or-regime" data-testid="oil-regime-card">
        <header className="panel-head"><h2 className="panel-title">Oil Market Regime</h2><div className="panel-note mono">{new Date(regime.as_of).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "medium", timeStyle: "short" })} KST</div></header>
        <div className="panel-body">
          <div className="or-head">
            <div className="or-title">
              <span className="or-k mono">DOMINANT DRIVER</span>
              <span className="or-label">{regime.regime_label.split(" — ")[0]}</span>
              <span className="or-status mono" style={{ color: st.color }} data-testid="oil-status">{dom.status} · {st.ko}</span>
            </div>
            <div className="or-strength" title={`|driver 점수| ${regime.signal_strength.toFixed(0)} · 2위와 격차 ${regime.margin.toFixed(0)}`}>
              <span className="or-k mono">SIGNAL STRENGTH</span>
              <span className="or-strength-bar"><i style={{ width: `${regime.signal_strength}%`, background: strengthColor(regime.signal_strength_label) }} /></span>
              <span className="mono" style={{ color: strengthColor(regime.signal_strength_label) }}>{regime.signal_strength_label} <b className="num">{regime.signal_strength.toFixed(0)}</b><span style={{ color: "var(--faint)" }}> · 2위와 {regime.margin.toFixed(0)} 차</span></span>
            </div>
          </div>
          <p className="or-headline">{regime.headline}</p>
          <p className="or-impl"><span className="or-k mono">MARKET IMPLICATION</span> {regime.implication}</p>
          {regime.oil_move.note ? <p className="or-oilnote mono">유가 관측: 브렌트 {sg(regime.oil_move.brent_z)}σ · WTI {sg(regime.oil_move.wti_z)}σ — {regime.oil_move.note}</p> : (
            <p className="or-oilnote mono">유가 관측: 브렌트 {sg(regime.oil_move.brent_z)}σ · WTI {sg(regime.oil_move.wti_z)}σ · 방향 {regime.oil_move.direction}</p>
          )}
          <div className="or-chips">
            {ordered.map((d) => (
              <span key={d.id} className={`or-chip${d.id === regime.dominant ? " on" : ""}`} style={{ borderColor: (STATUS[d.status] ?? STATUS.UNCONFIRMED!).color }} title={d.status_reason}>
                {d.label} <b className="num">{sg(d.score, 0)}</b> <small>{d.status}</small>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* 1a. STATE HISTORY · 1M — 저장된 daily snapshot 의 sequence (지배 driver · 점수 · 확신). 과거 고정, 오늘 LIVE */}
      <DailyHistoryPanel tab="oil_regime" title="Oil State History · 1M" scenario={snapshot.scenario ?? undefined} asOf={snapshot.as_of} />

      {/* 2. WHAT IS DRIVING OIL? */}
      <section className="panel span-2">
        <header className="panel-head"><h2 className="panel-title">What Is Driving Oil?</h2><div className="panel-note mono">evidence score · −100 하락 압력 … +100 상승 압력</div></header>
        <div className="panel-body or-drivers">
          {ordered.map((d) => <DriverBar key={d.id} d={d} dominant={d.id === regime.dominant} />)}
        </div>
      </section>

      {/* 3. MARKET CONFIRMATION */}
      <section className="panel">
        <header className="panel-head"><h2 className="panel-title">Market Confirmation</h2><div className="panel-note mono"><span style={{ color: "var(--ok)" }}>확인 {confirms}</span> · <span style={{ color: "var(--down)" }}>반박 {contradicts}</span> · {dom.label} 기준</div></header>
        <div className="panel-body or-confs" role="table" aria-label="시장 확인">
          {regime.confirmations.map((r) => <ConfRow key={r.key} r={r} />)}
        </div>
      </section>

      {/* 4. NARRATIVE vs PRICE */}
      <section className="panel span-3">
        <header className="panel-head"><h2 className="panel-title">Narrative vs Price</h2><div className="panel-note mono">뉴스 톤 / 가격 모멘텀 (−100~+100) · 괴리 엔진 심각도</div></header>
        <div className="panel-body or-nar">
          {regime.narrative.map((n) => (
            <div key={n.theme_id} className="or-nar-row" data-testid="narrative-row">
              <span className="or-nar-name">{n.name}</span>
              <span className="num mono or-nar-vals">뉴스 <b className={n.news !== null && n.news >= 0 ? "up" : "down"}>{sg(n.news, 0)}</b> · 가격 <b className={n.price !== null && n.price >= 0 ? "up" : "down"}>{sg(n.price, 0)}</b>{n.divergence_severity !== null ? <span style={{ color: "var(--warn)" }}> · 괴리 {n.divergence_severity.toFixed(0)}</span> : null}</span>
              <span className="or-nar-sent">{n.sentence}</span>
            </div>
          ))}
        </div>
      </section>

      {/* 5. WHAT TO WATCH NEXT */}
      <section className="panel span-3 or-watch">
        <header className="panel-head"><h2 className="panel-title">What To Watch Next</h2><div className="panel-note mono">지금 판단이 바뀌려면</div></header>
        <div className="panel-body">
          <ol className="or-watch-list">
            {regime.watch.map((w, i) => (
              <li key={i} data-testid="watch-item">
                <span className="or-watch-text">{w.text}</span>
                <span className="or-watch-meta mono">{w.metric} 지금 <b className="num">{w.current}</b> → 조건 {w.condition} → {w.effect}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 6. Diagnostics */}
      <details className="panel span-3 or-diag" data-testid="oil-diagnostics">
        <summary className="panel-head"><h2 className="panel-title">Diagnostics / Historical Pattern Match</h2><div className="panel-note mono">판정 룰 · 시나리오 서명 대조 — 접어 둔 내부 진단</div></summary>
        <div className="panel-body">
          <div className="or-diag-grid">
            <div>
              <div className="or-k mono">판정 룰 — {check.label ?? "라벨 없음"}</div>
              {hyp ? <RuleTrace hypothesis={hyp} /> : <div className="sv-muted">가설 없음</div>}
              <div className="sv-muted" style={{ marginTop: 6 }}>지금 판정 {snapshot.market_state.primary_label} {snapshot.market_state.confidence.toFixed(0)}% · 가설 점수 {check.hypothesis_score === null ? "–" : check.hypothesis_score.toFixed(2)}</div>
            </div>
            <div>
              <div className="or-k mono">driver 증거 전체</div>
              {regime.drivers.map((d) => (
                <div key={d.id} className="or-diag-ev mono">
                  <b>{d.label}</b> {sg(d.score, 0)} · {d.evidence.map((e) => e.available ? `${evText(e)} → ${sg(e.contribution, 2)}` : `${e.label} 결측`).join(" · ")}
                </div>
              ))}
            </div>
          </div>
          <div className="or-k mono" style={{ marginTop: 12 }}>시나리오 서명 대조 · 실데이터 일치도 <span style={{ color: scoreColor(check.match_score) }}>{check.match_score.toFixed(0)}%</span></div>
          <ScenarioCheckPanel check={check} />
          <div className="sh-note" style={{ marginTop: 8 }}>{regime.note}</div>
        </div>
      </details>
    </div>
  );
}
