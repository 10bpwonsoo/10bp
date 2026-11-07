import type { ScenarioCheck, ScenarioCheckRow } from "../api/types";
import { LABEL_KO } from "./StateHistoryStrip";

/**
 * 시나리오 점검 — 모의 탭을 실데이터로 바꾼 것.
 * 시나리오의 충격 서명(모의 데이터 마지막 봉의 목표 z)을 지금 실데이터의 z 에 대어, 얼마나 닮았는지와
 * 그 시나리오가 가정하는 판정 룰이 실제로 걸렸는지를 보여준다. 숫자는 서버(scenario_checks.yaml)가 만들고
 * 화면은 그대로 그린다. 예측이 아니다.
 */
const STATUS_KO: Record<ScenarioCheckRow["status"], string> = {
  agree: "일치", weak: "미달", oppose: "반대", quiet_ok: "조용", quiet_broken: "요동", missing: "결측",
};
const STATUS_COLOR: Record<ScenarioCheckRow["status"], string> = {
  agree: "var(--ok)", weak: "var(--warn)", oppose: "var(--down)", quiet_ok: "var(--ok)", quiet_broken: "var(--warn)", missing: "var(--faint)",
};
const LAYER_KO = { market: "", alternative: "대체", stock: "종목", theme: "테마" } as const;
const sg = (v: number | null, d = 1) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);

export function scoreColor(score: number): string {
  return score >= 70 ? "var(--ok)" : score >= 45 ? "var(--warn)" : "var(--muted)";
}

export function ScenarioCheckPanel({ check }: { check: ScenarioCheck }) {
  const rows = [...check.rows].sort((a, b) => (a.status === "missing" ? 1 : 0) - (b.status === "missing" ? 1 : 0) || b.weight - a.weight);
  return (
    <div className="sc" data-testid="scenario-check" data-scenario={check.name}>
      <div className="sc-head">
        <span className="sc-score num" style={{ color: scoreColor(check.match_score) }}>{check.match_score.toFixed(0)}%</span>
        <span className="sc-title">
          <b>{check.title}</b>
          <span className="sc-sub">{check.match_label} · 서명 {check.rows.length}개 중 {check.evaluated}개 평가 · 일치 {check.agree} · 미달 {check.weak} · 반대 {check.oppose}
            {check.quiet_ok + check.quiet_broken > 0 ? ` · 조용 ${check.quiet_ok}/${check.quiet_ok + check.quiet_broken}` : ""}
            {check.missing.length ? ` · 결측 ${check.missing.length}` : ""}</span>
        </span>
        <span className="sc-rule mono" data-testid="scenario-rule">
          {check.label === null ? (
            <span style={{ color: "var(--faint)" }}>판정 라벨 없는 시나리오</span>
          ) : check.label === "NEUTRAL" ? (
            <span style={{ color: check.current_label === "NEUTRAL" ? "var(--ok)" : "var(--muted)" }}>평시 = 룰 없음 · 지금 {LABEL_KO[check.current_label] ?? check.current_label}</span>
          ) : (
            <>
              <span style={{ color: check.require_passed ? "var(--ok)" : "var(--down)" }}>{check.require_passed ? "✓" : "·"} require</span>{" "}
              <span style={{ color: "var(--ink-2)" }}>{check.require_expression ?? "—"}</span>{" "}
              <span className="num" style={{ color: "var(--muted)" }}>{check.require_observed === null ? "데이터 없음" : sg(check.require_observed, 2)}</span>
              <span style={{ color: "var(--muted)" }}> · 가설 {check.hypothesis_score === null ? "–" : check.hypothesis_score.toFixed(2)} · 지금 {LABEL_KO[check.current_label] ?? check.current_label} {check.current_confidence.toFixed(0)}%</span>
            </>
          )}
        </span>
      </div>
      <p className="sc-verdict">{check.verdict}</p>
      {check.themes.length > 0 && (
        <div className="sc-themes mono">
          {check.themes.map((t) => (
            <span key={t.theme_id} className="sc-theme" title="테마 가격 점수 / 뉴스 톤">
              {t.name} <b className={`num ${t.theme_score >= 0 ? "up" : "down"}`}>{sg(t.theme_score, 0)}</b>
              <span style={{ color: "var(--muted)" }}> / 뉴스 {t.news_sentiment === null ? "없음" : sg(t.news_sentiment, 0)}</span>
            </span>
          ))}
        </div>
      )}
      <div className="sc-rows" role="table" aria-label="시나리오 서명 대 실데이터">
        {rows.map((r) => (
          <div key={r.instrument_id} className={`sc-row ${r.status}`} role="row" data-status={r.status} title={`${r.instrument_id} · 하루 ${sg(r.actual_z_1d)}σ · 5일 ${sg(r.actual_z_5d)}σ · 가중치 ${r.weight.toFixed(2)}`}>
            <span className="sc-r-label">{r.label}{r.layer !== "market" ? <i className="sc-layer">{LAYER_KO[r.layer]}</i> : null}</span>
            <span className="num sc-r-exp">기대 {r.layer === "theme" ? sg(r.expected_z, 0) : `${sg(r.expected_z)}σ`}</span>
            <span className="sc-r-bar" aria-hidden="true"><i style={{ width: `${Math.round(r.ratio * 100)}%`, background: STATUS_COLOR[r.status] }} /></span>
            <span className="num sc-r-act" style={{ color: STATUS_COLOR[r.status] }}>
              {r.used_z === null ? "결측" : r.layer === "theme" ? sg(r.used_z, 0) : `${sg(r.used_z)}σ`}{r.used_window ? <small> {r.used_window}일</small> : null}
            </span>
            <span className="sc-r-status" style={{ color: STATUS_COLOR[r.status] }}>{STATUS_KO[r.status]}</span>
          </div>
        ))}
      </div>
      <div className="sc-note">{check.note}</div>
    </div>
  );
}
