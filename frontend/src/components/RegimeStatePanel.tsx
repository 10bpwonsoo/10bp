import type { CkRegimeState } from "../api/types";

/**
 * 공식 regime Exit / Entry 상태 (exit_entry_v2, 2026-11-09 Daily Snapshot~).
 * 화면만 보고 바로 알 수 있어야 하는 다섯 가지: ① 지금 공식 regime ② 지금 후보 ③ 공식 regime 이 유지 중인지 · 깨지는지
 * ④ 이탈(EXIT) 며칠째 ⑤ 새 후보 진입(ENTRY) 며칠째. 숫자는 서버가 정했다 — 화면은 그리기만 한다.
 */
export const KEY_TEXT: Record<string, string> = {
  risk_on: "RISK-ON", neutral: "NEUTRAL / MIXED", liquidity_stress: "LIQUIDITY STRESS", growth: "GROWTH SHOCK", inflation: "INFLATION SHOCK",
  policy: "POLICY DRIVEN", geopolitical: "GEOPOLITICAL RISK",
};
export const KEY_COLOR: Record<string, string> = {
  risk_on: "var(--lbl-risk-on)", neutral: "var(--lbl-neutral)", growth: "var(--lbl-growth)", inflation: "var(--lbl-inflation)",
  policy: "var(--lbl-policy)", liquidity_stress: "var(--lbl-liquidity)", geopolitical: "var(--lbl-geopolitical)",
};
const RAW_TEXT: Record<string, string> = {
  RISK_ON: "RISK-ON", RISK_OFF: "RISK-OFF", LIQUIDITY_STRESS: "LIQUIDITY STRESS", INFLATION_SHOCK: "INFLATION SHOCK", GROWTH_SHOCK: "GROWTH SHOCK",
  GEOPOLITICAL_RISK: "GEOPOLITICAL RISK", POLICY_DRIVEN: "POLICY DRIVEN", NEUTRAL: "NEUTRAL / MIXED",
};
export const SUPPORT_COLOR: Record<string, string> = { SUPPORTED: "var(--ok)", WEAKENING: "var(--warn)", BROKEN: "var(--crit)", NA: "var(--faint)" };
const SUPPORT_KO: Record<string, string> = { SUPPORTED: "핵심 근거 유지", WEAKENING: "근거 약해짐 — 이탈 일수에 들어간다", BROKEN: "근거 깨짐 — 이탈 일수에 들어간다", NA: "" };
const EQ_COLOR: Record<string, string> = { STRONG: "var(--ok)", CONFIRMED: "var(--ok)", PARTIAL: "var(--warn)", MIXED: "var(--warn)", CONTRADICTED: "var(--crit)", UNAVAILABLE: "var(--faint)" };

export const isV2 = (s: CkRegimeState | null | undefined): s is CkRegimeState => !!s && s.logic_version !== "legacy";
export const keyText = (k: string | null | undefined) => (k ? KEY_TEXT[k] ?? k.toUpperCase() : "–");
export const keyColor = (k: string | null | undefined) => (k ? KEY_COLOR[k] ?? "var(--ink)" : "var(--muted)");
const md = (d: string | null | undefined) => (d ? d.slice(5).replace("-", "/") : "");

/** EXIT 칸 — 공식이 방향성 regime 이면 n / need, 이날 해제됐으면 CONFIRMED, 공식이 Neutral 이면 직전 해제 기록 */
export function exitText(s: CkRegimeState): { text: string; tone: string } {
  if (s.changed && s.change_kind === "exit") return { text: `${keyText(s.exited_regime)} EXIT CONFIRMED`, tone: "var(--accent)" };
  if (s.official === "neutral") {
    return s.released_label ? { text: `${keyText(labelKey(s.released_label))} EXIT CONFIRMED${s.released_on ? ` · ${md(s.released_on)}` : ""}`, tone: "var(--muted)" }
      : { text: "해당 없음 (공식 Neutral)", tone: "var(--faint)" };
  }
  return { text: `${Math.min(s.exit_streak, s.exit_required)} / ${s.exit_required} DAYS`, tone: s.exit_streak > 0 ? "var(--warn)" : "var(--muted)" };
}

/** ENTRY 칸 — 진입 후보가 있으면 후보 n / need, 이날 확정됐으면 CONFIRMED, 없으면 — */
export function entryText(s: CkRegimeState): { regime: string | null; text: string; tone: string } {
  if (s.changed && s.change_kind === "entry") return { regime: s.official, text: "CONFIRMED", tone: "var(--accent)" };
  if (s.entry_regime) return { regime: s.entry_regime, text: `${Math.min(s.entry_streak, s.entry_required)} / ${s.entry_required} DAYS`, tone: "var(--warn)" };
  if (s.candidate === s.official) return { regime: null, text: "진입 대기 후보 없음 — 오늘 후보가 공식과 같다", tone: "var(--muted)" };
  return { regime: null, text: "진입 대기 후보 없음", tone: "var(--muted)" };
}

/** 라벨('Liquidity Stress / Risk-Off') → taxonomy key */
export function labelKey(label: string | null | undefined): string {
  const l = (label ?? "").toLowerCase();
  if (l.startsWith("liquidity")) return "liquidity_stress";
  if (l.startsWith("risk-on")) return "risk_on";
  if (l.startsWith("neutral")) return "neutral";
  if (l.startsWith("growth")) return "growth";
  if (l.startsWith("inflation")) return "inflation";
  if (l.startsWith("policy")) return "policy";
  if (l.startsWith("geopolitical")) return "geopolitical";
  return l;
}

const Row = ({ k, children, testid }: { k: string; children: React.ReactNode; testid?: string }) => (
  <div className="ck-st-row" data-testid={testid}><span className="ck-k">{k}</span><span className="ck-st-v">{children}</span></div>
);

/** MARKET NOW — 공식 아래 상태 표. legacy 저장본은 그리지 않는다(예전 RAW SIGNAL 줄이 그대로 보인다) */
export function RegimeStateGrid({ s }: { s: CkRegimeState }) {
  const ex = exitText(s); const en = entryText(s);
  return (
    <div className="ck-st mono" data-testid="ck-now-state" data-support={s.support} data-exit={s.exit_streak} data-entry={s.entry_streak}>
      <Row k={s.counted ? "Current candidate" : "Live candidate"} testid="ck-now-candidate">
        <b style={{ color: keyColor(s.candidate) }}>{keyText(s.candidate)}</b>{!s.counted ? <small> 장중 — 일수에 넣지 않음</small> : null}
      </Row>
      {s.official !== "neutral" ? (
        <Row k={`${keyText(s.official)} support`} testid="ck-now-support">
          <b style={{ color: SUPPORT_COLOR[s.support] }}>{s.support}</b>{SUPPORT_KO[s.support] ? <small> {SUPPORT_KO[s.support]}</small> : null}
        </Row>
      ) : s.released_label ? (
        <Row k="Previous official" testid="ck-now-prev-official"><b style={{ color: keyColor(labelKey(s.released_label)) }}>{keyText(labelKey(s.released_label))}</b></Row>
      ) : null}
      <Row k="Exit confirmation" testid="ck-now-exit"><b style={{ color: ex.tone }}>{ex.text}</b></Row>
      <Row k="Entry confirmation" testid="ck-now-entry">
        {en.regime ? <b style={{ color: keyColor(en.regime) }}>{keyText(en.regime)} </b> : null}<b style={{ color: en.tone }}>{en.text}</b>
      </Row>
      <Row k="Raw signal" testid="ck-now-rawsig">
        <b>{s.raw_signal ? RAW_TEXT[s.raw_signal] ?? s.raw_signal : "–"}</b>{s.raw_signal ? <small> 정량 · {s.raw_persistence_days}D 연속</small> : null}
      </Row>
      {s.equity ? (
        <Row k={`Equity vs ${keyText(s.official)}`}>
          {(["us", "kr", "global"] as const).map((m) => <span key={m} className="ck-st-eq">{m === "kr" ? "KOREA" : m.toUpperCase()} <b style={{ color: EQ_COLOR[s.equity![m]] ?? "var(--ink)" }}>{s.equity![m]}</b></span>)}
        </Row>
      ) : null}
      {s.support_reasons.length && s.official !== "neutral" ? (
        <details className="ck-st-why"><summary>support 근거</summary><ul>{s.support_reasons.map((r) => <li key={r}>{r}</li>)}</ul></details>
      ) : null}
    </div>
  );
}

/** MARKET REGIME HISTORY 우측 — CURRENT 는 공식 기준만. 후보 · 진입 · 이탈 · raw 는 따로 */
export function HistoryStateSummary({ s, previousLabel, status, statusKo }: { s: CkRegimeState; previousLabel: string | null; status: string; statusKo: string }) {
  const ex = exitText(s); const en = entryText(s);
  const stColor = status === "CHANGED" ? "var(--accent)" : status === "CONFIRMED" ? "var(--ok)" : "var(--warn)";
  return (
    <div className="ck-h-st mono" data-testid="ck-h-state">
      {en.regime && !(s.changed && s.change_kind === "entry") ? (
        <div className="ck-h-st-r" data-testid="ck-h-pending"><span className="ck-k">Pending candidate</span><b style={{ color: keyColor(en.regime) }}>{keyText(en.regime)}</b></div>
      ) : null}
      <div className="ck-h-st-r" data-testid="ck-h-entry"><span className="ck-k">Entry</span><b style={{ color: en.tone }}>{en.text}</b></div>
      <div className="ck-h-st-r" data-testid="ck-h-exit"><span className="ck-k">{s.official !== "neutral" ? `Exit · ${keyText(s.official)} ${s.support}` : "Exit"}</span><b style={{ color: ex.tone }}>{ex.text}</b></div>
      <div className="ck-h-st-r"><span className="ck-k">Previous official</span><b>{previousLabel ?? "–"}</b></div>
      <div className="ck-h-st-r" data-testid="ck-h-rawsig"><span className="ck-k">Raw signal</span><b>{s.raw_signal ? RAW_TEXT[s.raw_signal] ?? s.raw_signal : keyText(s.candidate)}</b>{s.raw_signal ? <small>{s.raw_persistence_days}D</small> : null}</div>
      <div className="ck-h-st-r" data-testid="ck-h-tstatus"><span className="ck-k">Transition status</span><b style={{ color: stColor }}>{status === "TRANSITION_WATCH" ? "WATCH" : status.replace(/_/g, " ")}</b></div>
      {statusKo ? <div className="ck-h-raw-ko">{statusKo}</div> : null}
    </div>
  );
}
