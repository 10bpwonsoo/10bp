import { useState } from "react";
import type {
  RatesRegime, RatesDriverScore, RatesEvidenceItem, CurrentRatesAnalysis, PolicyMacroEvents, PolicyDecision, MacroRelease, RecentEventItem, UpcomingEvent, EventImpact, EventSource, RatesTop,
} from "../api/types";
import { strengthColor } from "./OilRegimeView";

/**
 * 금리 탭 상단 정리 (2026-10-12) — 하단 패널(Inflation Pressure 이하)은 그대로 두고 위쪽 세 영역만.
 *   ① RATES REGIME: 판정 + 금리 방향 + 주도 driver + 신뢰도 + MARKET READ(≤2문장) + DRIVER READ, 기존 chip·Transmission 유지
 *   ② CURRENT RATES ANALYSIS: Driver · Curve · Real Yield · Breakeven 네 칸 + 한 줄, 그 아래 compact WHAT IS DRIVING RATES?(누르면 근거)
 *   ③ POLICY & MACRO EVENTS: regime 연결 → RECENT(EVENT → SURPRISE → RATES REACTION) · 중앙은행 · UPCOMING
 * 문장·판정·반응 bp 는 전부 서버가 만든다. 화면은 그리기만 한다.
 */
export const DRV_STATUS: Record<string, { ko: string; color: string }> = {
  CONFIRMED: { ko: "확인됨", color: "var(--ok)" },
  UNCONFIRMED: { ko: "미확인", color: "var(--warn)" },
  CONTRADICTED: { ko: "반박됨", color: "var(--down)" },
};
const IMPACT: Record<EventImpact, { ko: string; color: string }> = {
  SUPPORTED: { ko: "현재 판단 지지", color: "var(--ok)" },
  CHALLENGED: { ko: "현재 판단에 도전", color: "var(--warn)" },
  NEUTRAL: { ko: "중립", color: "var(--muted)" },
};
const SURPRISE_COLOR: Record<string, string> = {
  HOT: "var(--up)", STRONG: "var(--up)", HAWKISH: "var(--up)", COOL: "var(--down)", WEAK: "var(--down)", DOVISH: "var(--down)", INLINE: "var(--muted)", NEUTRAL: "var(--muted)", MIXED: "var(--warn)", "N/A": "var(--faint)",
};
const MOVE_COLOR: Record<string, string> = { up: "var(--up)", down: "var(--down)", flat: "var(--muted)", missing: "var(--faint)", none: "var(--ink)" };
const sg = (v: number | null, d = 0) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);
const bp = (v: number | null) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(0)}bp`);
const md = (iso: string | null) => (iso ? `${iso.slice(5, 7)}/${iso.slice(8, 10)}` : "–");
const fmtVal = (v: number | null, unit: string) => (v === null ? "–" : unit === "k" ? `${v >= 0 ? "+" : ""}${v.toFixed(0)}k` : `${v.toFixed(1)}${unit}`);
const evText = (e: RatesEvidenceItem) => (e.kind === "news" ? `${e.label} ${sg(e.value, 0)}` : `${e.label} ${sg(e.value, 1)}σ${e.window === 5 ? " (5일)" : ""}`);

/** ① REGIME 카드 몸통 — 큰 판정은 그대로, 바로 아래 방향 · 주도 driver · 물가 여부 · 신뢰도 */
export function RatesRegimeHead({ regime }: { regime: RatesRegime }) {
  const t = regime.top!;
  const rm = regime.rate_move;
  const [main] = regime.regime_label.split(" — ");
  const infl = DRV_STATUS[regime.inflation_status] ?? DRV_STATUS.UNCONFIRMED!;
  const dirColor = rm.direction === "up" ? "var(--up)" : rm.direction === "down" ? "var(--down)" : "var(--muted)";
  const ordered = [...regime.drivers].sort((a, b) => (a.status === "CONFIRMED" ? 0 : 1) - (b.status === "CONFIRMED" ? 0 : 1) || Math.abs(b.score) - Math.abs(a.score));
  return (
    <div className="rt-head" data-testid="rates-top">
      <div className="rt-main">
        <span className="rr-k mono">RATES REGIME</span>
        <span className="rr-label" data-testid="rates-regime-label">{main}</span>
        <div className="rt-dir mono" data-testid="yield-direction" data-direction={t.direction}>
          <span className="rr-k">YIELD DIRECTION</span>
          <b style={{ color: dirColor }}>{t.direction_arrow} {t.direction_en}</b>
          <span className="rt-seg">{t.segment} {t.direction_arrow}</span>
        </div>
        <div className="rt-driver mono" data-testid="driver-title">{t.driver_title}</div>
      </div>
      <div className="rt-facts" role="list">
        <div className="rt-fact" role="listitem" data-testid="rate-move">
          <span className="rr-k mono">10Y</span>
          <b className="num rt-big">{rm.level === null ? "–" : `${rm.level.toFixed(2)}%`}</b>
          <span className="num mono" style={{ color: dirColor }}>5D {bp(rm.change_5d_bp)} · {sg(rm.z, 1)}σ{rm.window === 5 ? " (5일)" : ""}</span>
        </div>
        <div className="rt-fact" role="listitem" title={`|driver 점수| ${regime.signal_strength.toFixed(0)} · 2위와 격차 ${regime.margin.toFixed(0)}`}>
          <span className="rr-k mono">CONFIDENCE · EVIDENCE</span>
          <b className="mono rt-big" style={{ color: strengthColor(regime.signal_strength_label) }}>{regime.signal_strength_label} · <span className="num">{regime.signal_strength.toFixed(0)}</span></b>
          <span className="rr-strength-bar"><i style={{ width: `${regime.signal_strength}%`, background: strengthColor(regime.signal_strength_label) }} /></span>
        </div>
        <div className="rt-fact" role="listitem">
          <span className="rr-k mono">PRIMARY DRIVER</span>
          <b className="rt-mid">{t.primary.label}</b>
          <span className="mono" style={{ color: (DRV_STATUS[t.primary.status] ?? DRV_STATUS.UNCONFIRMED!).color }}>{t.primary.status} · {(DRV_STATUS[t.primary.status] ?? DRV_STATUS.UNCONFIRMED!).ko}</span>
        </div>
        <div className="rt-fact" role="listitem" data-testid="inflation-status">
          <span className="rr-k mono">INFLATION REPRICING</span>
          <b className="mono rt-mid" style={{ color: infl.color }}>{regime.inflation_status === "UNCONFIRMED" ? "NOT CONFIRMED" : regime.inflation_status}</b>
          <span className="mono" style={{ color: infl.color }}>{infl.ko}</span>
        </div>
      </div>
      <MarketRead t={t} />
      <div className="rt-dread mono" data-testid="driver-read">
        <span className="rr-k">DRIVER READ</span>
        <span className="rt-dr"><em>PRIMARY</em> {t.primary.label} <b className="num" style={{ color: t.primary.score >= 0 ? "var(--up)" : "var(--down)" }}>{sg(t.primary.score)}</b></span>
        {t.counter ? <span className="rt-dr" data-testid="driver-counter"><em>COUNTER</em> {t.counter.label} <b className="num" style={{ color: t.counter.score >= 0 ? "var(--up)" : "var(--down)" }}>{sg(t.counter.score)}</b></span> : null}
        {t.not_confirmed.length ? <span className="rt-dr" data-testid="driver-nc"><em>NOT CONFIRMED</em> {t.not_confirmed_text}</span> : null}
      </div>
      <div className="rr-chips">
        {ordered.map((d) => (
          <span key={d.id} className={`rr-chip${d.id === regime.dominant ? " on" : ""}`} style={{ borderColor: (DRV_STATUS[d.status] ?? DRV_STATUS.UNCONFIRMED!).color }} title={d.status_reason}>
            {d.label} <b className="num">{sg(d.score)}</b> <small>{d.status}</small>
          </span>
        ))}
      </div>
      <p className="rr-impl rt-trans"><span className="rr-k mono">TRANSMISSION</span> {regime.implication}</p>
      <details className="rt-more"><summary className="mono">판정 근거 문장</summary><p className="rr-headline">{regime.headline}</p></details>
    </div>
  );
}

/** compact WHAT IS DRIVING RATES? — 기본은 결론(순위 · 점수 · 상태 · 한 줄), 누르면 근거 데이터 */
function DriverLine({ d, rank, line, dominant }: { d: RatesDriverScore; rank: number; line: string; dominant: boolean }) {
  const [open, setOpen] = useState(false);
  const st = DRV_STATUS[d.status] ?? DRV_STATUS.UNCONFIRMED!;
  const ev = d.evidence.filter((e) => e.available);
  return (
    <div className={`rt-drow${dominant ? " on" : ""}${open ? " open" : ""}`} data-testid="rates-driver" data-id={d.id} data-status={d.status}>
      <button type="button" className="rt-drow-btn" aria-expanded={open} onClick={() => setOpen(!open)} title={d.status_reason}>
        <span className="rt-rank mono">{rank}</span>
        <span className="rt-dname">{d.label}<small> {d.label_ko}</small></span>
        <b className="num rt-dscore" style={{ color: d.score >= 0 ? "var(--up)" : "var(--down)" }}>{sg(d.score)}</b>
        <span className="mono rt-dst" style={{ color: st.color }}>{d.status}</span>
        <span className="rt-caret mono" aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {line ? <div className="rt-dline">{line}</div> : null}
      {open ? (
        <div className="rt-dev mono" data-testid="driver-evidence">
          <div className="rt-dev-reason">{d.status_reason}</div>
          {ev.length === 0 ? <div style={{ color: "var(--faint)" }}>확보한 근거 계열이 없다 — 0 이 아니라 결측</div> : ev.map((e) => (
            <div key={e.id} className="rt-dev-row"><span>{e.label}</span><b className="num">{e.kind === "news" ? sg(e.value, 0) : `${sg(e.value, 1)}σ`}</b><span style={{ color: "var(--faint)" }}>{e.window === 5 ? "5일" : e.kind === "news" ? "뉴스 톤" : "하루"} · 기여 {sg(e.contribution, 2)}</span></div>
          ))}
          {d.evidence.some((e) => !e.available) ? <div style={{ color: "var(--faint)" }}>결측: {d.evidence.filter((e) => !e.available).map((e) => e.label).join(" · ")}</div> : null}
          <div style={{ color: "var(--faint)" }}>확보율 {(d.coverage * 100).toFixed(0)}% · {ev.slice(0, 3).map(evText).join(" · ")}</div>
        </div>
      ) : null}
    </div>
  );
}

/** ② CURRENT RATES ANALYSIS — 네 칸 + 한 줄 + compact driver 표 */
export function CurrentRatesAnalysisPanel({ regime, analysis }: { regime: RatesRegime; analysis: CurrentRatesAnalysis }) {
  const ordered = [...regime.drivers].sort((a, b) => (a.status === "CONFIRMED" ? 0 : 1) - (b.status === "CONFIRMED" ? 0 : 1) || Math.abs(b.score) - Math.abs(a.score));
  const lines = regime.top?.driver_lines ?? {};
  return (
    <section className="panel span-3 rt-ca" data-testid="current-rates-analysis">
      <header className="panel-head"><h2 className="panel-title">Current Rates Analysis</h2><div className="panel-note mono">흩어진 금리 판단의 요약 — 세부 수치는 아래 Treasury Curve · Decomposition</div></header>
      <div className="panel-body">
        <div className="rt-tiles">
          {analysis.tiles.map((x) => (
            <div key={x.key} className="rt-tile" data-testid="analysis-tile" data-key={x.key} data-move={x.move} title={x.detail}>
              <span className="rr-k mono">{x.label}</span>
              <b className="rt-tval" style={{ color: MOVE_COLOR[x.move] }}>{x.arrow ? `${x.arrow} ` : ""}{x.value}</b>
              {x.sub ? <span className="mono rt-tsub">{x.sub}</span> : null}
            </div>
          ))}
        </div>
        <p className="rt-sent" data-testid="analysis-sentence">{analysis.sentence}</p>
        <div className="rt-wd">
          <div className="rt-wd-head"><span className="panel-title">What Is Driving Rates?</span><span className="mono rt-wd-note">evidence score −100 하락 압력 … +100 상승 압력 · 누르면 근거</span></div>
          {ordered.map((d, i) => <DriverLine key={d.id} d={d} rank={i + 1} line={lines[d.id] ?? ""} dominant={d.id === regime.dominant} />)}
        </div>
      </div>
    </section>
  );
}

function Sources({ sources }: { sources: EventSource[] }) {
  if (!sources.length) return null;
  return <div className="rt-src mono">{sources.map((s, i) => <a key={i} href={s.url} target="_blank" rel="noreferrer">{s.publisher || "source"} · {s.title}</a>)}</div>;
}

function ImpactChip({ impact, testid }: { impact: EventImpact | null; testid?: string }) {
  if (!impact) return <span className="rt-imp mono" style={{ color: "var(--faint)" }} data-testid={testid} data-impact="none">CONTEXT</span>;
  const c = IMPACT[impact];
  return <span className="rt-imp mono" style={{ color: c.color, borderColor: c.color }} data-testid={testid} data-impact={impact} title={c.ko}>{impact}</span>;
}

function Chain({ chain }: { chain: string[] }) {
  return <div className="rt-chain mono" data-testid="event-chain">{chain.map((c, i) => <span key={i}>{i ? <i aria-hidden="true">→</i> : null}{c}</span>)}</div>;
}

function ReleaseDetail({ r }: { r: MacroRelease }) {
  return (
    <div className="rt-edet" data-testid="release-detail">
      <div className="rt-mtbl mono" role="table">
        <div className="rt-mrow rt-mth" role="row"><span>{r.period}</span><span>ACTUAL</span><span>CONSENSUS</span><span>PRIOR</span></div>
        {r.measures.map((m) => (
          <div key={m.key} className={`rt-mrow${m.judged && m.diff !== null && m.diff !== 0 ? " hit" : ""}`} role="row" title={m.note}>
            <span>{m.label}</span><b className="num">{fmtVal(m.actual, m.unit)}</b><span className="num">{fmtVal(m.consensus, m.unit)}</span><span className="num">{fmtVal(m.prior, m.unit)}</span>
          </div>
        ))}
      </div>
      <div className="rt-ekv mono"><span>SURPRISE 근거</span> {r.surprise_basis}{r.consensus_source ? ` · 컨센서스 ${r.consensus_source}` : ""}</div>
      <div className="rt-ekv mono"><span>RATES REACTION</span> 2Y <b>{bp(r.reaction.us2y_bp)}</b> · 10Y <b>{bp(r.reaction.us10y_bp)}</b> <em>{r.reaction.note}</em></div>
      <div className="rt-ekv"><span className="mono">REGIME IMPACT</span> {r.regime.reason}</div>
      {r.note ? <div className="rt-ekv" style={{ color: "var(--muted)" }}>{r.note}</div> : null}
      {r.measures.some((m) => m.note) ? <div className="rt-ekv" style={{ color: "var(--faint)" }}>{r.measures.filter((m) => m.note).map((m) => `${m.label}: ${m.note}`).join(" · ")}</div> : null}
      <Sources sources={r.sources} />
    </div>
  );
}

function PolicyDetail({ p }: { p: PolicyDecision }) {
  const rows: [string, string][] = [
    ["Decision", `${p.decision_label} · ${md(p.date)}`], ["Previous Rate", p.previous_rate], ["Current Rate", `${p.current_rate} (${p.rate_label})`], ["Vote", p.vote || "확인 못 함"],
    ["Statement", p.statement], [p.bank === "FED" ? "Chair tone" : "Governor / President", p.chair], ["Projections", p.projections], ["Market path", p.market_path],
    ["Next meeting", p.next_meeting ? `${p.next_meeting_start ? `${md(p.next_meeting_start)}–` : ""}${md(p.next_meeting)}` : "–"], ["Market implication", p.implication],
  ];
  return (
    <div className="rt-edet" data-testid="policy-detail">
      {rows.filter(([, v]) => v).map(([k, v]) => <div key={k} className="rt-ekv"><span className="mono">{k}</span> {v}</div>)}
      {p.reaction ? <div className="rt-ekv mono"><span>RATES REACTION</span> 2Y <b>{bp(p.reaction.us2y_bp)}</b> · 10Y <b>{bp(p.reaction.us10y_bp)}</b> <em>{p.reaction.note}</em></div> : null}
      <div className="rt-ekv"><span className="mono">REGIME IMPACT</span> {p.regime.reason}</div>
      {p.tone_basis ? <div className="rt-ekv" style={{ color: "var(--muted)" }}>TONE 근거 — {p.tone_basis}</div> : null}
      <Sources sources={p.sources} />
    </div>
  );
}

function RecentCard({ it, ev, open, onToggle }: { it: RecentEventItem; ev: PolicyMacroEvents; open: boolean; onToggle: () => void }) {
  const rel = it.kind === "release" ? ev.releases.find((r) => r.key === it.key) : undefined;
  const pol = it.kind === "policy" ? ev.policy.find((p) => p.bank === it.key) : undefined;
  const head = rel?.measures.find((m) => m.actual !== null);
  const color = SURPRISE_COLOR[rel ? rel.surprise : (pol?.tone ?? "NEUTRAL")] ?? "var(--muted)";
  return (
    <div className={`rt-ev${open ? " open" : ""}`} data-testid="recent-event" data-key={it.key} data-kind={it.kind}>
      <button type="button" className="rt-ev-btn" aria-expanded={open} onClick={onToggle}>
        <span className="rt-ev-top">
          <span className="mono rt-ev-date">{md(it.date)}</span>
          <b className="rt-ev-title">{it.title}{rel ? <small> {rel.period.replace("-", ".")}</small> : null}</b>
          <span className="mono rt-ev-label" style={{ color, borderColor: color }}>{it.label}</span>
          <ImpactChip impact={it.impact} testid="event-impact" />
        </span>
        {head ? (
          <span className="rt-ev-nums mono">
            <span>ACTUAL <b className="num">{fmtVal(head.actual, head.unit)}</b></span><span>CONS <b className="num">{fmtVal(head.consensus, head.unit)}</b></span><span>PRIOR <b className="num">{fmtVal(head.prior, head.unit)}</b></span>
            <span className="rt-ev-mlab">{head.label}</span>
          </span>
        ) : pol ? <span className="rt-ev-nums mono"><span>RATE <b className="num">{pol.current_rate}</b></span><span>{pol.decision_label}</span></span> : null}
        <Chain chain={rel ? rel.chain : pol?.chain ?? []} />
        {rel ? <span className="rt-ev-read">{rel.read}</span> : pol ? <span className="rt-ev-read">{pol.line}</span> : null}
      </button>
      {open ? (rel ? <ReleaseDetail r={rel} /> : pol ? <PolicyDetail p={pol} /> : null) : null}
    </div>
  );
}

function BankCard({ p, open, onToggle }: { p: PolicyDecision; open: boolean; onToggle: () => void }) {
  const color = SURPRISE_COLOR[p.tone] ?? "var(--muted)";
  return (
    <div className={`rt-bank${open ? " open" : ""}`} data-testid="bank-card" data-bank={p.bank}>
      <button type="button" className="rt-bank-btn" aria-expanded={open} onClick={onToggle}>
        <b className="rt-bank-name">{p.name}</b>
        <span className="rt-bank-kv mono"><span>LAST</span><b>{p.decision}</b></span>
        <span className="rt-bank-kv mono"><span>RATE</span><b className="num">{p.current_rate}</b></span>
        <span className="rt-bank-kv mono"><span>TONE</span><b style={{ color }}>{p.tone}</b></span>
        <span className="rt-bank-kv mono"><span>NEXT</span><b className="num">{md(p.next_meeting)}</b></span>
        <span className="rt-bank-line">{p.line}</span>
      </button>
      {open ? <PolicyDetail p={p} /> : null}
    </div>
  );
}

function UpcomingRow({ u }: { u: UpcomingEvent }) {
  return (
    <li className="rt-up" data-testid="upcoming-event" data-importance={u.importance}>
      <span className="mono rt-up-imp" style={{ color: u.importance === "HIGH" ? "var(--accent)" : "var(--muted)" }}>{u.importance}</span>
      <b className="rt-up-name">{u.name}</b>
      <span className="mono num rt-up-date">{u.date_start ? `${md(u.date_start)}–` : ""}{md(u.date)}<small> D-{u.days_ahead}</small></span>
      {u.note ? <span className="rt-up-note">{u.note}</span> : null}
    </li>
  );
}

/** ③ POLICY & MACRO EVENTS */
export function PolicyMacroEventsPanel({ events }: { events: PolicyMacroEvents | null | undefined }) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [allRecent, setAllRecent] = useState(false);
  const [allUp, setAllUp] = useState(false);
  if (!events) {
    return (
      <section className="panel span-3 rt-events" data-testid="policy-macro-events">
        <header className="panel-head"><h2 className="panel-title">Policy &amp; Macro Events</h2><div className="panel-note">금리 방향을 바꿀 수 있는 최근 정책 결정과 주요 경제지표</div></header>
        <div className="panel-body"><div className="sv-muted" data-testid="events-empty">확인된 정책·지표 이벤트 파일이 없습니다 — 만들어 채우지 않습니다.</div></div>
      </section>
    );
  }
  const ev = events; const lk = ev.link;
  const recent = allRecent ? ev.recent : ev.recent.slice(0, ev.recent_default);
  const up = allUp ? ev.upcoming : ev.upcoming.slice(0, ev.upcoming_default);
  const toggle = (k: string) => setOpenKey(openKey === k ? null : k);
  return (
    <section className="panel span-3 rt-events" data-testid="policy-macro-events">
      <header className="panel-head"><h2 className="panel-title">Policy &amp; Macro Events</h2><div className="panel-note">금리 방향을 바꿀 수 있는 최근 정책 결정과 주요 경제지표</div></header>
      <div className="panel-body">
        {lk ? (
          <div className="rt-link" data-testid="regime-link" data-impact={lk.impact}>
            <span className="rt-link-kv mono"><span>CURRENT REGIME</span><b>{lk.current_driver}</b><em>금리 {lk.direction_ko}</em></span>
            <span className="rt-link-kv mono"><span>{lk.latest_label.toUpperCase()}</span><b style={{ color: SURPRISE_COLOR[lk.latest_surprise] }}>{lk.latest_surprise}</b></span>
            <span className="rt-link-kv mono"><span>REGIME IMPACT</span><ImpactChip impact={lk.impact} testid="link-impact" /></span>
            <span className="rt-link-sent">{lk.sentence}</span>
            <span className="rt-link-counts mono">최근 미국 이벤트 · SUPPORTED {lk.counts.SUPPORTED ?? 0} · CHALLENGED {lk.counts.CHALLENGED ?? 0} · NEUTRAL {lk.counts.NEUTRAL ?? 0}</span>
          </div>
        ) : null}
        <div className="rt-ev-grid">
          <div className="rt-ev-col">
            <div className="rt-sub mono">RECENT <span>EVENT → SURPRISE → RATES REACTION · 누르면 상세</span></div>
            {recent.map((it) => <RecentCard key={`${it.kind}-${it.key}`} it={it} ev={ev} open={openKey === `r-${it.key}`} onToggle={() => toggle(`r-${it.key}`)} />)}
            {ev.recent.length > ev.recent_default ? <button type="button" className="ck-more" data-testid="recent-all" onClick={() => setAllRecent(!allRecent)}>{allRecent ? "접기" : `View all ${ev.recent.length}`}</button> : null}
          </div>
          <div className="rt-ev-col">
            <div className="rt-sub mono">CENTRAL BANKS <span>최근 확인된 결정 · 누르면 상세</span></div>
            <div className="rt-banks">{ev.policy.map((p) => <BankCard key={p.bank} p={p} open={openKey === `b-${p.bank}`} onToggle={() => toggle(`b-${p.bank}`)} />)}</div>
            <div className="rt-sub mono" style={{ marginTop: 10 }}>UPCOMING <span>다음 주요 발표</span></div>
            <ul className="rt-ups">{up.map((u) => <UpcomingRow key={`${u.kind}-${u.date}`} u={u} />)}</ul>
            {ev.upcoming.length > ev.upcoming_default ? <button type="button" className="ck-more" data-testid="upcoming-all" onClick={() => setAllUp(!allUp)}>{allUp ? "접기" : `View all ${ev.upcoming.length}`}</button> : null}
          </div>
        </div>
        <div className="sh-note" style={{ marginTop: 8 }} data-testid="events-note">{ev.missing.length ? `확인하지 못해 비워 둔 값: ${ev.missing.join(" · ")}. ` : ""}금리 반응 = 발표일 미국채 일간 종가 − 직전 거래일 종가(FRED). 수집 {ev.collected}.</div>
      </div>
    </section>
  );
}

const kst = (iso: string | null | undefined): string => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d);
  const g = (k: string) => p.find((x) => x.type === k)?.value ?? "";
  return `${g("month")}/${g("day")} ${g("hour")}:${g("minute")} KST`;
};

/** MARKET READ — LLM 해석(검증 통과)이면 AI INTERPRETATION, 아니면 RULE-BASED 와 그 이유. 모델 이름은 보이지 않는다. */
function MarketRead({ t }: { t: RatesTop }) {
  const m = t.market_read_meta ?? null;
  const llm = m?.source === "llm";
  const tag = llm ? "AI INTERPRETATION" : "RULE-BASED";
  const sub = !m ? "" : llm ? [m.generator === "session" ? "세션 생성" : "", kst(m.generated_at)].filter(Boolean).join(" · ")
    : m.status === "pending" ? "AI 해석 생성 중" : m.status === "skipped" ? "AI 해석 생략" : "AI 해석 없음";
  return (
    <div className="rt-read" data-testid="rates-market-read" data-source={m?.source ?? "rule"} data-status={m?.status ?? "none"}>
      <div className="rt-read-head mono">
        <span className="rr-k">MARKET READ</span>
        <span className={`rt-src${llm ? " ai" : ""}`} data-testid="market-read-source" title={m?.reason || undefined}>{tag}{sub ? ` · ${sub}` : ""}</span>
        {llm && m?.themes_ko.length ? m.themes_ko.map((x) => <span key={x} className="rt-theme" data-testid="market-read-theme">{x}</span>) : null}
      </div>
      <p className="rt-read-text" data-testid="market-read-text">{t.market_read}</p>
      {m && !llm && m.reason ? <p className="rt-read-note" data-testid="market-read-reason">{m.reason}</p> : null}
      {llm && m?.data_caveat ? <p className="rt-read-note" data-testid="market-read-caveat">데이터 주의 — {m.data_caveat}</p> : null}
      {llm && m?.generator === "session" && m.reason ? <p className="rt-read-note" data-testid="market-read-reason">{m.reason}</p> : null}
    </div>
  );
}
