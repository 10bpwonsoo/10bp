import { useState } from "react";
import type { DailyHistory, DailyHistoryPoint, HistorySource } from "../api/types";
import { useDailyHistory as useDailyHistoryLazy } from "../api/useDailyHistory";

/**
 * Daily snapshot history (2026-10-07) — 모든 탭 공통 1M strip.
 * 각 날짜는 그 날짜의 저장 snapshot(RECORDED · BACKFILLED)에서만 읽는다. 오늘만 LIVE. 과거 색·점수·driver 는 저장 후 고정이고
 * 현재 모델이 과거를 다시 분류하지 않는다. 화면은 숫자를 만들지 않는다 — 서버가 준 sequence 를 그대로 그린다.
 */
export const SOURCE_KO: Record<HistorySource, string> = { RECORDED: "Recorded", BACKFILLED: "Backfilled", LIVE: "Live", RECOMPUTED: "Recomputed" };
const md = (iso: string) => iso.slice(5).replace("-", "/");
const sg = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "–" : `${v >= 0 && d >= 0 ? (v > 0 ? "+" : "") : ""}${v.toFixed(Math.max(0, d))}`);

/** 툴팁·상세의 출처 줄 — 'Backfilled · calculated 10/07 · model_v4 · rules_v6'. RECORDED 는 'Recorded' 와 시각만. */
export function sourceLine(source: HistorySource, calculatedAt: string | null | undefined, model: string, logic: string, locked?: boolean): string {
  const when = calculatedAt ? ` · calculated ${md(calculatedAt.slice(0, 10))}` : "";
  const ver = [model, logic].filter(Boolean).join(" · ");
  return `${SOURCE_KO[source] ?? source}${source === "BACKFILLED" || source === "RECOMPUTED" ? when : ""}${ver ? ` · ${ver}` : ""}${locked ? " · locked" : source === "LIVE" ? " · 확정 전" : ""}`;
}

function pointTitle(p: DailyHistoryPoint, h: DailyHistory): string {
  const head = `${p.date} · ${p.label}${p.label_ko ? ` (${p.label_ko})` : ""}${p.score !== null ? ` · ${h.score_label || "score"} ${sg(p.score, 0)}` : ""}${p.confidence !== null ? ` · ${p.confidence.toFixed(0)}%` : ""}`;
  const drv = p.drivers.length ? `주도: ${p.drivers.slice(0, 3).join(" · ")}` : "";
  const miss = p.missing.length ? `결측: ${p.missing.slice(0, 4).join(", ")}${p.missing.length > 4 ? " …" : ""}` : "";
  return [head, sourceLine(p.source, p.calculated_at, p.model_version, p.logic_version, p.locked), drv, miss].filter(Boolean).join("\n");
}

function Detail({ p, h, onClose }: { p: DailyHistoryPoint; h: DailyHistory; onClose: () => void }) {
  const comps = Object.entries(p.components).filter(([, v]) => v !== null).slice(0, 8);
  const detail = Object.entries(p.detail).filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0) && typeof v !== "object").slice(0, 6);
  return (
    <div className="dh-detail mono" data-testid="dh-detail">
      <div className="dh-detail-head"><b>{p.date}</b> <em style={{ color: h.palette[p.state] ?? "var(--lbl-neutral)" }}>{p.label}</em>{p.label_ko ? <span className="dh-ko">{p.label_ko}</span> : null}
        <span className="dh-src" data-testid="dh-source" data-source={p.source}>{sourceLine(p.source, p.calculated_at, p.model_version, p.logic_version, p.locked)}</span>
        <button type="button" className="ck-more" onClick={onClose}>닫기</button></div>
      <div className="dh-detail-grid">
        {p.score !== null ? <span>{h.score_label || "Score"} <b className="num">{sg(p.score, 0)}</b></span> : null}
        {p.confidence !== null ? <span>Confidence <b className="num">{p.confidence.toFixed(0)}%</b></span> : null}
        {p.coverage !== null ? <span>Coverage <b className="num">{(p.coverage * 100).toFixed(0)}%</b></span> : null}
        {detail.map(([k, v]) => <span key={k}>{k.replace(/_/g, " ")} <b>{String(v)}</b></span>)}
      </div>
      {comps.length ? <div className="dh-comps">{comps.map(([k, v]) => <span key={k}>{k.replace(/^(driver|inflation|memory|peer|korea):/, "")} <b className="num">{sg(v as number, 1)}</b></span>)}</div> : null}
      {p.drivers.length ? <div className="dh-drv">주도 변수 {p.drivers.join(" · ")}</div> : null}
      {p.missing.length ? <div className="dh-miss">결측 {p.missing.join(" · ")} — 0 으로 채우지 않았다</div> : null}
      {p.summary ? <div className="dh-sum">{p.summary}</div> : null}
    </div>
  );
}

export function DailyHistoryStrip({ history, compact = false }: { history: DailyHistory | null; compact?: boolean }) {
  const [sel, setSel] = useState<string | null>(null);
  if (!history) return <div className="dh dh-empty mono" data-testid="dh-loading">히스토리를 불러오는 중…</div>;
  const h = history; const pts = h.points;
  if (pts.length === 0) return <div className="dh dh-empty mono" data-testid="dh-empty">저장된 daily snapshot 이 없습니다.</div>;
  const color = (st: string) => h.palette[st] ?? "var(--lbl-neutral)";
  const [lo, hi] = h.score_range.length === 2 ? [h.score_range[0]!, h.score_range[1]!] : [-100, 100];
  const W = Math.max(120, pts.length * 14), H = 34;
  const y = (v: number) => 3 + (1 - (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * (H - 6);
  const x = (i: number) => (i + 0.5) * (W / pts.length);
  const path = pts.map((p, i) => (p.score === null ? null : `${x(i).toFixed(1)},${y(p.score).toFixed(1)}`)).filter(Boolean).join(" ");
  const seen = new Set<string>(); const legend = pts.map((p) => p.state).filter((s) => (seen.has(s) ? false : (seen.add(s), true)));
  const selected = sel ? pts.find((p) => p.date === sel) ?? null : null;
  const zeroY = lo < 0 && hi > 0 ? y(0) : null;
  return (
    <div className={`dh${compact ? " dh-compact" : ""}`} data-testid="daily-history" data-tab={h.tab_id} data-mode="stored">
      <div className="dh-ctx mono" data-testid="dh-ctx">
        <span className="dh-cur">Current <b style={{ color: color(h.current_state ?? "") }} data-testid="dh-current">{h.current_label ?? "–"}</b> <span className="num">{h.current_streak}D</span></span>
        <span>Previous <b>{h.previous_label ?? "–"}</b></span>
        <span>1M Transitions <b className="num">{h.changes}</b></span>
        <span>1M Share <b className="num">{h.share_pct.toFixed(0)}%</b></span>
        {h.score_current !== null ? <span>{h.score_label || "Score"} <b className="num">{sg(h.score_current, 0)}</b>{h.score_change_1w !== null ? <span className="dh-1w"> 1W {sg(h.score_change_1w, 0)}</span> : null}</span> : null}
        <span className="dh-counts" data-testid="dh-counts" title="Recorded = 그날 당시 저장한 판정 · Backfilled = 기록이 없어 그 날짜까지의 데이터로 1회 복원 · Live = 오늘, 확정 전">R {h.recorded_days} · B {h.backfilled_days}{h.live_today ? " · L 1" : ""}</span>
      </div>
      <div className="dh-band" role="list" aria-label="daily snapshots">
        {pts.map((p) => (
          <span key={p.date} role="listitem" className={`dh-cell${p.date === sel ? " dh-sel" : ""}${p.source === "LIVE" ? " dh-live" : ""}`} data-testid="dh-cell" data-state={p.state} data-source={p.source}
            style={{ background: color(p.state) }} title={pointTitle(p, h)} onClick={() => setSel(p.date === sel ? null : p.date)} />
        ))}
      </div>
      {pts.filter((p) => p.score !== null).length >= 2 ? (
        <svg viewBox={`0 0 ${W} ${H}`} className="dh-spark" preserveAspectRatio="none" aria-hidden="true" data-testid="dh-spark">
          {zeroY !== null ? <line x1={0} x2={W} y1={zeroY} y2={zeroY} className="dh-zero" /> : null}
          <polyline points={path} className="dh-line" />
          {pts.map((p, i) => (p.score === null ? null : <circle key={p.date} cx={x(i)} cy={y(p.score)} r={p.source === "LIVE" ? 2.6 : 1.6} className={`dh-dot dh-dot-${p.source.toLowerCase()}`} />))}
        </svg>
      ) : null}
      <div className="dh-axis mono"><span>{md(pts[0]!.date)}</span><span>{md(pts[Math.floor(pts.length / 2)]!.date)}</span><span>{md(pts[pts.length - 1]!.date)}</span></div>
      <div className="dh-legend mono">{legend.map((s) => <span key={s} className="dh-leg"><i style={{ background: color(s) }} />{h.labels[s] ?? s}</span>)}</div>
      {selected ? <Detail p={selected} h={h} onClose={() => setSel(null)} /> : null}
      <div className="dh-foot mono" data-testid="dh-footnote">{h.footnote}</div>
    </div>
  );
}

/** 탭 화면에 꽂는 패널 — 제목 + 훅. snapshot.as_of 가 바뀔 때만 다시 받는다. */
export function DailyHistoryPanel({ tab, title, scenario, asOf, span = 3, enabled = true }: { tab: DailyHistory["tab_id"]; title: string; scenario: string | undefined; asOf: string | null; span?: 1 | 2 | 3; enabled?: boolean }) {
  const { history, error } = useDailyHistoryLazy(tab, scenario, asOf, enabled);
  return (
    <section className={`panel span-${span} dh-panel`} data-testid={`history-panel-${tab}`}>
      <header className="panel-head"><h2 className="panel-title">{title}</h2><div className="panel-note mono">{history ? `${history.window_days}거래일 · ${history.footnote}` : "Daily recorded history · past states locked"}</div></header>
      <div className="panel-body">{error ? <div className="dh dh-empty mono" data-testid="dh-error">{error}</div> : <DailyHistoryStrip history={history} compact />}</div>
    </section>
  );
}

