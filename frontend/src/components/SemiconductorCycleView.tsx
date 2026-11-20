import { useEffect, useRef, useState } from "react";
import type { DailyHistory } from "../api/types";
import type { SemiconductorCycle, SemiMapRow, SemiPremium, SemiProduct, SemiStage, SemiNormalized } from "../api/semiconductor";
import { DailyHistoryStrip } from "./DailyHistoryStrip";
import "../theme/semiconductor.css";

/**
 * 반도체 사이클 탭 (2026-10-23) — 메모리 가격 → Spot Premium → 계약가 → HBM / 공급 → 한국 반도체 수출 → 매출 / EPS → 주가.
 * 숫자·판정은 서버(engines/semiconductor_cycle)가 만들고 화면은 그리기만 한다. 없는 값은 NO DATA — 0 으로 그리지 않는다.
 * 데스크톱 최대 2열 · 모바일 1열(선택은 드롭다운). 기존 색 토큰만 쓴다. 확률·추천 표현 없음.
 */

const NO = "NO DATA";
const sg = (v: number | null | undefined, d = 1, unit = "%") => (v === null || v === undefined ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);
const px = (v: number | null | undefined, d = 3) => (v === null || v === undefined ? "–" : `$${v.toFixed(d)}`);
const md = (iso?: string | null) => (iso ? iso.slice(5, 10).replace("-", "/") : "–");
const chgColor = (v: number | null | undefined) => (v === null || v === undefined ? "var(--faint)" : v > 0 ? "var(--up)" : v < 0 ? "var(--down)" : "var(--muted)");

const REGIME_COLOR: Record<string, string> = {
  STRONG_UPSWING: "var(--lbl-risk-on)", UPSWING: "var(--lbl-growth)", EARLY_RECOVERY: "var(--lbl-policy)", NEUTRAL: "var(--lbl-neutral)",
  DOWNTURN: "var(--lbl-inflation)", DEEP_DOWNTURN: "var(--lbl-risk-off)", INSUFFICIENT_DATA: "var(--faint)",
};
export const STAGE_COLOR: Record<string, string> = {
  CONFIRMED: "var(--ok)", PARTIAL: "var(--warn)", WATCH: "var(--info)", "NOT CONFIRMED": "var(--crit)", "NO DATA": "var(--faint)",
};
const QUALITY_COLOR: Record<string, string> = { FRESH: "var(--ok)", STALE: "var(--warn)", UNAVAILABLE: "var(--faint)" };
const SERIES_COLORS = ["var(--lbl-risk-on)", "var(--lbl-risk-off)", "var(--lbl-growth)", "var(--lbl-liquidity)", "var(--lbl-inflation)", "var(--lbl-policy)", "var(--lbl-geopolitical)"];
const RANGES = [{ key: "1M", days: 30 }, { key: "3M", days: 91 }, { key: "6M", days: 182 }, { key: "1Y", days: 365 }] as const;

function chipColor(v: string): string {
  if (v.startsWith(NO)) return "var(--faint)";
  if (/DIVERGENCE|DECELERATING|FALLING|SOFT|WEAK|COMPRESSING|NEGATIVE/.test(v)) return "var(--down)";
  if (/STALE|MIXED|FLAT|STABLE|PARTIAL|NEUTRAL/.test(v)) return "var(--warn)";
  return "var(--ok)";
}

function Panel({ title, note, wide, testid, children }: { title: string; note?: string; wide?: boolean; testid: string; children: React.ReactNode }) {
  return (
    <section className={`panel sm-panel${wide ? " sm-wide" : ""}`} data-testid={testid}>
      <header className="panel-head"><h2 className="panel-title">{title}</h2>{note ? <div className="panel-note mono">{note}</div> : null}</header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

/** 폭을 재서 SVG 를 실제 픽셀로 그린다 — 글자가 늘어나지 않고 모바일에서 넘치지 않는다. */
function useWidth<T extends HTMLElement>(fallback = 600): [React.RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const set = () => { const x = el.clientWidth; if (x > 0) setW(x); };
    set();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

// ── 1. REGIME ───────────────────────────────────────────────
function RegimeCard({ c }: { c: SemiconductorCycle }) {
  const r = c.regime;
  const color = REGIME_COLOR[r.state] ?? "var(--muted)";
  return (
    <section className="panel sm-panel sm-wide sm-regime" data-testid="semi-regime" data-state={r.state}>
      <div className="panel-body">
        <div className="sm-regime-top">
          <span className="sm-kicker mono">SEMICONDUCTOR CYCLE</span>
          <span className="sm-asof mono">{c.as_of.slice(0, 16).replace("T", " ")} UTC</span>
        </div>
        <div className="sm-regime-head">
          <b className="sm-regime-label" style={{ color }} data-testid="semi-regime-label">{r.label}</b>
          <span className="sm-conf mono" data-testid="semi-confidence">신뢰도 {r.confidence.toFixed(0)} · 증거 확보 {(r.coverage * 100).toFixed(0)}%{r.composite !== null ? ` · composite ${sg(r.composite, 0, "")}` : ""}</span>
        </div>
        <div className="sm-chips" data-testid="semi-chips">
          {r.chips.map((ch) => (
            <span key={ch.key} className="sm-chip mono" data-key={ch.key}><small>{ch.label}</small><b style={{ color: chipColor(ch.value) }}>{ch.value}</b></span>
          ))}
        </div>
        <div className="sm-evidence">
          {r.components.map((x) => (
            <div key={x.key} className="sm-ev-row" data-key={x.key}>
              <span className="sm-ev-name">{x.label}<small className="mono"> ×{x.weight}</small></span>
              {x.score === null ? <span className="sm-ev-bar mono sm-nd">{NO}</span> : (
                <span className="sm-ev-bar"><i className="sm-zero" /><i className="sm-fill" style={{ width: `${Math.min(100, Math.abs(x.score)) / 2}%`, [x.score >= 0 ? "left" : "right"]: "50%", background: x.score >= 0 ? "var(--up)" : "var(--down)" } as React.CSSProperties} />
                  <b className="num mono">{sg(x.score, 0, "")}</b></span>
              )}
            </div>
          ))}
        </div>
        <p className="sm-note">{r.note}</p>
      </div>
    </section>
  );
}

// ── 2. MARKET READ ─────────────────────────────────────────
function MarketRead({ c }: { c: SemiconductorCycle }) {
  const m = c.market_read;
  const src = m.source === "llm" ? (m.generator === "session" ? "AI · 세션 생성(같은 검증)" : "AI") : "규칙 기반";
  return (
    <Panel title="Market Read" note={`${src}${m.status === "pending" ? " · 생성 중" : ""}`} wide testid="semi-read">
      <p className="sm-read" data-testid="semi-read-text">{m.read}</p>
      {m.themes_ko.length ? <div className="sm-tags">{m.themes_ko.map((t) => <span key={t} className="sm-tag mono">{t}</span>)}</div> : null}
      {m.data_caveat ? <p className="sm-note">단서 · {m.data_caveat}</p> : null}
      {m.source !== "llm" && m.reason ? <p className="sm-note mono">{m.reason}</p> : null}
    </Panel>
  );
}

// ── 3. MEMORY PRICE SNAPSHOT ───────────────────────────────
function PriceSnapshot({ c }: { c: SemiconductorCycle }) {
  const rows = c.memory_prices;
  return (
    <Panel title="Memory Price Snapshot" note="DRAMeXchange 현물 세션 평균 · USD" wide testid="semi-prices">
      <div className="sm-table sm-prices" role="table">
        <div className="sm-tr sm-th mono" role="row"><span>제품</span><span>Current</span><span>1D</span><span>1W</span><span>1M</span><span>3M</span></div>
        {rows.map((p) => (
          <div key={p.id} className={`sm-tr${p.tier === "ett" ? " sm-ett" : ""}`} role="row" data-testid="semi-price-row" data-id={p.id}>
            <span className="sm-name">{p.label}<small className="mono"> {p.available ? `${md(p.updated_at)} · 관측 ${p.observations}` : "UNAVAILABLE"}</small></span>
            <span className="num mono" data-label="Current">{px(p.current)}</span>
            {[p.change_1d, p.change_1w, p.change_1m, p.change_3m].map((v, i) => (
              <span key={i} className="num mono" data-label={["1D", "1W", "1M", "3M"][i]} style={{ color: chgColor(v) }}>{v === null ? "–" : sg(v)}</span>
            ))}
          </div>
        ))}
      </div>
      <p className="sm-note">'–' 는 그 창의 기준 관측이 없다는 뜻이다(0 이 아니다). 현물 이력이 쌓이면 채워진다. eTT 는 유효 테스트 등급(저가 · 변동 큼).</p>
    </Panel>
  );
}

// ── 4. PRICE + SPOT PREMIUM CHART ──────────────────────────
// 선 = 평일 Daily State(그날까지 알려진 최근 원천 값 — 갱신 사이는 수평선). 툴팁에 원천 관측일과 RAW / CARRIED_FORWARD 를 보인다.
// 계약가 = 공개 뒤부터 다음 공개 전까지의 anchor(점선 계단). Premium = 우축 옅은 면. 계산용 값은 서버 그대로 — 그릴 때만 솎는다(점이 많을 때).
interface ChartPt { t: number; iso: string; spot: number; origin: "R" | "C"; src: string; contract: number | null; anchor: string | null; premium: number | null }
const RENDER_MAX = 520;
const HQ_COLOR: Record<string, string> = { FULL: "var(--ok)", "RECONSTRUCTED GOOD": "var(--ok)", PARTIAL: "var(--warn)", UNAVAILABLE: "var(--faint)" };
const SRC_NAME: Record<string, string> = {
  dramexchange_daily_express: "DRAMeXchange Daily Express", dramexchange_home: "DRAMeXchange (direct)", trendforce_weekly: "TrendForce weekly",
  dramexchange_archived: "DRAMeXchange (Internet Archive)", trendforce_archived: "TrendForce (Internet Archive)",
};
// 직접 공개 원천을 먼저, Internet Archive 보존본을 뒤에
const sourceNames = (xs: string[]) => [...xs].sort((a, b) => Number(a.endsWith("_archived")) - Number(b.endsWith("_archived"))).map((x) => SRC_NAME[x] ?? x).join(" + ");

export function buildPts(p: SemiProduct, prem: SemiPremium | undefined): ChartPt[] {
  const byT = new Map((prem?.available ? prem.series ?? [] : []).map((s) => [s.t.slice(0, 10), s]));
  const rows: [string, number, "R" | "C", string][] = p.daily?.length ? p.daily : p.history.map((h) => [h.t.slice(0, 10), h.v, "R", h.t.slice(0, 10)]);
  return rows.map(([d, v, o, src]) => {
    const s = byT.get(d);
    return { t: Date.parse(`${d}T00:00:00Z`), iso: d, spot: v, origin: o, src, contract: s ? s.contract : null, anchor: s ? s.anchor : null, premium: s ? s.premium : null };
  });
}

/** 그릴 때만 솎는다(마지막 점은 남긴다). 툴팁·계산은 원본 배열. */
function thin<T>(pts: T[]): T[] {
  if (pts.length <= RENDER_MAX) return pts;
  const k = Math.ceil(pts.length / RENDER_MAX);
  return pts.filter((_x, i) => i % k === 0 || i === pts.length - 1);
}

const anchorLabel = (a: string | null) => {
  if (!a) return "";
  const [y, m] = a.split("-");
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m) - 1]}-${y}`;
};

function PriceChart({ c }: { c: SemiconductorCycle }) {
  const choices = c.memory_prices.filter((p) => p.selector && p.available);
  // 기본 = 1Y 이력 품질이 가장 높은 제품 — 원천 그대로(FULL) → 보존본 재구성(GOOD) → 첫 제품
  const best = choices.find((p) => p.history_quality?.class === "FULL") ?? choices.find((p) => p.coverage?.["1Y"]?.status === "GOOD") ?? choices[0];
  const [sel, setSel] = useState(best?.id ?? "");
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("1Y");
  const [showContract, setShowContract] = useState(true);
  const [hover, setHover] = useState<number | null>(null);
  const [ref, width] = useWidth<HTMLDivElement>();
  const p = choices.find((x) => x.id === sel) ?? best;
  const prem = c.spot_premium.find((x) => x.spot === p?.id);
  const all = p ? buildPts(p, prem) : [];
  const last = all.length ? all[all.length - 1]!.t : 0;
  const days = RANGES.find((r) => r.key === range)!.days;
  const pts = all.filter((x) => x.t >= last - days * 86400000);
  const draw = thin(pts);
  const cov = p?.coverage?.[range];
  const H = 240, L = 48, R = 48, T = 12, B = 26;
  const W = Math.max(280, width);
  const prices = pts.flatMap((x) => [x.spot, ...(showContract && x.contract !== null ? [x.contract] : [])]);
  // 가격 축은 $0 부터 — 현물과 계약가의 격차(= premium)가 눈에 그대로 보이게
  const pmax = prices.length ? Math.max(...prices) : 1;
  const pad = pmax * 0.08 || 1;
  const yP = (v: number) => T + (H - T - B) * (1 - v / (pmax + pad));
  const prs = pts.map((x) => x.premium).filter((v): v is number => v !== null);
  const qmin = Math.min(0, ...prs), qmax = Math.max(0, ...prs);
  const qpad = (qmax - qmin) * 0.1 || 10;
  const yQ = (v: number) => T + (H - T - B) * (1 - (v - (qmin - qpad)) / ((qmax + qpad) - (qmin - qpad)));
  const t0 = pts.length ? pts[0]!.t : 0, t1 = pts.length ? pts[pts.length - 1]!.t : 1;
  const xT = (t: number) => (t1 === t0 ? L + (W - L - R) / 2 : L + (W - L - R) * ((t - t0) / (t1 - t0)));
  const line = (f: (x: ChartPt) => number | null, y: (v: number) => number, step = false) => {
    let d = ""; let pen = false;
    for (const x of draw) {
      const v = f(x);
      if (v === null) { pen = false; continue; }
      const X = xT(x.t).toFixed(1), Y = y(v);
      d += pen ? (step ? `H${X} V${Y.toFixed(1)} ` : `L${X},${Y.toFixed(1)} `) : `M${X},${Y.toFixed(1)} `;
      pen = true;
    }
    return d.trim();
  };
  const area = () => {
    const seg = draw.filter((x) => x.premium !== null);
    if (seg.length < 2) return "";
    const z = yQ(0).toFixed(1);
    return `M${xT(seg[0]!.t).toFixed(1)},${z} ` + seg.map((x) => `L${xT(x.t).toFixed(1)},${yQ(x.premium!).toFixed(1)}`).join(" ") + ` L${xT(seg[seg.length - 1]!.t).toFixed(1)},${z} Z`;
  };
  const h = hover !== null ? pts[hover] : null;
  const onMove = (ev: React.PointerEvent<SVGSVGElement>) => {
    if (!pts.length) return;
    const box = ev.currentTarget.getBoundingClientRect();
    const x = ev.clientX - box.left;
    let bi = 0, bd = Infinity;
    pts.forEach((q, i) => { const d = Math.abs(xT(q.t) - x); if (d < bd) { bd = d; bi = i; } });
    setHover(bi);
  };
  const rawDots = pts.length <= 70 ? draw.filter((x) => x.origin === "R") : [];
  const note = prem?.available ? `계약 기준 ${prem.contract_anchor_label} · ${prem.proxy ? `PROXY PREMIUM (${prem.comparability})` : `${prem.comparability} · 같은 칩 비교`}` : "Spot Premium 없음";
  return (
    <Panel title="Product Price & Spot Premium" note={note} wide testid="semi-chart">
      <div className="sm-controls">
        <select className="sm-select mono" aria-label="제품 선택" value={p?.id ?? ""} onChange={(e) => { setSel(e.target.value); setHover(null); }} data-testid="semi-product-select">
          {choices.map((x) => <option key={x.id} value={x.id}>{x.label}{x.coverage?.["1Y"]?.status === "GOOD" ? "" : " · 1Y PARTIAL"}</option>)}
        </select>
        <div className="sm-seg sm-product-btns" role="group" aria-label="제품">
          {choices.map((x) => <button key={x.id} type="button" className="sm-segbtn mono" aria-pressed={x.id === p?.id} onClick={() => { setSel(x.id); setHover(null); }}>{x.label}</button>)}
        </div>
        <div className="sm-seg" role="group" aria-label="기간">
          {RANGES.map((r) => {
            const st = p?.coverage?.[r.key]?.status;
            return <button key={r.key} type="button" className={`sm-segbtn mono${st && st !== "GOOD" ? " sm-partial" : ""}`} aria-pressed={r.key === range} title={st ? `${r.key} coverage ${st}` : undefined}
              onClick={() => { setRange(r.key); setHover(null); }}>{r.key}</button>;
          })}
        </div>
        {prem?.available ? <label className="sm-toggle mono"><input type="checkbox" checked={showContract} onChange={(e) => setShowContract(e.target.checked)} data-testid="semi-contract-toggle" /> Contract</label> : null}
      </div>
      <div className="sm-cov mono" data-testid="semi-chart-coverage" data-status={cov?.status ?? "UNAVAILABLE"}>
        {p?.history_quality ? (
          <span data-testid="semi-history-quality" data-class={p.history_quality.class}>
            1Y HISTORY <b style={{ color: HQ_COLOR[p.history_quality.class] ?? "var(--muted)" }}>{p.history_quality.label}</b> · Raw observations {p.history_quality.raw_obs}
            {" "}· Source {sourceNames(p.history_quality.sources)}{p.history_quality.archived_share ? ` · Internet Archive 비중 ${Math.round(p.history_quality.archived_share * 100)}%` : ""}<br />
          </span>
        ) : null}
        {cov?.status === "GOOD"
          ? <>{range} COVERAGE <b style={{ color: "var(--ok)" }}>GOOD</b> · RAW {cov.raw}{cov.expected_weeks ? ` · 관측 주 ${cov.observed_weeks}/${cov.expected_weeks}` : ""}{cov.max_gap !== undefined && cov.max_gap !== null ? ` · 최대 공백 ${cov.max_gap}일` : ""}{cov.score !== undefined ? ` · score ${cov.score}` : ""}</>
          : <>{range} COVERAGE <b style={{ color: "var(--warn)" }}>{cov?.status === "MONTHLY" ? "MONTHLY COVERAGE GOOD" : cov?.status ?? "UNAVAILABLE"}</b> · Available From {cov?.available_from ?? "–"} · RAW {cov?.raw ?? 0}{(c.coverage_table ?? []).find((r) => r.id === p?.id)?.reason ? ` — ${(c.coverage_table ?? []).find((r) => r.id === p?.id)!.reason}` : ""}</>}
        {p?.validation?.length ? <><br />VALIDATION {p.validation.map((v) => `${v.reference_period} ${v.value_type === "CHANGE_PCT" ? `${v.value > 0 ? "+" : ""}${v.value}%` : `$${v.value}`} (${v.grade}) → ${v.check}${v.raw_change_pct !== undefined ? ` · raw ${v.raw_change_pct > 0 ? "+" : ""}${v.raw_change_pct}%` : ""}`).join(" · ")}</> : null}
      </div>
      <div ref={ref} className="sm-chart-wrap">
        {pts.length === 0 ? <div className="sm-empty mono">{NO}</div> : (
          <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${p?.label} 현물 가격과 Spot Premium`} onPointerMove={onMove} onPointerLeave={() => setHover(null)} data-testid="semi-price-svg">
            {prs.length ? <path d={area()} className="sm-area-prem" data-testid="semi-premium-area" /> : null}
            {prs.length ? <line x1={L} x2={W - R} y1={yQ(0)} y2={yQ(0)} className="sm-zero-line" data-testid="semi-zero-line" /> : null}
            {showContract ? <path d={line((x) => x.contract, yP, true)} className="sm-l-con" data-testid="semi-contract-line" /> : null}
            <path d={line((x) => x.spot, yP)} className="sm-l-spot" data-testid="semi-spot-line" />
            {rawDots.map((x, i) => <circle key={i} cx={xT(x.t)} cy={yP(x.spot)} r={2.4} className="sm-dot" />)}
            <text x={4} y={T + 8} className="sm-ax mono">{px(pmax + pad, 1)}</text>
            <text x={4} y={H - B} className="sm-ax mono">$0</text>
            {prs.length ? <><text x={W - 4} y={T + 8} className="sm-ax mono" textAnchor="end">{sg(qmax + qpad, 0)}</text><text x={W - 4} y={yQ(0) - 3} className="sm-ax mono" textAnchor="end">0%</text></> : null}
            <text x={L} y={H - 6} className="sm-ax mono">{pts[0]!.iso}</text>
            <text x={W - R} y={H - 6} className="sm-ax mono" textAnchor="end">{pts[pts.length - 1]!.iso}</text>
            {h ? <line x1={xT(h.t)} x2={xT(h.t)} y1={T} y2={H - B} className="sm-hover-line" /> : null}
          </svg>
        )}
        {h ? (
          <div className="sm-tip mono" data-testid="semi-tooltip" data-origin={h.origin} style={{ left: Math.min(Math.max(0, xT(h.t) - 90), W - 200) }}>
            <b>{h.iso}</b><br />Spot {px(h.spot)}<br />Latest Source Observation {h.src}<br />Origin {h.origin === "R" ? "RAW" : "CARRIED_FORWARD"}
            <br />Contract {h.contract !== null ? `${px(h.contract)} (${anchorLabel(h.anchor)})` : "–"}<br />Premium {h.premium !== null ? sg(h.premium) : "–"}
          </div>
        ) : null}
      </div>
      <div className="sm-legend mono">
        <span className="sm-lg-spot">— Spot (Daily State)</span>
        {prem?.available && showContract ? <span className="sm-lg-con">-- Contract anchor{prem.proxy ? " (proxy, 칩 환산)" : ""}</span> : null}
        {prs.length ? <span className="sm-lg-prem">▒ Premium (우축)</span> : null}
        {rawDots.length ? <span className="sm-lg-spot">● RAW 관측일</span> : null}
      </div>
      {prem && !prem.available ? <p className="sm-note">Spot Premium 계산 안 함 — {prem.reason}</p> : null}
      {prem?.available ? (
        <p className="sm-note" data-testid="semi-premium-stats">
          Premium = 그날 알려진 Spot ÷ 그날 알려진 계약가 − 1(미래 계약가를 과거에 쓰지 않는다). 1Y z-score{" "}
          {prem.z_status === "OK" ? <b>{prem.zscore ?? "–"} · percentile {prem.percentile_1y ?? "–"}% (RAW {prem.raw_premium_obs}개, 평균 {sg(prem.mean_1y, 1)})</b> : <b>NOT ENOUGH HISTORY (RAW {prem.raw_premium_obs ?? 0}/{prem.zscore_min_obs})</b>}
          . {prem.conversion ? `환산: ${prem.conversion}. ` : ""}{prem.note}
        </p>
      ) : null}
      {p ? <p className="sm-note mono">MA20 {px(p.ma20, 2)} · MA60 {px(p.ma60, 2)} · 6M {sg(p.change_6m)} · 1Y {sg(p.change_1y)} · {c.history_note ?? ""}</p> : null}
    </Panel>
  );
}

// ── 4b. SPOT PREMIUM TABLE ────────────────────────────────
function PremiumTable({ c }: { c: SemiconductorCycle }) {
  return (
    <Panel title="Spot Premium" note="Spot / comparable contract − 1" testid="semi-premium">
      {c.spot_premium.map((x) => (
        <div key={x.spot} className="sm-prem" data-testid="semi-premium-row" data-spot={x.spot} data-proxy={x.proxy ? "1" : "0"}>
          <div className="sm-prem-head">
            <span className="sm-name">{x.spot_label}{x.proxy ? <span className="sm-badge mono">PROXY PREMIUM</span> : null}</span>
            {x.available ? <b className="num mono" style={{ color: chgColor(x.current) }}>{sg(x.current)}</b> : <span className="mono sm-nd">NOT COMPUTED</span>}
          </div>
          {x.available ? (
            <div className="sm-prem-meta mono">
              {x.state?.replace("_", " ")} · {x.direction} · 계약 {x.contract_anchor_label}{x.contract_stale ? <b style={{ color: "var(--warn)" }}> STALE</b> : null} · 1W {sg(x.change_1w_pp, 1, "pp")} · 1M {sg(x.change_1m_pp, 1, "pp")}
              {" · "}{x.z_status === "OK" ? <>1Y z {x.zscore ?? "–"} · pct {x.percentile_1y ?? "–"}%</> : <span data-testid="semi-not-enough">NOT ENOUGH HISTORY</span>} · RAW {x.raw_premium_obs ?? x.observations ?? 0}
            </div>
          ) : <div className="sm-prem-meta">{x.reason}</div>}
        </div>
      ))}
    </Panel>
  );
}

// ── 5. MOMENTUM & BREADTH ────────────────────────────────
function Momentum({ c }: { c: SemiconductorCycle }) {
  const rows = c.memory_prices.filter((p) => p.tier === "main");
  const b = c.breadth;
  return (
    <Panel title="Momentum & Breadth" note={`Breadth ${b.state}`} testid="semi-momentum">
      <div className="sm-breadth mono" data-testid="semi-breadth" data-state={b.state}>
        <span>Premium {b.products_in_premium[0]}/{b.products_in_premium[1]}</span><span>Expanding {b.expanding_premium[0]}/{b.expanding_premium[1]}</span><span>Positive {b.positive_momentum[0]}/{b.positive_momentum[1]}</span>
      </div>
      {rows.map((p) => (
        <div key={p.id} className="sm-ev-row" data-testid="semi-momentum-row" data-id={p.id}>
          <span className="sm-ev-name">{p.label}<small className="mono"> {p.momentum_basis === "SINCE_FIRST" ? `SINCE ${md(p.since_first_from)}` : p.momentum_basis === "NONE" ? "" : "1W·1M·3M"}
            {p.momentum_confidence ? <> · conf <b data-testid="semi-mom-conf" style={{ color: p.momentum_confidence === "HIGH" ? "var(--ok)" : p.momentum_confidence === "MEDIUM" ? "var(--warn)" : "var(--faint)" }}>{p.momentum_confidence}</b></> : null}
            {p.freshness?.days_since_source !== null && p.freshness?.days_since_source !== undefined ? ` · 원천 ${p.freshness.days_since_source}일 전 · RAW 1M ${p.raw_obs_1m ?? 0}` : ""}</small></span>
          {p.momentum === null ? <span className="sm-ev-bar mono sm-nd">{NO}</span> : (
            <span className="sm-ev-bar"><i className="sm-zero" /><i className="sm-fill" style={{ width: `${Math.min(100, Math.abs(p.momentum)) / 2}%`, [p.momentum >= 0 ? "left" : "right"]: "50%", background: p.momentum >= 0 ? "var(--up)" : "var(--down)" } as React.CSSProperties} />
              <b className="num mono">{sg(p.momentum, 0, "")}</b></span>
          )}
        </div>
      ))}
      <p className="sm-note">−100 … +100. 변화율은 Daily State 로, confidence 는 원천 갱신 간격·최근 30일 RAW 수로 정한다(같은 값 반복을 관측으로 세지 않는다). {b.note}</p>
    </Panel>
  );
}

// ── 6. NORMALIZED ────────────────────────────────────────
function Normalized({ c }: { c: SemiconductorCycle }) {
  const [range, setRange] = useState<"1M" | "3M" | "6M" | "1Y">("1Y");
  const [ref, width] = useWidth<HTMLDivElement>();
  const rows: SemiNormalized[] = c.normalized[range] ?? [];
  const H = 200, L = 38, R = 12, T = 10, B = 22, W = Math.max(280, width);
  const ts = rows.flatMap((r) => r.points.map((p) => Date.parse(p.t)));
  const vs = rows.flatMap((r) => r.points.map((p) => p.v));
  const t0 = Math.min(...ts), t1 = Math.max(...ts), v0 = Math.min(100, ...vs), v1 = Math.max(100, ...vs);
  const vpad = (v1 - v0) * 0.1 || 2;
  const x = (t: number) => (t1 === t0 ? L : L + (W - L - R) * ((t - t0) / (t1 - t0)));
  const y = (v: number) => T + (H - T - B) * (1 - (v - (v0 - vpad)) / ((v1 + vpad) - (v0 - vpad)));
  return (
    <Panel title="Normalized Comparison" note="기간 시작 = 100" wide testid="semi-normalized">
      <div className="sm-controls"><div className="sm-seg" role="group" aria-label="기간">
        {(["1M", "3M", "6M", "1Y"] as const).map((k) => <button key={k} type="button" className="sm-segbtn mono" aria-pressed={k === range} onClick={() => setRange(k)}>{k}</button>)}
      </div></div>
      <div ref={ref} className="sm-chart-wrap">
        {rows.length === 0 ? <div className="sm-empty mono">{NO} — 비교할 이력(2개 이상 관측)이 없다</div> : (
          <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="제품 정규화 비교" data-testid="semi-normalized-svg">
            <line x1={L} x2={W - R} y1={y(100)} y2={y(100)} className="sm-base-line" />
            <text x={4} y={y(100) + 3} className="sm-ax mono">100</text>
            {rows.map((r, i) => (
              <path key={r.id} d={r.points.map((p, j) => `${j ? "L" : "M"}${x(Date.parse(p.t)).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ")} fill="none" stroke={SERIES_COLORS[i % SERIES_COLORS.length]} strokeWidth={1.8} />
            ))}
          </svg>
        )}
      </div>
      <div className="sm-legend mono">{rows.map((r, i) => <span key={r.id} style={{ color: SERIES_COLORS[i % SERIES_COLORS.length] }}>— {r.label} {r.last.toFixed(1)} <small>(from {r.base_date}{r.coverage && r.coverage !== "GOOD" ? ` · ${range} ${r.coverage}` : ""})</small></span>)}</div>
    </Panel>
  );
}

// ── 7. HISTORY ──────────────────────────────────────────
function History({ c }: { c: SemiconductorCycle }) {
  const h = c.memory_history as DailyHistory | null;
  return (
    <Panel title="Memory Regime History · 1M" note={h ? `${h.window_days}거래일 · ${h.footnote}` : "Daily snapshot 기준"} wide testid="semi-history">
      {h ? <DailyHistoryStrip history={h} compact /> : <div className="sm-empty mono">{NO}</div>}
      <p className="sm-note">탭이 생긴 2026-10-23 이전 날짜는 그 날짜까지 공개된 가격·수출·주가로 1회 계산(BACKFILLED, 뉴스 제외) 후 고정. 증거가 기준에 못 미친 날은 데이터 부족.</p>
    </Panel>
  );
}

// ── 8. PRODUCT MAPS ──────────────────────────────────────
function ProductMap({ title, rows, testid }: { title: string; rows: SemiMapRow[]; testid: string }) {
  return (
    <Panel title={title} testid={testid}>
      <div className="sm-table sm-map" role="table">
        <div className="sm-tr sm-th mono" role="row"><span>제품</span><span>Spot</span><span>1W/1M</span><span>Premium</span><span>Strength</span></div>
        {rows.map((r) => (
          <div key={r.id} className={`sm-tr${r.tier === "ett" ? " sm-ett" : ""}`} role="row" data-testid="semi-map-row" data-id={r.id}>
            <span className="sm-name">{r.label}</span>
            <span className="num mono" data-label="Spot">{px(r.spot)}</span>
            <span className="num mono" data-label="1W/1M" style={{ color: chgColor(r.change_1m ?? r.change_1w ?? r.since_first) }}>
              {r.change_1m !== null ? sg(r.change_1m) : r.change_1w !== null ? sg(r.change_1w) : r.since_first !== null ? `${sg(r.since_first)}*` : "–"}
            </span>
            <span className="num mono" data-label="Premium">{r.premium !== null ? `${sg(r.premium, 0)}${r.premium_proxy ? " p" : ""}` : "–"}</span>
            <span className="mono" data-label="Strength" style={{ color: chipColor(r.strength) }}>{r.strength}</span>
          </div>
        ))}
      </div>
      <p className="sm-note">* 첫 관측 이후 변화(표준 창 없음). p = proxy premium.</p>
    </Panel>
  );
}

// ── 9/12/HBM chain ─────────────────────────────────────
function Chain({ title, stages, testid, wide, note }: { title: string; stages: SemiStage[]; testid: string; wide?: boolean; note?: string }) {
  return (
    <Panel title={title} note={note} wide={wide} testid={testid}>
      <ol className="sm-chain">
        {stages.map((s) => (
          <li key={s.stage} className="sm-stage" data-testid="semi-stage" data-status={s.status}>
            <span className="sm-stage-name">{s.stage}</span>
            <b className="mono" style={{ color: STAGE_COLOR[s.status] ?? "var(--muted)" }}>{s.status}</b>
            <small>{s.evidence}</small>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function HbmPanel({ c }: { c: SemiconductorCycle }) {
  const h = c.hbm_supply;
  return (
    <Panel title="HBM / AI Memory Supply" note="계약가 앵커 · 보도" testid="semi-hbm">
      <div className="sm-kv mono">
        <span>HBM Pricing <b style={{ color: chipColor(h.pricing) }}>{h.pricing}</b></span>
        <span>Capacity <b style={{ color: chipColor(h.capacity) }}>{h.capacity}</b></span>
        <span>Lead Time <b style={{ color: chipColor(h.lead_time) }}>{h.lead_time}</b></span>
        <span>Supplier Commentary <b style={{ color: chipColor(h.supplier_commentary) }}>{h.supplier_commentary}</b></span>
      </div>
      {h.anchors.map((a) => (
        <div key={a.id} className="sm-anchor mono" data-testid="semi-hbm-anchor">
          {a.label}: {a.available ? <>{px(a.value, 2)} ({a.date}{a.prev !== null && a.prev !== undefined ? ` · 직전 ${px(a.prev, 2)} ${a.prev_date} → ${sg(a.change_pct)}` : ""})<small> {a.confidence} · {a.source}</small></> : NO}
        </div>
      ))}
      <ol className="sm-chain sm-chain-tight">
        {h.transmission.map((s) => (
          <li key={s.stage} className="sm-stage" data-testid="semi-hbm-stage" data-status={s.status}>
            <span className="sm-stage-name">{s.stage}</span><b className="mono" style={{ color: STAGE_COLOR[s.status] ?? "var(--muted)" }}>{s.status}</b><small>{s.evidence}</small>
          </li>
        ))}
      </ol>
      <p className="sm-note">{h.note}</p>
    </Panel>
  );
}

// ── 11. EXPORT NOWCAST ──────────────────────────────────
function ExportNowcast({ c }: { c: SemiconductorCycle }) {
  const e = c.export_nowcast;
  if (!e.available) return <Panel title="Semiconductor Export Nowcast" testid="semi-export"><div className="sm-empty mono">{NO} · {e.note}</div></Panel>;
  const n = e.nowcast;
  return (
    <Panel title="Semiconductor Export Nowcast" note={`${e.month} · ${e.unit} · 신뢰도 ${e.confidence_label ?? "–"} (${e.confidence ?? "–"})`} wide testid="semi-export">
      <div className="sm-table sm-export" role="table">
        <div className="sm-tr sm-th mono" role="row"><span>구간</span><span>금액</span><span>YoY</span><span>일평균 YoY</span><span>조업일</span></div>
        {(e.progress ?? []).map((p) => (
          <div key={p.scope} className="sm-tr" role="row" data-testid="semi-export-row" data-scope={p.scope}>
            <span className="sm-name">{p.label}{p.scope === "nowcast" && n ? <small className="mono"> 범위 {n.low.toFixed(0)}~{n.high.toFixed(0)}</small> : null}</span>
            <span className="num mono" data-label="금액">{p.available && p.value !== null ? p.value.toFixed(1) : p.scope === "actual" ? "Pending" : "–"}</span>
            <span className="num mono" data-label="YoY" style={{ color: chgColor(p.yoy) }}>{p.yoy !== null && p.yoy !== undefined ? sg(p.yoy) : "–"}</span>
            <span className="num mono" data-label="일평균 YoY" style={{ color: chgColor(p.daily_avg_yoy) }}>{p.daily_avg_yoy !== null && p.daily_avg_yoy !== undefined ? sg(p.daily_avg_yoy) : "–"}</span>
            <span className="num mono" data-label="조업일">{p.days !== null && p.days !== undefined ? `${p.days}${p.days_prev ? ` (전년 ${p.days_prev})` : ""}` : "–"}</span>
          </div>
        ))}
      </div>
      <div className="sm-kv mono">
        <span>Momentum <b style={{ color: chipColor(e.momentum ?? NO) }}>{e.momentum}</b><small> vs {e.prev_month} {sg(e.prev_month_yoy, 0)}</small></span>
        <span>Revision <b style={{ color: chgColor(e.revision_pp) }}>{e.revision_pp !== null && e.revision_pp !== undefined ? sg(e.revision_pp, 1, "pp") : "–"}</b><small> {e.previous ? `직전(${e.previous.basis}) ${sg(e.previous.yoy_mid, 0)}` : ""}</small></span>
        <span>Price vs Volume <b>{e.price_vs_volume}</b></span>
        <span>조업일 <b>{e.working_days ?? "–"}</b><small> {e.working_days_basis}</small></span>
      </div>
      <div className="sm-drivers">
        {(e.drivers ?? []).map((d) => <span key={d.key} className="sm-chip mono"><small>{d.label}</small><b style={{ color: chipColor(d.value) }}>{d.value}</b>{d.note ? <i>{d.note}</i> : null}</span>)}
      </div>
      <p className="sm-note">{e.method} 월말 배수: {(e.ratios ?? []).map((r) => `${r.period} ${r.ratio}${r.derived ? "(역산)" : ""}`).join(" · ") || "없음(1.0)"}. 일평균 YoY 는 조업일 차이를 걷어낸 비교. {e.price_vs_volume_note}</p>
      <p className="sm-note" data-testid="semi-export-accuracy">Accuracy · {e.accuracy?.note}</p>
    </Panel>
  );
}

// ── 13. FUNDAMENTAL ───────────────────────────────────────
function Fundamental({ c }: { c: SemiconductorCycle }) {
  const f = c.fundamental_confirmation;
  return (
    <Panel title="Fundamental Confirmation" note={f.state} testid="semi-fundamental">
      {f.rows.map((r) => (
        <div key={r.key} className="sm-frow" data-testid="semi-fund-row" data-key={r.key}>
          <span className="sm-name">{r.label}</span><b className="mono" style={{ color: r.value === "?" ? "var(--faint)" : chgColor(r.value === "↑" ? 1 : r.value === "↓" ? -1 : 0) }}>{r.value}</b><small>{r.basis}</small>
        </div>
      ))}
      <p className="sm-note">{f.companies.map((x) => x.label).join(" · ")} — {f.companies[0]?.note}</p>
    </Panel>
  );
}

// ── 14. EQUITY ───────────────────────────────────────────
function Equity({ c }: { c: SemiconductorCycle }) {
  const e = c.equity_confirmation;
  return (
    <Panel title="Equity Confirmation" note={e.status} testid="semi-equity">
      <div className="sm-table sm-eq" role="table">
        <div className="sm-tr sm-th mono" role="row"><span>종목</span><span>1D</span><span>1W</span><span>1M</span><span>vs bench</span></div>
        {[...e.stocks.map((s) => ({ ...s, key: s.id })), { key: e.index.id, label: e.index.label, ret_1d: e.index.ret_1d, ret_1w: e.index.ret_1w, ret_1m: e.index.ret_1m, rel_1m: null, bench: null, confirmation: "" }].map((s) => (
          <div key={s.key} className="sm-tr" role="row" data-testid="semi-equity-row" data-confirmation={s.confirmation}>
            <span className="sm-name">{s.label}{s.confirmation ? <small className="mono" style={{ color: chipColor(s.confirmation) }}> {s.confirmation}</small> : null}</span>
            {[s.ret_1d, s.ret_1w, s.ret_1m].map((v, i) => <span key={i} className="num mono" data-label={["1D", "1W", "1M"][i]} style={{ color: chgColor(v) }}>{sg(v)}</span>)}
            <span className="num mono" data-label="vs bench" style={{ color: chgColor(s.rel_1m) }}>{s.rel_1m !== null ? `${sg(s.rel_1m, 1, "pp")} ${s.bench}` : "–"}</span>
          </div>
        ))}
      </div>
      <p className="sm-read-small" data-testid="semi-divergence-read">{e.read}</p>
    </Panel>
  );
}

// ── 15. STOCK IMPACT ─────────────────────────────────────
function StockImpact({ c }: { c: SemiconductorCycle }) {
  return (
    <Panel title="Stock Impact" note="노출 = 사업 구조(고정) · 확인 = 오늘 데이터" testid="semi-stock-impact">
      {c.stock_impact.map((s) => (
        <div key={s.id} className="sm-impact" data-testid="semi-impact-row" data-id={s.id}>
          <div className="sm-prem-head"><span className="sm-name">{s.label}</span><b className="mono" style={{ color: chipColor(s.overall) }}>{s.overall}</b></div>
          <div className="sm-kv mono sm-kv-tight">
            <span>Memory <b>{s.memory_pricing}</b></span><span>HBM <b>{s.hbm}</b></span><span>Export <b>{s.export}</b></span>
            <span>EPS <b style={{ color: "var(--faint)" }}>{s.eps_revision}</b></span><span>Price <b style={{ color: chipColor(s.price_confirmation) }}>{s.price_confirmation}</b></span>
          </div>
        </div>
      ))}
      <p className="sm-note">장비주(P2)는 아직 넣지 않았다.</p>
    </Panel>
  );
}

// ── 16. NEWS ─────────────────────────────────────────────
function News({ c }: { c: SemiconductorCycle }) {
  return (
    <Panel title="News / Catalysts" note={`${c.news.length}건 · 그날 저장된 기사`} testid="semi-news">
      {c.news.length === 0 ? <div className="sm-empty mono">반도체 관련 기사 없음</div> : c.news.map((n) => (
        <div key={n.id} className="sm-news" data-testid="semi-news-row" data-category={n.category}>
          <div className="sm-news-head">
            <span className="sm-badge mono">{n.category}</span>
            <b className="mono" style={{ color: n.direction === "↑" ? "var(--up)" : n.direction === "↓" ? "var(--down)" : "var(--muted)" }}>{n.direction}</b>
            <span className="mono sm-faint">{md(n.published_at)} · 중요도 {n.importance}</span>
          </div>
          <div className="sm-news-title">{n.url ? <a href={n.url} target="_blank" rel="noreferrer">{n.headline}</a> : n.headline}</div>
          <small className="sm-news-why">{n.why} · {n.transmission}{n.products.length ? ` · ${n.products.join("/")}` : ""}</small>
        </div>
      ))}
    </Panel>
  );
}

// ── 17. WHAT MATTERS NEXT ────────────────────────────────
function Next({ c }: { c: SemiconductorCycle }) {
  return (
    <Panel title="What Matters Next" testid="semi-next">
      {c.what_matters_next.slice(0, 5).map((w) => (
        <div key={w.title} className="sm-next" data-testid="semi-next-row">
          <b>{w.title}</b>
          <div className="sm-next-grid">
            <span><small className="mono">CURRENT</small>{w.current}</span><span><small className="mono">TRIGGER</small>{w.trigger}</span>
            <span><small className="mono">CONFIRMATION</small>{w.confirmation}</span><span><small className="mono">IMPLICATION</small>{w.implication}</span>
          </div>
        </div>
      ))}
    </Panel>
  );
}

// ── 18. DATA QUALITY ─────────────────────────────────────
function Quality({ c }: { c: SemiconductorCycle }) {
  return (
    <Panel title="Data Quality" note="Fresh / Stale / Unavailable" wide testid="semi-quality">
      <div className="sm-table sm-quality" role="table">
        <div className="sm-tr sm-th mono" role="row"><span>항목</span><span>Tier</span><span>주기</span><span>최근</span><span>상태</span></div>
        {c.data_quality.map((q, i) => (
          <div key={`${q.item}-${i}`} className="sm-tr" role="row" data-testid="semi-quality-row" data-status={q.status}>
            <span className="sm-name">{q.item}<small> {q.source}</small></span>
            <span className="mono" data-label="Tier">{q.tier ?? "–"}</span>
            <span className="mono" data-label="주기">{q.frequency ?? "–"}</span>
            <span className="mono" data-label="최근">{q.last ? q.last.slice(0, 10) : "–"}</span>
            <b className="mono" data-label="상태" style={{ color: QUALITY_COLOR[q.status] ?? "var(--muted)" }}>{q.status}</b>
          </div>
        ))}
      </div>
      {c.coverage_table?.length ? (
        <>
          <h3 className="sm-sub mono">PRODUCT HISTORY COVERAGE</h3>
          <div className="sm-table sm-covtab" role="table" data-testid="semi-coverage-table">
            <div className="sm-tr sm-th mono" role="row"><span>PRODUCT</span><span>SPOT</span><span>CONTRACT</span><span>PREMIUM</span><span>RAW OBS</span><span>MAX GAP</span><span>COVERAGE</span></div>
            {c.coverage_table.map((r) => (
              <div key={r.id} className="sm-tr" role="row" data-testid="semi-coverage-row" data-id={r.id} data-coverage={r.coverage} data-class={r.history_class}>
                <span className="sm-name">{r.label}<small className="mono"> {r.frequency} · {r.history_start ?? "–"}~{r.history_end ?? "–"} · {Object.entries(r.windows).map(([k, v]) => `${k} ${v === "GOOD" ? "✓" : v === "MONTHLY" ? "M" : "P"}`).join(" ")}
                  {r.quality ? ` · ${Object.entries(r.quality).map(([g, n]) => `${g}:${n}`).join(" ")}` : ""}</small>
                  {r.reason ? <small className="sm-reason"> {r.coverage} · Available From {r.available_from ?? "–"} — {r.reason}</small> : null}</span>
                <span className="mono" data-label="SPOT">{r.spot_history_months}M</span>
                <span className="mono" data-label="CONTRACT">{r.contract_history_months === null ? "–" : `${r.contract_history_months}M`}</span>
                <span className="mono" data-label="PREMIUM">{r.premium_history_months === null ? "–" : `${r.premium_history_months}M`}<small> {r.premium_type}</small></span>
                <span className="mono" data-label="RAW OBS">{r.raw_obs}{r.expected_obs ? <small> /{r.expected_obs}</small> : null}{r.expected_weeks ? <small> · wk {r.observed_weeks}/{r.expected_weeks}</small> : null}</span>
                <span className="mono" data-label="MAX GAP">{r.max_gap ?? "–"}d<small> · {r.days_since === 0 ? "Today" : r.days_since === null ? "–" : `${r.days_since}D AGO`}</small></span>
                <b className="mono" data-label="COVERAGE" style={{ color: HQ_COLOR[r.history_class ?? ""] ?? (r.coverage === "GOOD" ? "var(--ok)" : "var(--warn)") }}>{r.history_class ?? r.coverage}<small> {r.history_label && r.history_label !== r.history_class ? r.history_label : ""}</small></b>
              </div>
            ))}
          </div>
          <p className="sm-note">SPOT/CONTRACT/PREMIUM = 실제 원천 이력 개월 수. RAW OBS = 최근 1년 원천 관측 수 / 기대 관측 수(Daily State 반복값 제외). COVERAGE = 기간 40% · 관측 밀도 30% · 출처 품질 20% · 공백 10% — GOOD 은 덮는 기간 330일 이상 그리고 관측 주 85% 이상. 등급 A = DRAMeXchange·TrendForce 직접 공개, B = Internet Archive 에 보존된 당시 공개 화면. RECONSTRUCTED 는 공개 과거 스냅샷을 조합해 복원했다는 뜻(가짜 값이 아니다). PARTIAL 제품은 다른 제품 값으로 메우지 않는다.</p>
        </>
      ) : null}
      {c.not_supported?.length ? <p className="sm-note">지원 안 함: {c.not_supported.join(" · ")}</p> : null}
    </Panel>
  );
}

export function SemiconductorNotArchived() {
  return (
    <div className="sm-grid">
      <section className="panel sm-panel sm-wide" data-testid="semi-not-archived">
        <div className="panel-body" style={{ color: "var(--muted)" }}>
          <b className="mono" style={{ color: "var(--ink)" }}>SEMICONDUCTOR CYCLE NOT ARCHIVED FOR THIS DATE</b> · 이 날짜 저장본에는 반도체 사이클 섹션이 없습니다. 지금 데이터로 대신 보여 주지 않습니다.
        </div>
      </section>
    </div>
  );
}

export function SemiconductorCycleView({ cycle }: { cycle: SemiconductorCycle }) {
  const c = cycle;
  return (
    <div className="sm-grid" data-testid="semi-view">
      <RegimeCard c={c} />
      <MarketRead c={c} />
      <PriceSnapshot c={c} />
      <PriceChart c={c} />
      <PremiumTable c={c} />
      <Momentum c={c} />
      <Normalized c={c} />
      <History c={c} />
      <ProductMap title="DRAM Product Map" rows={c.dram_map} testid="semi-dram-map" />
      <ProductMap title="NAND Product Map" rows={c.nand_map} testid="semi-nand-map" />
      <Chain title="Spot → Contract Transmission" stages={c.spot_to_contract.stages} testid="semi-spot-contract" note={c.contract.stale ? "계약가 STALE" : undefined} />
      <HbmPanel c={c} />
      <ExportNowcast c={c} />
      <Chain title="Price → Export Transmission" stages={c.price_to_export.stages} testid="semi-price-export" />
      <Fundamental c={c} />
      <Equity c={c} />
      <StockImpact c={c} />
      <News c={c} />
      <Next c={c} />
      <Quality c={c} />
    </div>
  );
}
