import { useState } from "react";
import type { BreakdownTenor, CurveMoveView, CurvePoint, InflationPressureMap, MarketReadMeta, PressureItem, PressureTone, PressureValue, SourceClass, YieldMoveBreakdown } from "../api/types";
import { kst } from "./RatesTopSections";

/**
 * 금리 탭 아래 세 패널(2026-10-13) — INFLATION PRESSURE MAP → TREASURY CURVE → YIELD MOVE BREAKDOWN.
 * 물가 압력(어디서 오나) → 금리곡선(어느 만기가 움직이나) → 금리 변화 원인(실질금리 대 기대인플레) 순으로 읽힌다.
 * 숫자는 서버가 만들고 화면은 상태 → 방향 → 원인 → 의미 순으로 그리기만 한다. 커브 모양(bp)과 이례성(σ)은 칸을 나눈다.
 */
const TONE: Record<PressureTone, string> = { up: "var(--up)", down: "var(--down)", flat: "var(--muted)", missing: "var(--faint)" };
const sg = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}`);
const bp = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${sg(v)}bp`);
const md = (iso: string | null | undefined) => (iso ? `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}` : "");

function ReadTag({ meta }: { meta: MarketReadMeta | null }) {
  const llm = meta?.source === "llm";
  const sub = !meta ? "" : llm ? [meta.generator === "session" ? "세션 생성" : "", kst(meta.generated_at)].filter(Boolean).join(" · ")
    : meta.status === "pending" ? "AI 해석 생성 중" : meta.status === "skipped" ? "AI 해석 생략" : "AI 해석 없음";
  return <span className={`rt-src${llm ? " ai" : ""}`} data-testid="panel-read-source" title={meta?.reason || undefined}>{llm ? "AI INTERPRETATION" : "RULE-BASED"}{sub ? ` · ${sub}` : ""}</span>;
}

function Link({ text }: { text: string }) {
  return text ? <p className="rp-link" data-testid="panel-link"><span aria-hidden="true">↳</span> {text}</p> : null;
}

/* ── 1. INFLATION PRESSURE MAP ───────────────────────── */
function ScoreTrack({ score }: { score: number }) {
  const w = Math.min(50, (Math.abs(score) / 100) * 50);
  return (
    <span className="rp-track" aria-hidden="true">
      <i className="rp-mid" />
      <i className="rp-fill" style={{ width: `${w}%`, [score >= 0 ? "left" : "right"]: "50%", background: score >= 0 ? "var(--up)" : "var(--down)" } as React.CSSProperties} />
    </span>
  );
}

/** 출처 급 배지 — 색을 아끼고 글자로 구분한다. PRIMARY 실선 · MIRROR 실선 · SECONDARY 점선 · PROXY 주의 · NEWS 보조 · UNAVAILABLE 흐림 */
const TIER_LABEL: Record<SourceClass, string> = { PRIMARY: "PRIMARY", MIRROR: "MIRROR", SECONDARY: "SECONDARY VERIFIED", PROXY: "PROXY", NEWS: "NEWS", UNAVAILABLE: "DATA UNAVAILABLE" };
export function TierBadge({ tier, title }: { tier: SourceClass; title?: string }) {
  return <span className={`rp-tier t-${tier.toLowerCase()}`} data-testid="tier-badge" data-tier={tier} title={title}>{TIER_LABEL[tier]}</span>;
}

function PressureRow({ it }: { it: PressureItem }) {
  const missing = it.score === null;
  const tier = it.source_class ?? (missing ? "UNAVAILABLE" : "PRIMARY");
  const proxy = tier === "PROXY";
  const news = tier === "NEWS";
  return (
    <div className={`rp-item${proxy ? " is-proxy" : ""}${news ? " is-news" : ""}`} data-testid="pressure-item" data-key={it.key} data-state={it.state} data-tier={tier}>
      <div className="rp-item-name"><b>{it.display_label || it.label}</b><span>{it.label_ko}</span></div>
      <div className="rp-item-state mono" style={{ color: TONE[it.tone] }}>{it.state}</div>
      {missing ? <div className="rp-item-miss">{it.missing_text}</div> : (
        <>
          <div className="rp-item-score mono num" title={`${it.state_ko} · −100 강한 물가 하락 압력 … +100 강한 물가 상승 압력`}>{sg(it.score)}<ScoreTrack score={it.score!} /></div>
          {it.evidence_text ? <div className="rp-item-ev mono">{it.evidence_text}</div> : null}
        </>
      )}
      <div className="rp-item-src mono" data-testid="item-source">
        <TierBadge tier={tier} title={it.fallback_reason || undefined} />
        {it.stale ? <span className="rp-tier t-stale" data-testid="stale-badge">STALE</span> : null}
        {it.source_label && !proxy ? <span>{it.source_label}</span> : null}
        {it.last_updated ? <span>Updated {md(it.last_updated)}{it.freshness_days !== null && it.freshness_days !== undefined ? ` · ${it.freshness_days}D` : ""}</span> : null}
        {news ? <span>보조 신호 · INFLATION SIGNAL 점수 미반영</span> : null}
        {it.in_signal === false && !news && !missing ? <span>신호 계산 제외</span> : null}
      </div>
      {proxy ? (
        <div className="rp-proxy" data-testid="proxy-disclosure">
          <b>{it.proxy_note || "실제 원데이터 미연결 · 대체 지표로 추정"}</b>
          {it.fallback_reason ? <span>{it.fallback_reason}</span> : null}
          <span>대체: {(it.proxy_components ?? []).join(" · ")} 기반</span>
        </div>
      ) : null}
      {it.values && it.values.length ? (
        <ul className="rp-vals mono" data-testid="item-values">
          {it.values.map((v) => <li key={v.label}><span>{v.label}</span><b className="num">{v.text}</b>{v.source_class !== tier || v.stale ? <TierBadge tier={v.source_class} /> : null}{v.stale ? <span className="rp-tier t-stale">STALE</span> : null}</li>)}
        </ul>
      ) : null}
      {it.comment ? <div className="rp-item-comment">{it.comment}</div> : null}
    </div>
  );
}

function DataSources({ rows }: { rows: PressureValue[] }) {
  if (!rows.length) return null;
  return (
    <details className="rp-sources" data-testid="data-sources">
      <summary className="mono">DATA SOURCES · macro {rows.length}개 series — 출처 급 · 갱신일 · 신선도</summary>
      <div className="rp-src-table" role="table">
        {rows.map((r) => (
          <div key={r.label} className="rp-src-row" role="row" data-tier={r.source_class}>
            <span className="rp-src-l">{r.label}</span><b className="num mono">{r.text}</b>
            <span className="rp-src-meta mono"><TierBadge tier={r.source_class} /> {r.source || "–"} · {r.updated ? `Updated ${md(r.updated)} · ${r.freshness_days ?? "–"}D` : "날짜 없음"}{r.stale ? " · STALE" : ""}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

export function InflationPressureMapPanel({ map }: { map: InflationPressureMap }) {
  return (
    <section className="panel rp-panel" data-testid="inflation-map">
      <header className="panel-head"><h2 className="panel-title">Inflation Pressure Map</h2><div className="panel-note">물가를 위·아래로 움직이는 주요 압력을 구성요소별로 확인</div></header>
      <div className="panel-body rp-body">
        <div className="rp-verdict">
          <div className="rp-fact" data-testid="inflation-signal" data-signal={map.signal}>
            <span className="rr-k mono">INFLATION SIGNAL</span>
            <b className="mono" style={{ color: TONE[map.signal_tone] }}>{map.signal}</b>
            <span className="rp-sub">{map.signal_ko}</span>
          </div>
          <div className="rp-fact" data-testid="inflation-confirmation" data-confirmation={map.confirmation}>
            <span className="rr-k mono">CONFIRMATION</span>
            <b className="mono" style={{ color: map.confirmation === "FULL" ? "var(--ok)" : "var(--warn)" }}>{map.confirmation}</b>
            <span className="rp-sub">{map.confirmation_ko} · 구성요소 {map.available}/{map.total}</span>
            {map.official_count !== undefined ? <span className="rp-sub mono" data-testid="confirmation-quality">Official data {map.official_count}/{map.total} · Proxy {map.proxy_count ?? 0} · News {map.news_count ?? 0}{map.unavailable_count ? ` · Unavailable ${map.unavailable_count}` : ""}</span> : null}
          </div>
        </div>
        <p className="rp-summary" data-testid="inflation-summary">{map.summary}</p>
        <div className="rp-scale mono" title={map.scale_note}><span style={{ color: "var(--down)" }}>−100 물가 하락 압력</span><span>0 중립</span><span style={{ color: "var(--up)" }}>+100 물가 상승 압력</span></div>
        <div className="rp-items">{map.items.map((it) => <PressureRow key={it.key} it={it} />)}</div>
        <DataSources rows={map.data_sources ?? []} />
        <div className="rp-read" data-testid="inflation-read"><div className="rp-read-head"><span className="rr-k mono">READ</span><ReadTag meta={map.read_meta} /></div><p>{map.read}</p></div>
        <Link text={map.link} />
      </div>
    </section>
  );
}

/* ── 2. TREASURY CURVE ───────────────────────────────── */
function CurveChart({ points, window }: { points: CurvePoint[]; window: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const pts = points.filter((p) => p.today !== null);
  if (pts.length < 2) return null;
  const vals = pts.flatMap((p) => [p.today!, ...(p.ago !== null ? [p.ago] : [])]);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = Math.max(0.05, (hi - lo) * 0.15);
  const y0 = lo - pad, y1 = hi + pad;
  const W = 360, H = 150, L = 40, R = 58, T = 10, B = 24;
  const x = (i: number) => L + (i * (W - L - R)) / (pts.length - 1);
  const y = (v: number) => T + ((y1 - v) / (y1 - y0)) * (H - T - B);
  const path = (k: "today" | "ago") => pts.map((p, i) => (p[k] === null ? "" : `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p[k]!).toFixed(1)}`)).join(" ");
  const ticks = [y0 + pad, (y0 + y1) / 2, y1 - pad];
  const last = pts.length - 1;
  const h = hover === null ? null : pts[hover]!;
  return (
    <figure className="rp-chart" data-testid="curve-chart">
      <div className="rp-legend mono"><span><i className="rp-sw today" />TODAY</span><span><i className="rp-sw ago" />{window} AGO</span><span className="rp-legend-y">yield %</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`미국채 수익률 곡선 — 오늘과 ${window} 전`} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="rp-grid" /><text x={L - 6} y={y(t) + 3} className="rp-axis" textAnchor="end">{t.toFixed(2)}</text></g>)}
        {pts.map((p, i) => <text key={p.label} x={x(i)} y={H - 6} className="rp-axis" textAnchor="middle">{p.label}</text>)}
        <path d={path("ago")} className="rp-line ago" />
        <path d={path("today")} className="rp-line today" />
        {pts.map((p, i) => p.ago === null ? null : <circle key={`a${i}`} cx={x(i)} cy={y(p.ago)} r={3.5} className="rp-dot ago" />)}
        {pts.map((p, i) => <circle key={`t${i}`} cx={x(i)} cy={y(p.today!)} r={4} className="rp-dot today" />)}
        {(() => {
          // 끝점 라벨 — 두 선이 붙어 있으면 위·아래로 벌려 겹치지 않게
          const yt = y(pts[last]!.today!), ya = pts[last]!.ago === null ? null : y(pts[last]!.ago!);
          const gap = 11; let lt = yt + 3, la = ya === null ? 0 : ya + 3;
          if (ya !== null && Math.abs(la - lt) < gap) { const mid = (lt + la) / 2; const agoAbove = ya <= yt; la = mid + (agoAbove ? -gap / 2 : gap / 2); lt = mid + (agoAbove ? gap / 2 : -gap / 2); }
          return <>{<text x={x(last) + 8} y={lt} className="rp-dl today">TODAY</text>}{ya !== null ? <text x={x(last) + 8} y={la} className="rp-dl ago">{window} AGO</text> : null}</>;
        })()}
        {hover !== null ? <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} className="rp-cross" /> : null}
        {pts.map((_p, i) => <rect key={`h${i}`} x={x(i) - (W - L - R) / (pts.length - 1) / 2} y={0} width={(W - L - R) / (pts.length - 1)} height={H} fill="transparent" onMouseEnter={() => setHover(i)} />)}
      </svg>
      {h ? <div className="rp-tip mono" data-testid="curve-tip"><b>{h.label}</b> 오늘 {h.today!.toFixed(2)}% · {window} 전 {h.ago === null ? "–" : `${h.ago.toFixed(2)}%`} · {bp(h.chg_bp)}</div> : <div className="rp-tip mono rp-tip-hint">점에 올리면 만기별 값</div>}
    </figure>
  );
}

export function TreasuryCurvePanel({ cv }: { cv: CurveMoveView }) {
  return (
    <section className="panel rp-panel" data-testid="curve">
      <header className="panel-head"><h2 className="panel-title">Treasury Curve</h2><div className="panel-note">금리곡선의 어느 만기가 움직이고 있는가</div></header>
      <div className="panel-body rp-body">
        <div className="rp-verdict">
          <div className="rp-fact" data-testid="curve-shape" data-shape={cv.shape_key}>
            <span className="rr-k mono">CURVE MOVE · {cv.window_label} bp</span>
            <b className="mono">{cv.shape}</b>
            <span className="rp-sub mono">{cv.level_dir}</span>
          </div>
          <div className="rp-fact" data-testid="curve-intensity">
            <span className="rr-k mono">MOVE INTENSITY · {cv.window_label} σ</span>
            <b className="mono">{cv.most_unusual ?? "–"} <span className="num">{cv.most_unusual_z === null ? "" : `${sg(cv.most_unusual_z, 1)}σ`}</span></b>
            <span className="rp-sub mono">{cv.intensity}</span>
          </div>
        </div>
        <div className="rp-spreads mono" data-testid="curve-spreads">
          {cv.spreads.map((s) => (
            <span key={s.key} data-direction={s.direction}><em>{s.key}</em> <b className="num">{bp(s.chg_bp)}</b> {s.direction === "missing" ? "–" : s.direction.toUpperCase()}{s.level_bp !== null ? <small> · 수준 {s.level_bp.toFixed(0)}bp</small> : null}</span>
          ))}
        </div>
        <CurveChart points={cv.points} window={cv.window_label} />
        <div className="rp-table" role="table" aria-label="만기별 수익률">
          <div className="rp-tr rp-th mono" role="row"><span>TENOR</span><span>YIELD</span><span>{cv.window_label} bp</span><span>{cv.window_label} σ</span></div>
          {cv.points.map((p) => (
            <div key={p.label} className="rp-tr" role="row" data-tenor={p.label}>
              <span className="mono">{p.label}</span>
              <b className="num">{p.today === null ? "–" : `${p.today.toFixed(2)}%`}</b>
              <span className="num" style={{ color: (p.chg_bp ?? 0) >= 0 ? "var(--up)" : "var(--down)" }}>{bp(p.chg_bp)}</span>
              <span className="num" style={{ color: p.label === cv.most_unusual ? "var(--ink)" : "var(--muted)", fontWeight: p.label === cv.most_unusual ? 600 : 400 }}>{p.z === null ? "–" : `${sg(p.z, 1)}σ`}</span>
            </div>
          ))}
        </div>
        {cv.short_window ? <p className="rp-note mono" data-testid="curve-1d">{cv.short_window} — 상단 REGIME 칸은 이 하루 기준</p> : null}
        <div className="rp-read" data-testid="curve-read"><div className="rp-read-head"><span className="rr-k mono">READ</span></div><p>{cv.read}</p></div>
        <Link text={cv.link} />
      </div>
    </section>
  );
}

/* ── 3. YIELD MOVE BREAKDOWN ─────────────────────────── */
function TenorCard({ t }: { t: BreakdownTenor }) {
  const row = (label: string, sub: string, v: number | null, lead: boolean) => (
    <div className={`rp-bd-row${lead ? " lead" : ""}`}><span>{label}<small>{sub}</small></span><b className="num" style={{ color: v === null ? "var(--faint)" : v > 0 ? "var(--up)" : v < 0 ? "var(--down)" : "var(--muted)" }}>{bp(v)}</b></div>
  );
  return (
    <div className="rp-bd" data-testid="breakdown-tenor" data-tenor={t.tenor} data-primary={t.primary}>
      <div className="rp-bd-head"><b className="mono">{t.tenor}</b>{t.small_move ? <span className="rp-tag" data-testid="small-move">SMALL MOVE · 분해 의미 제한</span> : null}</div>
      {row("Real Yield", "MODEL · 명목 − 기대인플레", t.real_bp, t.primary === "real" || t.primary === "both")}
      {row("Inflation Expectation", "BREAKEVEN", t.breakeven_bp, t.primary === "breakeven" || t.primary === "both")}
      <div className="rp-bd-sum">{row("Nominal Yield", "명목", t.nominal_bp, false)}</div>
      <div className="rp-bd-primary mono" data-testid="primary-driver"><span className="rr-k">PRIMARY DRIVER</span> <b>{t.primary_label}</b></div>
      <p className="rp-bd-line">{t.line}</p>
      {t.tips_bp !== null ? (
        <div className={`rp-bd-tips mono${t.divergence ? " div" : ""}`} data-testid="observed-tips" data-divergence={t.divergence ? "1" : "0"}>
          OBSERVED TIPS <b className="num">{bp(t.tips_bp)}</b> {t.divergence ? <span>· {t.divergence_text}</span> : t.divergence_text ? <span>· {t.divergence_text}</span> : <span>· MODEL REAL 과 일치</span>}
        </div>
      ) : null}
    </div>
  );
}

export function YieldMoveBreakdownPanel({ yb }: { yb: YieldMoveBreakdown }) {
  const [all, setAll] = useState(false);
  const shown = all ? yb.tenors : yb.tenors.filter((t) => yb.default_tenors.includes(t.tenor));
  const hidden = yb.tenors.length - yb.tenors.filter((t) => yb.default_tenors.includes(t.tenor)).length;
  const t0 = yb.tenors[0];
  return (
    <section className="panel rp-panel" data-testid="decomposition">
      <header className="panel-head"><h2 className="panel-title" title="Nominal Yield Decomposition">Yield Move Breakdown</h2><div className="panel-note">명목금리 변화 = 실질금리 변화 + 기대인플레이션 변화</div></header>
      <div className="panel-body rp-body">
        <p className="rp-formula">금리가 왜 움직였는지 분해 <span className="mono">· {t0 ? `${t0.window_days}D` : ""}{t0?.start_date ? ` · ${md(t0.start_date)} → ${md(t0.end_date)}` : ""}{t0?.aligned ? " · 세 계열 같은 날짜" : ""}</span></p>
        <div className="rp-bds">{shown.map((t) => <TenorCard key={t.tenor} t={t} />)}</div>
        {hidden > 0 ? <button type="button" className="rp-more" data-testid="breakdown-all" onClick={() => setAll((v) => !v)}>{all ? "접기" : `View all (+${hidden})`}</button> : null}
        <div className="rp-read" data-testid="breakdown-read"><div className="rp-read-head"><span className="rr-k mono">READ · {yb.headline_tenor ?? ""}</span></div><p>{yb.character}</p></div>
        <p className="rp-note">{yb.note}</p>
        <Link text={yb.link} />
      </div>
    </section>
  );
}

export function RatesLowerFlow({ map, cv, yb }: { map: InflationPressureMap; cv: CurveMoveView; yb: YieldMoveBreakdown }) {
  return (
    <div className="rp-flow span-3" data-testid="rates-lower-flow">
      <InflationPressureMapPanel map={map} />
      <TreasuryCurvePanel cv={cv} />
      <YieldMoveBreakdownPanel yb={yb} />
    </div>
  );
}
