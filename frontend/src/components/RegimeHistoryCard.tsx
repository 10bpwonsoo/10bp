import { useEffect, useRef, useState } from "react";
import type { CkRegimeDay, CkRegimeHistory } from "../api/types";
import { duplicateDates, kstTime, maxLabelsFor, md, mergedNote, snapshotLine, thinLabels } from "../lib/historyDates";
import { sourceLine } from "./DailyHistoryStrip";

/**
 * MARKET REGIME HISTORY · 1M — 실시간 2 탭 전용. "최근 한 달 시장의 색이 어떻게 변해 왔는가" 를 3초에 읽게 한다.
 * A CURRENT REGIME CONTEXT · B REGIME BAND(핵심) · C MARKET COMPOSITE SPARKLINE(보조, 선 1개) · D DRIVER HEAT STRIP(5) · E REGIME SHARE · F RECENT TRANSITIONS(≤3).
 * 띠는 Display Regime(안정화)이고 raw 판정은 날짜를 눌러 본다 — 시각화를 위해 데이터를 왜곡하지 않는다. 확률 표현 없음.
 */
const REGIME_COLOR: Record<string, string> = {
  risk_on: "var(--lbl-risk-on)", neutral: "var(--lbl-neutral)", growth: "var(--lbl-growth)", inflation: "var(--lbl-inflation)",
  policy: "var(--lbl-policy)", liquidity_stress: "var(--lbl-liquidity)", geopolitical: "var(--lbl-geopolitical)",
};
const color = (k: string) => REGIME_COLOR[k] ?? "var(--rule-hi)";
const short = (label: string) => label.split(" / ")[0] ?? label;
const sg = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);

function isMobile(): boolean {
  try { return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(max-width: 760px)").matches; } catch { return false; }
}

function Context({ h }: { h: CkRegimeHistory }) {
  const last = h.days[h.days.length - 1];
  const kst = h.date_basis === "kst_snapshot";
  return (
    <div className="ck-h-ctx" data-testid="ck-h-ctx">
      {kst && last ? (
        <div className="ck-h-snap mono" data-testid="ck-h-snapshot">
          <span><i>Daily Snapshot</i> <b>{last.date}</b></span>
          {h.snapshot_time ? <span><i>Cutoff</i> <b>{h.snapshot_time}</b></span> : null}
          {last.market_date ? <span><i>US data through</i> <b>{last.market_date} close</b></span> : null}
        </div>
      ) : null}
      <div className="ck-h-ctx-main">
        <span className="ck-k mono">Current</span>
        <b className="ck-h-cur" style={{ color: color(h.current_regime) }} data-testid="ck-h-current">{h.current_label}</b>
      </div>
      <dl className="ck-h-ctx-grid mono">
        <div><dt title="공식 regime 이 이어진 거래일 수">Regime Duration</dt><dd className="num">{h.duration_days}D</dd></div>
        <div><dt>Previous</dt><dd>{h.previous_label ? short(h.previous_label) : "–"}</dd></div>
        <div><dt>1M Transitions</dt><dd className="num">{h.transitions_1m}</dd></div>
        <div><dt>1M Share</dt><dd className="num">{h.share_pct.toFixed(0)}%</dd></div>
      </dl>
      {/* CURRENT SIGNAL · TRANSITION — MARKET NOW 와 같은 state (2026-10-22). 일수는 서로 다른 미국 장(Daily Snapshot)만 센다 */}
      <div className="ck-h-rawbox mono" data-testid="ck-h-raw" data-status={h.state?.transition_status ?? h.transition_status}>
        <span className="ck-k">Current signal</span><b style={{ color: h.pending_regime ? color(h.raw_regime) : "var(--muted)" }}>{short(h.raw_label || h.current_label)}</b><span className="num">{h.raw_persistence_days}D</span>
        <span className="ck-k">Transition</span><b style={{ color: h.transition_status === "STABLE" ? "var(--ok)" : h.transition_status === "CONFIRMED" ? "var(--accent)" : "var(--warn)" }} data-testid="ck-h-tstatus">{h.state?.transition_text || (h.transition_status || "").replace(/_/g, " ")}</b>
        {h.transition_status_ko ? <span className="ck-h-raw-ko">{h.transition_status_ko}</span> : null}
      </div>
      {h.intraday ? (
        <div className="ck-h-intraday mono" data-testid="ck-h-intraday" title="장중 LIVE 신호는 daily history 칸을 덮지 않고 공식 연속일수에도 넣지 않는다 — 다음 Daily Snapshot 에서 확인된다">
          <span className="ck-k">Live signal</span><b>{kstTime(h.intraday.as_of) || h.intraday.date}</b>
          <span><em style={{ color: color(h.intraday.raw_regime) }}>{short(h.intraday.raw_label || h.intraday.raw_state)}</em></span>
          <span className="ck-h-raw-ko">공식 연속일수 제외{h.intraday.market_date ? ` · US ${md(h.intraday.market_date)} close 기준` : ""}</span>
        </div>
      ) : null}
    </div>
  );
}

function DayTip({ d, palette }: { d: CkRegimeDay; palette: Record<string, string> }) {
  return (
    <div className="ck-h-tip mono" role="tooltip" data-testid="ck-h-tip">
      <b>{d.date}</b>
      {d.market_date ? <span data-testid="ck-h-tip-dates">{snapshotLine(d.date, d.market_date)}{d.data_asof ? ` · data ${kstTime(d.data_asof)}` : ""}</span> : null}
      <span>Dominant <em style={{ color: color(d.dominant_regime) }}>{short(palette[d.dominant_regime] ?? d.dominant_regime)}</em>{d.end_regime !== d.dominant_regime ? <> · End <em style={{ color: color(d.end_regime) }}>{short(palette[d.end_regime] ?? d.end_regime)}</em></> : null}</span>
      <span>Evidence <b className="num">{d.evidence_strength.toFixed(0)}%</b>{d.dominant_regime_dwell !== null ? <> · Dwell <b className="num">{(d.dominant_regime_dwell * 100).toFixed(0)}%</b></> : null}</span>
      {d.dominant_driver ? <span>Driver {d.dominant_driver}</span> : null}
      {d.top_evidence.length > 1 ? <span>{d.top_evidence.slice(0, 2).join(" · ")}</span> : null}
      {d.bridged ? <span className="ck-h-note">raw {d.raw_state} — 하루짜리라 직전 regime 에 이어짐</span> : null}
      <span className="ck-h-src" data-testid="ck-h-tip-source">{sourceLine(d.source, d.calculated_at, d.model_version, "", d.locked)}</span>
      {d.merged && d.merged.length ? <span className="ck-h-note">{mergedNote(d.merged)}</span> : null}
    </div>
  );
}

function DayDetail({ d, h, onClose }: { d: CkRegimeDay; h: CkRegimeHistory; onClose: () => void }) {
  const fs = h.drivers.map((dr) => ({ label: dr.label, v: d.factors[dr.key] ?? null }));
  return (
    <div className="ck-h-detail" data-testid="ck-h-detail">
      <div className="ck-h-detail-head mono"><b>{d.date}</b>
        <span>Raw <em>{d.raw_state}</em>{d.raw_secondary ? ` / ${d.raw_secondary}` : ""}</span>
        <span>Display <em style={{ color: color(d.display_regime) }}>{short(d.display_label)}</em>{d.bridged ? " (bridged)" : d.is_transition ? " (transition)" : ""}</span>
        <button type="button" className="ck-more" onClick={onClose}>닫기</button></div>
      <div className="ck-h-detail-grid mono">
        <span>Dominant <em>{h.palette[d.dominant_regime] ?? d.dominant_regime}</em></span>
        <span>End <em>{h.palette[d.end_regime] ?? d.end_regime}</em>{d.key_change ? <i className="ck-h-note"> {d.key_change}</i> : null}</span>
        <span>Evidence <b className="num">{d.evidence_strength.toFixed(0)}%</b></span>
        <span>Daily dwell <b className="num">{d.dominant_regime_dwell === null ? "–" : `${(d.dominant_regime_dwell * 100).toFixed(0)}%`}</b> · 관측 {d.observations}회 · 장중 전환 {d.transition_count}회</span>
        <span>Composite <b className="num">{d.composite === null ? "–" : sg(d.composite, 0)}</b></span>
        <span>{d.data_quality}</span>
        <span data-testid="ck-h-detail-source" data-source={d.source}>{sourceLine(d.source, d.calculated_at, d.model_version, d.logic_version, d.locked)}</span>
        {d.market_date ? <span data-testid="ck-h-detail-dates">{snapshotLine(d.date, d.market_date)}{d.data_asof ? ` · data ${kstTime(d.data_asof)}` : ""}{d.storage_date ? ` · 저장 키 ${d.storage_date}` : ""}</span> : null}
        {d.merged && d.merged.length ? <span className="ck-h-note">{mergedNote(d.merged)}</span> : null}
      </div>
      {d.top_evidence.length ? <div className="mono ck-h-detail-ev">주도 변수 {d.top_evidence.join(" · ")}</div> : null}
      <div className="ck-h-detail-f mono">{fs.map((f) => <span key={f.label}>{f.label} <b className="num">{f.v === null ? "–" : sg(f.v, 1)}</b></span>)}</div>
    </div>
  );
}

function Band({ h }: { h: CkRegimeHistory }) {
  const [hover, setHover] = useState<number | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const n = h.days.length;
  const tipIdx = hover ?? sel;
  const first = h.days[0]; const lastDay = h.days[n - 1];
  const axisRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState<number>(() => (isMobile() ? 320 : 900));
  useEffect(() => {
    const el = axisRef.current;
    if (!el) return;
    const read = () => { const w = el.getBoundingClientRect().width; if (w > 0) setWidth(w); };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read); ro.observe(el);
    return () => ro.disconnect();
  }, []);
  if (!first || !lastDay) return null;
  const dates = h.days.map((d) => d.date);
  const dupes = duplicateDates(dates);
  const seen = new Set<string>();
  // 같은 날짜 라벨은 한 번만 — 중복이 있으면 위에 경고를 띄운다(숨기지 않고 알린다)
  const shown = thinLabels(n, maxLabelsFor(width, n)).filter((i) => { const k = dates[i] as string; if (seen.has(k)) return false; seen.add(k); return true; });
  const curStart = h.blocks.length ? h.blocks[h.blocks.length - 1]?.start ?? "" : "";
  return (
    <div className="ck-h-bandwrap" data-testid="ck-h-band">
      <div className="ck-h-blocks">
        {h.blocks.map((b) => (
          <span key={b.start} className={`ck-h-block${b.current ? " cur" : ""}`} style={{ flex: b.days, color: color(b.regime) }} title={`${b.label} ${md(b.start)}–${md(b.end)} · ${b.days}D`}>
            {b.days >= 3 ? short(b.label) : b.days === 2 ? short(b.label).slice(0, 6) : ""}
          </span>
        ))}
      </div>
      <div className="ck-h-band" onMouseLeave={() => setHover(null)}>
        {h.days.map((d, i) => (
          <i key={`${d.date}-${i}`} className={`ck-h-cell${d.is_transition ? " tr" : ""}${curStart && curStart <= d.date ? " cur" : ""}${sel === i ? " sel" : ""}`}
            style={{ background: color(d.display_regime) }} data-testid="ck-h-cell" aria-label={`${d.date} ${d.display_label}`}
            onMouseEnter={() => setHover(i)} onClick={() => setSel(sel === i ? null : i)} />
        ))}
        {tipIdx !== null && h.days[tipIdx] ? <div className="ck-h-tipwrap" style={{ left: `${((tipIdx + 0.5) / n) * 100}%` }}><DayTip d={h.days[tipIdx] as CkRegimeDay} palette={h.palette} /></div> : null}
      </div>
      {/* x축 — KST snapshot 날짜 한 기준. 폭이 모자라면 라벨만 솎는다(칸은 그대로, 정확한 날짜는 툴팁). 전환 ▲ 는 날짜 글자 없이 */}
      <div className="ck-h-axis mono" ref={axisRef} data-testid="ck-h-axis" data-labels={shown.length}>
        <span className="ck-h-marks">
          {h.days.map((d, i) => d.is_transition ? <em key={`m${i}`} style={{ left: `${(i / n) * 100}%` }} data-testid="ck-h-mark" title={`${d.date} ${h.palette[h.days[i - 1]?.display_regime ?? ""] ?? ""} → ${d.display_label}`}>▲</em> : null)}
        </span>
        {shown.map((i) => {
          const d = h.days[i] as CkRegimeDay;
          const edge = i === 0 ? "first" : i === n - 1 ? "last" : undefined;
          return <span key={`l${i}`} className="ck-h-lbl" data-edge={edge} data-testid="ck-h-axis-label" style={edge ? undefined : { left: `${((i + 0.5) / n) * 100}%` }}>{md(d.date)}</span>;
        })}
      </div>
      {dupes.length ? <div className="ck-h-warn mono" data-testid="ck-h-dupes">날짜 중복 {dupes.join(", ")} — 저장 데이터 확인 필요 (라벨은 한 번만)</div> : null}
      {sel !== null && h.days[sel] ? <DayDetail d={h.days[sel] as CkRegimeDay} h={h} onClose={() => setSel(null)} /> : null}
    </div>
  );
}

function Spark({ h }: { h: CkRegimeHistory }) {
  const vals = h.composite; const n = vals.length;
  if (!n || vals.every((v) => v === null)) return null;
  const W = 300, H = 40, pad = 3;
  const xs = (i: number) => pad + (i / Math.max(1, n - 1)) * (W - 2 * pad);
  const ys = (v: number) => H / 2 - (Math.max(-100, Math.min(100, v)) / 100) * (H / 2 - pad);
  const pts = vals.map((v, i) => (v === null ? null : `${xs(i).toFixed(1)},${ys(v).toFixed(1)}`)).filter(Boolean).join(" ");
  const last = [...vals].reverse().findIndex((v) => v !== null); const li = n - 1 - last; const lv = vals[li] ?? null;
  return (
    <div className="ck-h-spark" data-testid="ck-h-spark">
      <span className="ck-k mono">Market composite</span>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <line x1={0} x2={W} y1={H / 2} y2={H / 2} className="ck-h-zero" />
        <polyline points={pts} fill="none" className="ck-h-line" />
        {lv !== null ? <circle cx={xs(li)} cy={ys(lv)} r={2.4} className="ck-h-dot" /> : null}
      </svg>
      <span className="mono ck-h-spark-t"><b className="num">{sg(h.composite_current, 0)}</b> · {h.composite_slope_days}D slope <b className="num">{sg(h.composite_slope, 0)}</b></span>
    </div>
  );
}

function Heat({ h }: { h: CkRegimeHistory }) {
  const ref = 2.0;
  const first = md(h.days[0]?.date ?? ""); const last = md(h.days[h.days.length - 1]?.date ?? "");
  return (
    <div className="ck-h-heat" data-testid="ck-h-heat">
      <div className="ck-h-heat-title"><span className="ck-k mono">Driver heat</span><span className="ck-sub-i">factor 별 최근 한 달 흐름 — 위에서 아래로: 이름 / 띠 / 지금 상태 / 해석</span></div>
      <div className="ck-h-heat-axis mono" data-testid="ck-h-heat-axis"><span>{first}</span><span>{last}</span></div>
      {h.drivers.map((dr) => {
        const h1 = dr.horizons.find((x) => x.key === "1D"); const h5 = dr.horizons.find((x) => x.key === "5D");
        const split = !!(h1 && h5 && h1.z !== null && h5.z !== null && h1.arrow !== "?" && h5.arrow !== "?" && ((h1.z > 0) !== (h5.z > 0)) && Math.abs(h1.z) >= 0.3 && Math.abs(h5.z) >= 0.5);
        return (
          <div key={dr.key} className={`ck-h-heat-row${split ? " split" : ""}`} data-testid="ck-h-heat-row" data-key={dr.key}>
            <div className="ck-h-heat-l"><b>{dr.label_ui || dr.label}</b><small>{dr.label_ko}</small></div>
            <div className="ck-h-heat-body">
              <div className="ck-h-heat-cells">
                {dr.values.map((v, i) => (
                  <i key={i} className={v === null ? "miss" : v >= 0 ? "pos" : "neg"} style={v === null ? undefined : { opacity: 0.12 + 0.88 * Math.min(1, Math.abs(v) / ref) }} title={`${h.days[i]?.date ?? ""} ${dr.label_ui || dr.label} factor ${v === null ? "결측" : sg(v, 2)}`} />
                ))}
              </div>
              <div className="ck-h-heat-a" data-testid="ck-h-heat-meaning">
                <span className="ck-h-heat-st"><b className="mono">{dr.arrow}</b><em>{dr.meaning}</em></span>
                {dr.horizons.length ? (
                  <span className="mono ck-h-heat-hz" title={dr.horizon_label ? `대표 계열 ${dr.horizon_label}` : undefined}>
                    {dr.horizons.map((x) => <span key={x.key}><i>{x.key}</i> {x.arrow !== "?" ? x.arrow : "–"}{x.z !== null ? ` ${sg(x.z)}σ` : ""}</span>)}
                  </span>
                ) : null}
              </div>
              {dr.horizon_read ? <div className="ck-h-heat-read">{dr.horizon_read}</div> : null}
            </div>
          </div>
        );
      })}
      <div className="ck-legend mono ck-h-heat-legend" data-testid="ck-h-heat-legend"><span>COLOR</span> factor 방향 (빨강 +, 파랑 −) — 좋고 나쁨이 아니다 · <span>ARROW</span> 현재 경제적 의미</div>
    </div>
  );
}

function Share({ h }: { h: CkRegimeHistory }) {
  return (
    <div className="ck-h-share" data-testid="ck-h-share">
      <span className="ck-k mono">1M regime share</span>
      {h.share.map((s) => (
        <div key={s.regime} className={`ck-h-share-row${s.regime === h.current_regime ? " cur" : ""}`}>
          <span className="ck-h-share-l">{short(s.label)}</span>
          <span className="ck-h-share-bar"><i style={{ width: `${s.share}%`, background: color(s.regime) }} /></span>
          <span className="num mono">{s.share.toFixed(0)}%</span>
        </div>
      ))}
    </div>
  );
}

function Transitions({ h }: { h: CkRegimeHistory }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!h.transitions.length) return <div className="ck-h-empty mono">기간 중 display regime 전환 없음</div>;
  return (
    <div className="ck-h-trans" data-testid="ck-h-trans">
      <span className="ck-k mono">Recent transitions{h.total_transitions > h.transitions.length ? ` · ${h.transitions.length} / ${h.total_transitions}` : ""}</span>
      {h.transitions.map((t) => (
        <div key={t.date} className={`ck-h-tr${open === t.date ? " open" : ""}`} data-testid="ck-h-transition" onClick={() => setOpen(open === t.date ? null : t.date)} role="button" tabIndex={0}>
          <div className="ck-h-tr-l1"><b className="mono">{md(t.date)}</b> <span style={{ color: color(t.from_regime) }}>{short(t.from_label)}</span> <span className="ck-h-tr-ar">→</span> <span style={{ color: color(t.to_regime) }}>{short(t.to_label)}</span></div>
          <div className="ck-h-tr-l2 mono">{t.primary_driver}{t.confirmation ? ` · ${t.confirmation}` : ""}</div>
          {open === t.date ? <ul className="ck-h-tr-ev mono">{t.evidence.map((e) => <li key={e}>{e}</li>)}</ul> : null}
        </div>
      ))}
    </div>
  );
}

function Fold({ label, open, children, testid }: { label: string; open: boolean; children: React.ReactNode; testid?: string }) {
  return (
    <details className="ck-h-fold" open={open} data-testid={testid}>
      <summary className="mono">{label}</summary>
      {children}
    </details>
  );
}

export function RegimeHistoryCard({ h }: { h: CkRegimeHistory }) {
  const mobile = isMobile();
  return (
    <section className="panel ck-card" style={{ gridArea: "hist" }} data-testid="ck-history">
      <header className="panel-head">
        <h2 className="panel-title">Market Regime History · 1M</h2>
        <div className="panel-note mono ck-h-ranges" role="group" aria-label="기간">
          {h.ranges.map((r) => (
            <button key={r.key} type="button" className="ck-h-range" aria-pressed={r.key === h.range} disabled={!r.available} title={r.available ? `${r.days}거래일` : r.reason}>{r.key}</button>
          ))}
        </div>
      </header>
      <div className="panel-body ck-h">
        <div className="ck-h-main">
          <Band h={h} />
          <Spark h={h} />
          <Fold label="Show drivers" open={!mobile} testid="ck-h-fold-drivers"><Heat h={h} /></Fold>
        </div>
        <aside className="ck-h-side"><Context h={h} /></aside>
        <div className="ck-h-sharewrap"><Fold label="Show regime share" open={!mobile} testid="ck-h-fold-share"><Share h={h} /></Fold></div>
        <div className="ck-h-foot">
          <Fold label="Show transitions" open={!mobile} testid="ck-h-fold-trans"><Transitions h={h} /></Fold>
          {h.footnote ? <div className="ck-h-footnote mono" data-testid="ck-h-footnote" data-mode={h.history_mode} data-basis={h.date_basis ?? "storage_utc"}>{h.footnote} · Recorded {h.recorded_days} · Backfilled {h.backfilled_days}{h.date_basis === "kst_snapshot" ? ` · 날짜 = KST Daily Snapshot${h.snapshot_time ? ` (${h.snapshot_time})` : ""}, 미국 장 날짜는 툴팁` : ""}</div> : null}
          {h.gaps && h.gaps.length ? <div className="ck-h-footnote mono" data-testid="ck-h-gaps">저장된 daily snapshot 이 없는 평일: {h.gaps.map(md).join(", ")} — 값을 채우지 않았다</div> : null}
        </div>
      </div>
    </section>
  );
}
