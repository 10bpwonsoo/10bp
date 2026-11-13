import type { AiRegime, Cockpit, CkLeaderRow, MarketOverview, MoAiSemiView, MoCrossView, MoEquitySide, MoRatesView, OilRegime, RatesRegime, RsSignal } from "../api/types";
import type { SemiconductorCycle } from "../api/semiconductor";
import { KEY_COLOR, isV2, keyColor, keyText } from "./RegimeStatePanel";

/**
 * MARKET OVERVIEW · 시장 종합 (2026-11-12).
 * 새 판정 · 새 점수를 만들지 않는다 — 숫자 칸은 같은 날짜의 기존 섹션(실시간 cockpit · 금리 · 유가 · AI 센티 · 반도체 사이클)을 그대로 읽고,
 * 해석 칸은 그 섹션들을 읽은 LLM 종합(market_overview)이다. 과거 날짜는 모든 칸이 같은 저장본에서 온다(App 의 selectedDate 하나).
 * 판단(synthesis)이 먼저, 근거 숫자는 그 아래 작게. 상세는 DETAIL → 로 기존 탭.
 */
export type DetailTarget = "live" | "rates" | "oil" | "ai" | "semi";

const sg = (v: number | null | undefined, d = 1, unit = "") => (v === null || v === undefined ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);
const arrowOf = (z: number | null | undefined) => (z === null || z === undefined ? "–" : z >= 1.5 ? "↑↑" : z >= 0.5 ? "↑" : z <= -1.5 ? "↓↓" : z <= -0.5 ? "↓" : "→");
const TONE: Record<string, string> = {
  POSITIVE: "var(--ok)", IMPROVING: "var(--ok)", Bullish: "var(--ok)", Improving: "var(--ok)", Tailwind: "var(--ok)", Low: "var(--ok)", LOW: "var(--ok)",
  MIXED: "var(--warn)", NEUTRAL: "var(--muted)", Mixed: "var(--warn)", Neutral: "var(--muted)", Moderate: "var(--warn)", MODERATE: "var(--warn)", MEDIUM: "var(--warn)",
  NEGATIVE: "var(--crit)", Weak: "var(--crit)", Headwind: "var(--crit)", Elevated: "var(--crit)", ELEVATED: "var(--crit)", High: "var(--crit)", HIGH: "var(--crit)",
  STRONG: "var(--ink)", WEAK: "var(--muted)",
  CONFIRMED: "var(--ok)", STRONG_EQ: "var(--ok)", PARTIAL: "var(--warn)", CONTRADICTED: "var(--crit)", UNAVAILABLE: "var(--faint)",
};
const EQ_TONE: Record<string, string> = { STRONG: "var(--ok)", CONFIRMED: "var(--ok)", PARTIAL: "var(--warn)", MIXED: "var(--warn)", CONTRADICTED: "var(--crit)", UNAVAILABLE: "var(--faint)" };

function Sec({ n, title, ko, area, detail, onDetail, children, testid }: { n: number; title: string; ko?: string; area: string; detail?: DetailTarget; onDetail?: (t: DetailTarget) => void; children: React.ReactNode; testid: string }) {
  return (
    <section className="panel mo-sec" style={{ gridArea: area }} data-testid={testid}>
      <header className="panel-head"><h2 className="panel-title"><span className="mo-n mono">{n}</span> {title}{ko ? <em className="mo-ko"> {ko}</em> : null}</h2>
        {detail && onDetail ? <button type="button" className="mo-detail mono" onClick={() => onDetail(detail)} data-testid={`mo-detail-${detail}`}>DETAIL →</button> : null}</header>
      <div className="panel-body">{children}</div>
    </section>
  );
}
const Read = ({ k, t, testid }: { k: string; t: string | null | undefined; testid?: string }) =>
  t ? <p className="mo-read" data-testid={testid}><span className="mo-k mono">{k}</span> {t}</p> : <p className="mo-read mo-none mono" data-testid={testid}>{k} · 종합 코멘트 없음</p>;
const Kv = ({ k, v, color, sub }: { k: string; v: React.ReactNode; color?: string; sub?: React.ReactNode }) => (
  <div className="mo-kv"><span className="mo-k mono">{k}</span><b style={color ? { color } : undefined}>{v}</b>{sub ? <small>{sub}</small> : null}</div>
);
const Excluded = ({ what }: { what: string }) => <div className="mo-excl mono">{what} · EXCLUDED — 이 날짜 데이터 없음</div>;

/** 주식 확인 상태 → 화면 표기(내부 값은 그대로). △ 부분 · ✓ 확인 · ✕ 반대 */
const EQ_UI: Record<string, { sym: string; ko: string; color: string }> = {
  STRONG: { sym: "✓", ko: "강한 확인", color: "var(--ok)" }, CONFIRMED: { sym: "✓", ko: "확인", color: "var(--ok)" }, PARTIAL: { sym: "△", ko: "부분 확인", color: "var(--warn)" },
  MIXED: { sym: "△", ko: "엇갈림", color: "var(--warn)" }, CONTRADICTED: { sym: "✕", ko: "반대", color: "var(--crit)" }, UNAVAILABLE: { sym: "–", ko: "데이터 없음", color: "var(--faint)" },
};

/** 공식 regime 이 지금 어디로 가려 하는가 — 상태 기계(exit_entry_v2) 값을 한 줄로. legacy 저장본은 공식 · raw 로 */
function regimeFlow(c: Cockpit): { from: string; fromKey: string | null; to: string | null; toKey: string | null; progress: string | null; status: string; sub: string } {
  const n = c.market_now; const st = n.state;
  if (!isV2(st)) { // legacy 저장본: raw 가 다른 쪽으로 진행 중(TRANSITION_WATCH)일 때만 화살표
    const watch = n.transition_status === "TRANSITION_WATCH";
    return { from: n.label_text, fromKey: null, to: watch ? n.raw_text : null, toKey: null, progress: watch ? `${Math.min(n.raw_persistence_days, n.required_days)} / ${n.required_days} DAYS` : null,
             status: watch ? "TRANSITION WATCH" : n.transition_status === "CHANGED" ? "TRANSITION CONFIRMED" : "STABLE", sub: n.transition_status_ko };
  }
  if (st.changed && st.change_kind === "entry") return { from: keyText(st.previous_official), fromKey: st.previous_official, to: keyText(st.official), toKey: st.official, progress: "CONFIRMED", status: "TRANSITION CONFIRMED", sub: "오늘 공식 전환" };
  if (st.changed && st.change_kind === "exit") return { from: keyText(st.exited_regime), fromKey: st.exited_regime, to: keyText("neutral"), toKey: "neutral", progress: "EXIT CONFIRMED", status: "REGIME RELEASED", sub: "이전 레짐 해제 · 새 레짐 미확정" };
  if (st.entry_regime) return { from: keyText(st.official), fromKey: st.official, to: keyText(st.entry_regime), toKey: st.entry_regime, progress: `${Math.min(st.entry_streak, st.entry_required)} / ${st.entry_required} DAYS`,
                                status: "TRANSITION WATCH", sub: st.official !== "neutral" && st.exit_streak > 0 ? `전환 확인 중 · ${keyText(st.official)} 이탈 ${st.exit_streak}/${st.exit_required}` : "" };
  if (st.official !== "neutral" && st.exit_streak > 0) return { from: keyText(st.official), fromKey: st.official, to: null, toKey: null, progress: `EXIT ${Math.min(st.exit_streak, st.exit_required)} / ${st.exit_required}`, status: "EXIT WATCH", sub: "공식 레짐 근거가 약해지는 중" };
  return { from: keyText(st.official), fromKey: st.official, to: null, toKey: null, progress: null, status: "STABLE", sub: st.candidate === st.official ? "오늘 후보도 같은 쪽" : "뚜렷한 새 후보 없음" };
}

function RegimeState({ c, summary }: { c: Cockpit; summary?: string }) {
  const sel = c.market_now.selection;
  const f = regimeFlow(c);
  const watch = f.status !== "STABLE";
  const eq = (["us", "kr", "global"] as const).map((m) => ({ m, label: m === "us" ? "US" : m === "kr" ? "KOREA" : "GLOBAL",
    v: m === "us" ? sel?.us_equity_confirmation : m === "kr" ? sel?.korea_equity_confirmation : sel?.global_equity_confirmation }));
  return (
    <div className="mo-rs" data-testid="mo-regime-state" data-status={f.status}>
      {summary ? <p className="mo-rs-sum" data-testid="mo-state-summary">{summary}</p> : null}
      <span className="mo-k mono">{f.to ? "OFFICIAL → CANDIDATE" : "OFFICIAL"}</span>
      <div className="mo-rs-flow mono" data-testid="mo-regime-flow">
        <span className="mo-rs-from">{f.from}</span>
        {f.to ? <><span className="mo-rs-ar" aria-hidden="true">→</span><span className="mo-rs-to" style={{ color: f.toKey ? keyColor(f.toKey) : "var(--ink)" }} data-testid="mo-regime-to">{f.to}</span></> : null}
      </div>
      <div className="mo-rs-tr mono" data-testid="mo-regime-transition">
        <b style={{ color: watch ? "var(--warn)" : "var(--muted)" }}>{f.status}</b>
        {f.progress ? <b className="mo-rs-days" style={{ color: watch ? "var(--warn)" : "var(--ink)" }} data-testid="mo-regime-days">{f.progress}</b> : null}
        {sel ? <span className="mo-rs-conf" data-testid="mo-regime-conf">CONF {sel.regime_confidence}</span> : null}
        {f.sub ? <span className="mo-rs-sub">{f.sub}</span> : null}
      </div>
      {sel ? (
        <div className="mo-rs-eq mono" data-testid="mo-regime-equity">
          <span className="mo-k">EQUITY CONFIRMATION</span>
          <span className="mo-rs-badges">
            {eq.map(({ m, label, v }) => {
              const u = EQ_UI[v ?? "UNAVAILABLE"] ?? EQ_UI.UNAVAILABLE!;
              return <span key={m} className="mo-rs-badge" title={`${label} ${v ?? "UNAVAILABLE"}`} data-state={v ?? "UNAVAILABLE"}><i>{label}</i> <b style={{ color: u.color }}>{u.sym} {u.ko}</b></span>;
            })}
          </span>
        </div>
      ) : null}
    </div>
  );
}

/**
 * 주식 신호 → 화면 단어 (2026-11-13). 새 계산이 아니라 기존 neutral_equity 신호값을 읽는 표시 규칙 —
 * 백엔드 marketpulse/ai/market_overview.py equity_terms 와 같은 문턱(LLM 이 같은 단어를 보고 쓴다). 문턱을 바꾸면 양쪽을 같이.
 */
export type EqTerms = { trend: string; trendSub: string; breadth: string; breadthSub: string; style: string[] };
const trendWord = (z: number | null) => z === null ? "UNAVAILABLE" : z >= 1.5 ? "STRONG" : z >= 0.5 ? "POSITIVE" : z <= -1.5 ? "WEAK" : z <= -0.5 ? "NEGATIVE" : "NEUTRAL";
const breadthZ = (z: number | null) => z === null ? "UNAVAILABLE" : z >= 1.0 ? "BROAD" : z >= 0.5 ? "IMPROVING" : z <= -1.0 ? "WEAK" : z <= -0.5 ? "NARROW" : "MIXED";
const breadthRatio = (r: number | null) => r === null ? "UNAVAILABLE" : r >= 0.65 ? "BROAD" : r >= 0.5 ? "MIXED" : r >= 0.35 ? "NARROW" : "WEAK";
const relWord = (v: number | null, a: string, b: string) => v === null ? null : v >= 0.5 ? `${a} > ${b}` : v <= -0.5 ? `${b} > ${a}` : `${a} ≈ ${b}`;
export function eqTerms(sigs: RsSignal[], m: "us" | "kr"): EqTerms {
  const g = (k: string) => sigs.find((x) => x.key === k) ?? null;
  const val = (k: string) => { const x = g(k); return x && x.state !== "EXCLUDED" && x.value !== null ? x.value : null; };
  const mean = (xs: (number | null)[]) => { const a = xs.filter((x): x is number => x !== null); return a.length ? a.reduce((p, q) => p + q, 0) / a.length : null; };
  const idx = (m === "us" ? ["spx", "ndx", "rut"] : ["kospi", "kosdaq"]).map(g).filter((x): x is RsSignal => !!x && x.state !== "EXCLUDED" && x.value !== null);
  const trend = trendWord(mean(m === "us" ? [val("spx"), val("ndx")] : [val("kospi"), val("kosdaq")]));
  const trendSub = idx.map((x) => `${x.label} ${arrowOf(x.value)}`).join(" · ");
  if (m === "us") {
    const b = val("breadth_us");
    return { trend, trendSub, breadth: breadthZ(b), breadthSub: b === null ? "상승종목 비율 데이터 없음" : "S&P 500 상승종목 비율 기준",
             style: [relWord(val("small_rel"), "SMALL", "LARGE"), relWord(val("cyc_def"), "CYCLICAL", "DEFENSIVE")].filter((x): x is string => !!x) };
  }
  const whole = val("breadth_kospi"); const proxy = val("breadth_kr");
  const n = /(\d+)개/.exec(g("breadth_kr")?.note ?? "")?.[1];
  return { trend, trendSub, breadth: whole !== null ? breadthZ(whole) : breadthRatio(proxy),
           breadthSub: whole !== null ? "KOSPI 상승종목 비율 기준" : proxy !== null ? `상승 참여율 ${Math.round(proxy * 100)}%${n ? ` · 대표 ${n}종목 기준` : ""}` : "상승종목 비율 데이터 없음",
           style: [relWord(val("kosdaq_rel"), "KOSDAQ", "KOSPI"), relWord(val("cyc_kr"), "CYCLICAL", "INDEX")].filter((x): x is string => !!x) };
}
const BREADTH_TONE: Record<string, string> = { BROAD: "var(--ok)", IMPROVING: "var(--ok)", MIXED: "var(--warn)", NARROW: "var(--warn)", WEAK: "var(--crit)", UNAVAILABLE: "var(--faint)" };

function EqMarket({ m, title, conf, side, sigs }: { m: "us" | "kr"; title: string; conf: string | undefined; side: MoEquitySide | string | undefined; sigs: RsSignal[] | null }) {
  const t = sigs ? eqTerms(sigs, m) : null;
  const obj = side && typeof side === "object" ? side : null;
  const headline = obj ? obj.headline : typeof side === "string" ? side : null;
  const lead = obj ? obj.leadership : null;
  const row = (k: string, v: React.ReactNode, sub: React.ReactNode, color?: string, muted?: boolean, testid?: string) => (
    <div className={`mo-eqc-r${muted ? " muted" : ""}`} data-k={k} data-testid={testid}><span className="mo-k mono">{k}</span><b className="mono" style={color ? { color } : undefined}>{v}</b>{sub ? <small className="mono">{sub}</small> : null}</div>
  );
  return (
    <div className="mo-eqc-col" data-testid={`mo-eq-${m}`}>
      <div className="mo-eqc-head"><b className="mono">{title}</b>{conf ? <span className="mo-eqc-badge mono" style={{ color: EQ_TONE[conf] ?? "var(--ink)", borderColor: EQ_TONE[conf] ?? "var(--rule)" }} data-testid={`mo-eq-${m}-status`}>{conf}</span> : null}</div>
      {headline ? <p className={`mo-eqc-h${obj ? "" : " legacy"}`} data-testid={`mo-eq-${m}-headline`}>{headline}</p> : <p className="mo-eqc-h mo-none mono">해석 없음</p>}
      {obj?.why ? <p className="mo-eqc-why" data-testid={`mo-eq-${m}-why`}><span className="mo-k mono">WHY {conf ?? ""}</span> {obj.why}</p> : <span />}
      {t ? (
        <>
          {row("TREND", t.trend, t.trendSub, undefined, t.trend === "UNAVAILABLE", `mo-eq-${m}-trend`)}
          {row("LEADERSHIP", lead === null ? "–" : lead.length ? lead.join(" / ") : "뚜렷한 주도 없음", null, lead && lead.length ? "var(--ink)" : undefined, !lead || !lead.length, `mo-eq-${m}-lead`)}
          {row("BREADTH", t.breadth === "UNAVAILABLE" ? "Unavailable" : t.breadth, t.breadthSub, BREADTH_TONE[t.breadth], t.breadth === "UNAVAILABLE", `mo-eq-${m}-breadth`)}
          {row("STYLE", t.style[0] ?? "–", t.style[1] ?? null, undefined, !t.style.length, `mo-eq-${m}-style`)}
        </>
      ) : <Excluded what="주식 신호" />}
    </div>
  );
}

/** EQUITY MARKET — 해석 먼저(GLOBAL EQUITY READ) → 미국 vs 한국 같은 형식 비교 → 둘의 차이. 개별 지수 값은 DETAIL → (실시간 탭) */
function Equity({ c, ov }: { c: Cockpit; ov: MarketOverview | null }) {
  const sel = c.market_now.selection;
  const ne = sel?.neutral_equity ?? null;
  const v = ov?.view?.equity_view;
  return (
    <div className="mo-eqx">
      {v?.global_read ? (
        <div className="mo-eqx-global" data-testid="mo-eq-global"><span className="mo-k mono">GLOBAL EQUITY READ</span><p>{v.global_read}</p></div>
      ) : <p className="mo-read mo-none mono" data-testid="mo-eq-global">GLOBAL EQUITY READ · 종합 코멘트 없음</p>}
      <div className="mo-eqc">
        <EqMarket m="us" title="US EQUITY" conf={sel?.us_equity_confirmation} side={v?.us} sigs={ne ? ne.us.signals : null} />
        <EqMarket m="kr" title="KOREA EQUITY" conf={sel?.korea_equity_confirmation} side={v?.korea} sigs={ne ? ne.kr.signals : null} />
      </div>
      {v ? <div className="mo-div" data-testid="mo-divergence"><span className="mo-k mono">US ↔ KOREA</span> <b className="mono">{v.divergence_label}</b> {v.divergence}</div> : null}
      <div className="mo-note mono">TREND = 지수 방향(1D·5D z 혼합, 위험선호 기준) · BREADTH · STYLE 은 실시간 탭 확인 신호를 단어로 옮긴 것 · 지수별 값은 DETAIL →</div>
    </div>
  );
}

function Leadership({ c }: { c: Cockpit }) {
  const L = c.leadership;
  const detail = new Map<string, CkLeaderRow>([...L.leaders, ...L.laggards].map((r) => [r.key, r]));
  const rows = (L.all_rows.length ? L.all_rows : L.leaders).slice(0, 5);
  return (
    <ol className="mo-lead" data-testid="mo-leadership">
      {rows.map((r) => {
        const d = (detail.get(r.key) ?? r).detail;
        const stocks = (d?.key_stocks ?? []).slice(0, 3).map((s) => s.name);
        return (
          <li key={r.key}>
            <div className="mo-lead-h"><b>{r.label}</b> <span className="mono">{r.arrow}</span>
              <span className="mono mo-lead-m">1W 상대 {sg(r.rel_1w)}σ · breadth {r.breadth === null ? "–" : `${r.breadth.toFixed(0)}%`}</span></div>
            {d?.why?.[0] ? <div className="mo-lead-w">{d.why[0]}</div> : null}
            {stocks.length ? <div className="mo-lead-s mono">대표 {stocks.join(" · ")}</div> : null}
          </li>
        );
      })}
    </ol>
  );
}

/** 5일 bp 변화 → 방향 단어(백엔드 bp_dir 와 같은 규칙: 1bp 미만은 FLAT) */
const bpDir = (bp: number | null | undefined) => bp === null || bp === undefined ? null : Math.abs(bp) < 1 ? "FLAT" : bp > 0 ? "RISING" : "FALLING";
const IMPACT: Record<string, { word: string; color: string }> = {
  NEGATIVE: { word: "HEADWIND", color: "var(--crit)" }, POSITIVE: { word: "TAILWIND", color: "var(--ok)" }, MIXED: { word: "MIXED", color: "var(--warn)" }, NEUTRAL: { word: "NEUTRAL", color: "var(--muted)" },
};

/** RATES & INFLATION — 금리 판정(엔진) + 주식 영향을 한 줄로, LLM headline · 원인 한 줄, 핵심 4개(10Y · REAL · BREAKEVEN · CURVE), EQUITY IMPACT 강조. 나머지는 DETAIL → 금리 탭 */
function RatesBlock({ rates, rv }: { rates: RatesRegime; rv: MoRatesView | string | undefined }) {
  const obj = rv && typeof rv === "object" ? rv : null;
  const legacy = typeof rv === "string" ? rv : null;
  const yb = rates.yield_breakdown?.tenors?.find((t) => t.tenor === "10Y") ?? null;
  const short = rates.regime_label.split(" — ")[0];
  const imp = obj ? IMPACT[obj.equity_impact] ?? null : null;
  const bp = (x: number | null | undefined) => (x === null || x === undefined ? "–" : sg(x, 0, "bp"));
  const m: { k: string; v: string; sub: string | null }[] = [
    { k: "10Y YIELD", v: rates.rate_move.level === null ? "–" : `${rates.rate_move.level.toFixed(2)}%`, sub: `5D ${sg(rates.rate_move.change_5d_bp, 0, "bp")}` },
    { k: "REAL YIELD", v: bp(yb?.real_bp), sub: bpDir(yb?.real_bp) },
    { k: "BREAKEVEN", v: bp(yb?.breakeven_bp), sub: bpDir(yb?.breakeven_bp) },
    { k: "CURVE", v: rates.curve_move?.shape ?? rates.curve.shape.replace(/_/g, " ").toUpperCase(), sub: rates.curve_move?.window_label ?? null },
  ];
  return (
    <div className="mo-syn" data-testid="mo-rates-block">
      <div className={obj ? "mo-kick mono" : "mo-big mono"} data-testid="mo-rates-regime">{short}{imp ? <> · <b style={{ color: imp.color }}>EQUITY {imp.word}</b></> : null}</div>
      {obj ? <h3 className="mo-hl" data-testid="mo-rates-headline">{obj.headline}</h3> : null}
      {obj ? <p className="mo-sum" data-testid="mo-rates-summary">{obj.summary}</p> : null}
      <div className="mo-m4 mono" data-testid="mo-rates-metrics">
        {m.map((x) => <div key={x.k} className="mo-m4-i"><span className="mo-k">{x.k}</span><b>{x.v}</b>{x.sub ? <small>{x.sub}</small> : null}</div>)}
      </div>
      {obj ? (
        <div className="mo-impact" style={{ borderColor: imp?.color }} data-testid="mo-rates-impact">
          <div className="mo-impact-h"><span className="mo-k mono">EQUITY IMPACT</span><b className="mono" style={{ color: imp?.color }}>{obj.equity_impact}</b></div>
          <p>{obj.equity_impact_read}</p>
        </div>
      ) : <Read k="EQUITY IMPACT" t={legacy} testid="mo-rates-impact" />}
    </div>
  );
}

/**
 * Cross-asset z → 상태 단어(Meaning > Number). 화살표와 같은 ±0.5 / ±1.5 문턱 — 백엔드 CA_WORDS · ca_state 와 같은 표(LLM 이 같은 단어를 본다).
 * (+강, +약, 중립, −약, −강). Credit 은 스프레드(HY OAS)라 내려가면 개선.
 */
const CA_WORDS: Record<string, [string, string, string, string, string]> = {
  EQUITY: ["STRONG", "FIRM", "FLAT", "SOFT", "WEAK"], RATES: ["RISING", "RISING", "STABLE", "FALLING", "FALLING"], CREDIT: ["STRESSED", "WIDENING", "STABLE", "IMPROVING", "IMPROVING"],
  VOLATILITY: ["SPIKING", "RISING", "STABLE", "CALMING", "CALMING"], USD: ["STRONG", "STRONG", "STABLE", "WEAK", "WEAK"], OIL: ["SURGING", "RISING", "NEUTRAL", "FALLING", "SLIDING"],
  GOLD: ["RISING", "RISING", "STABLE", "FALLING", "FALLING"],
};
export function caState(key: string, z: number | null): string {
  const w = CA_WORDS[key.toUpperCase()] ?? ["RISING", "RISING", "STABLE", "FALLING", "FALLING"];
  return z === null ? "UNAVAILABLE" : z >= 1.5 ? w[0] : z >= 0.5 ? w[1] : z <= -1.5 ? w[4] : z <= -0.5 ? w[3] : w[2];
}
const CA_ROLES: [string, string[]][] = [["RISK ASSETS", ["EQUITY", "CREDIT"]], ["RATES", ["RATES"]], ["VOLATILITY", ["VOLATILITY"]], ["MACRO ASSETS", ["USD", "OIL", "GOLD"]]];
type CaRow = Cockpit["cross_asset"]["rows"][number];

/** OIL / MACRO / CROSS-ASSET — LLM headline · 한 줄 → SUPPORT / RISK(자산 · 상태 단어, σ 는 작게) → OIL 보조 줄 → CROSS-ASSET READ. 금리 숫자는 반복하지 않는다 */
function CrossBlock({ rows, oil, cv }: { rows: CaRow[]; oil: OilRegime | null; cv: MoCrossView | string | undefined }) {
  const obj = cv && typeof cv === "object" ? cv : null;
  const legacy = typeof cv === "string" ? cv : null;
  const by = new Map(rows.map((r) => [r.label, r]));
  const item = (r: CaRow) => (
    <div key={r.key} className={`mo-sr-r${r.z === null ? " muted" : ""}`} title={r.instrument_label} data-testid="mo-cross-row">
      <span>{r.label}</span><b className="mono">{caState(r.key, r.z)}</b><small className="mono num">{r.z === null ? "결측" : `${sg(r.z)}σ`}</small>
    </div>
  );
  const pick = (names: string[]) => names.map((n) => by.get(n)).filter((r): r is CaRow => !!r);
  const used = new Set(obj ? [...obj.support, ...obj.risk] : []);
  const others = rows.filter((r) => !used.has(r.label) && r.key !== "OIL");
  const oilRow = rows.find((r) => r.key === "OIL") ?? null;
  return (
    <div className="mo-syn" data-testid="mo-cross-block">
      {obj ? <h3 className="mo-hl" data-testid="mo-cross-headline">{obj.headline}</h3> : null}
      {obj ? <p className="mo-sum" data-testid="mo-cross-summary">{obj.summary}</p> : null}
      {obj && rows.length ? (
        <div className="mo-sr" data-testid="mo-cross-rows">
          <div className="mo-sr-c" data-testid="mo-cross-support"><span className="mo-k mono" style={{ color: "var(--ok)" }}>SUPPORT</span>{pick(obj.support).map(item)}{obj.support.length ? null : <div className="mo-sr-r muted"><span>–</span></div>}</div>
          <div className="mo-sr-c" data-testid="mo-cross-risk"><span className="mo-k mono" style={{ color: "var(--crit)" }}>RISK</span>{pick(obj.risk).map(item)}{obj.risk.length ? null : <div className="mo-sr-r muted"><span>–</span></div>}</div>
        </div>
      ) : rows.length ? (
        <div className="mo-sr" data-testid="mo-cross-rows">
          {CA_ROLES.map(([role, keys]) => { const rs = rows.filter((r) => keys.includes(r.key)); return rs.length ? <div key={role} className="mo-sr-c"><span className="mo-k mono">{role}</span>{rs.map(item)}</div> : null; })}
        </div>
      ) : null}
      {obj && others.length ? <div className="mo-sr-o mono" data-testid="mo-cross-others"><span className="mo-k">OTHER</span> {others.map((r) => `${r.label} ${caState(r.key, r.z)}`).join(" · ")}</div> : null}
      {oil ? (
        <div className="mo-sr-o mono" data-testid="mo-oil-regime"><span className="mo-k">OIL</span> <b>{oilRow ? caState("OIL", oilRow.z) : "–"}</b> <small>{oil.regime_label}</small></div>
      ) : <div className="mo-sr-o mono mo-none" data-testid="mo-oil-regime">OIL · 이 날짜 데이터 없음</div>}
      <Read k="CROSS-ASSET READ" t={obj ? obj.read : legacy} testid="mo-cross-read" />
    </div>
  );
}

/**
 * 반도체 사이클 증거 점수 → 4개 축 단어(Meaning > Score). 엔진이 종합 점수를 만드는 방식 그대로(가중 평균, 없는 증거는 분모에서 뺀다) 축 안에서만 묶는다 —
 * 백엔드 SEMI_AXES · semi_axes 와 같은 표(LLM 이 같은 단어를 본다). 새 판정이 아니라 기존 증거 점수 · 가중치를 읽는 표시 규칙.
 */
const SEMI_AXES: [string, string[]][] = [["PRICING", ["memory_pricing", "spot_premium", "contract", "premium_breadth"]], ["AI MEMORY", ["hbm"]],
  ["FUNDAMENTAL", ["export", "eps_revision", "supply_news"]], ["EQUITY", ["equity"]]];
const SEMI_SHORT: Record<string, string> = { memory_pricing: "Memory", spot_premium: "Spot", contract: "Contract", premium_breadth: "Breadth", hbm: "HBM", export: "Export", eps_revision: "EPS", supply_news: "Supply", equity: "Equity" };
const axisWord = (x: number | null) => x === null ? "UNAVAILABLE" : x >= 50 ? "STRONG" : x >= 15 ? "IMPROVING" : x <= -50 ? "WEAK" : x <= -15 ? "SOFT" : "MIXED";
export function semiAxes(components: SemiconductorCycle["regime"]["components"]): { axis: string; state: string; sub: string; missing: string }[] {
  return SEMI_AXES.map(([axis, keys]) => {
    const cs = keys.map((k) => components.find((c) => c.key === k)).filter((c): c is NonNullable<typeof c> => !!c);
    const have = cs.filter((c) => c.score !== null);
    const w = have.reduce((p, c) => p + (c.weight ?? 1), 0);
    const val = have.length && w ? have.reduce((p, c) => p + (c.score as number) * (c.weight ?? 1), 0) / w : null;
    return { axis, state: axisWord(val), sub: [...have].sort((x, y) => (y.score as number) - (x.score as number)).map((c) => `${SEMI_SHORT[c.key] ?? c.label} ${sg(c.score, 0)}`).join(" · "),
             missing: cs.filter((c) => c.score === null).map((c) => SEMI_SHORT[c.key] ?? c.label).join(" · ") };
  });
}
/** AI 그룹 이름의 화면용 짧은 표기(값 · 이름 자체는 그대로 — LEADERSHIP 한 줄에 들어가게만) */
const AI_GROUP_SHORT: Record<string, string> = { "Semiconductors / Compute": "Compute Semis", "Networking / Infrastructure": "Networking", "Power / Data Center": "Power · DC", "Software / Application": "Software", "Korea AI Supply Chain": "Korea AI" };
const WORD_TONE: Record<string, string> = { STRONG: "var(--ok)", IMPROVING: "var(--ok)", WIDENING: "var(--ok)", MIXED: "var(--warn)", SOFT: "var(--warn)", NARROWING: "var(--warn)", WEAK: "var(--crit)", UNAVAILABLE: "var(--faint)" };
const CONF_TONE: Record<string, string> = { STRONG: "var(--ok)", PARTIAL: "var(--warn)", WEAK: "var(--crit)", DIVERGING: "var(--crit)" };
const STANCE_TONE: Record<string, string> = { POSITIVE: "var(--ok)", "CAUTIOUS POSITIVE": "var(--ok)", NEUTRAL: "var(--muted)", CAUTIOUS: "var(--warn)", NEGATIVE: "var(--crit)" };
const RELATION_KO: Record<string, string> = { "PRICE > FUNDAMENTALS": "가격이 펀더멘털보다 앞섬", "FUNDAMENTALS > PRICE": "펀더멘털 대비 주가가 뒤처짐", ALIGNED: "가격과 펀더멘털이 같은 방향" };

/** AI & SEMICONDUCTOR — INTEGRATED VIEW(LLM) → AI THEME 4줄 | SEMICONDUCTOR 4축 → AI ↔ SEMICONDUCTOR 확인 → EQUITY IMPLICATION. 전체 점수표는 DETAIL → */
function AiSemiBlock({ ai, semi, av, onDetail }: { ai: AiRegime | null; semi: SemiconductorCycle | null; av: MoAiSemiView | string | undefined; onDetail?: (t: DetailTarget) => void }) {
  const obj = av && typeof av === "object" ? av : null;
  const legacy = typeof av === "string" ? av : null;
  const st = (k: string) => ai?.status_strip.find((x) => x.key === k) ?? null;
  const price = st("price"); const rel = st("relative"); const breadth = st("breadth"); const fund = st("fundamental");
  const strong = (["infra", "software"] as const).map(st).filter((x): x is NonNullable<typeof x> => !!x && x.tone === "good").map((x) => x.label);
  const lead = obj ? obj.ai.leadership : null;
  const axes = semi ? semiAxes(semi.regime.components) : [];
  const row = (k: string, v: React.ReactNode, sub: React.ReactNode, color?: string, muted?: boolean) => (
    <div key={k} className={`mo-eqc-r${muted ? " muted" : ""}`} data-k={k} data-testid="mo-as-row"><span className="mo-k mono">{k}</span><b className="mono" style={color ? { color } : undefined}>{v}</b>{sub ? <small className="mono">{sub}</small> : null}</div>
  );
  const chip = (k: string, v: string | null | undefined, color?: string) => <span className="mo-as-chip"><i>{k}</i> <b style={color ? { color } : undefined}>{v ?? "–"}</b></span>;
  return (
    <div className="mo-syn" data-testid="mo-aisemi-block">
      <div className="mo-as-top" data-testid="mo-as-integrated">
        <span className="mo-k mono">INTEGRATED VIEW</span>
        <div className="mo-as-strip mono" data-testid="mo-as-strip">
          {chip("AI PRICE", price?.value)}<span className="mo-rs-ar" aria-hidden="true">→</span>{chip("SEMICONDUCTOR", semi?.regime.label)}<span className="mo-rs-ar" aria-hidden="true">→</span>
          {obj ? chip("CONFIRMATION", obj.confirmation.status, CONF_TONE[obj.confirmation.status]) : chip("FUNDAMENTALS", fund?.value, fund ? WORD_TONE[fund.value] : undefined)}
        </div>
        {obj ? <h3 className="mo-hl" data-testid="mo-as-headline">{obj.headline}</h3> : null}
        {obj ? <p className="mo-sum" data-testid="mo-as-summary">{obj.summary}</p> : null}
      </div>
      <div className="mo-eqc mo-as-cols">
        <div className="mo-eqc-col" data-testid="mo-ai">
          <div className="mo-eqc-head"><span><b className="mono">AI THEME</b>{ai ? <span className="mo-kick mono" data-testid="mo-ai-regime"> · {ai.regime_label}</span> : null}</span>
            {onDetail ? <button type="button" className="mo-detail mono" onClick={() => onDetail("ai")}>DETAIL →</button> : null}</div>
          {ai ? (
            <>
              {obj ? <p className="mo-eqc-h" data-testid="mo-ai-headline">{obj.ai.headline}</p> : <span />}
              {obj ? <p className="mo-eqc-why" data-testid="mo-ai-why"><span className="mo-k mono">WHY</span> {obj.ai.why}</p> : <span />}
              {row("TREND", price?.value ?? "–", rel ? `vs Nasdaq ${rel.value}` : null, undefined, !price)}
              {row("LEADERSHIP", lead && lead.length ? lead.map((n) => AI_GROUP_SHORT[n] ?? n).join(" + ") : strong.length ? strong.join(" + ") : "–", null, "var(--ink)", !(lead && lead.length) && !strong.length)}
              {row("BREADTH", breadth?.value ?? "–", null, breadth ? WORD_TONE[breadth.value] : undefined, !breadth)}
              {row("FUNDAMENTALS", fund?.value ?? "–", null, fund ? WORD_TONE[fund.value] : undefined, !fund)}
            </>
          ) : <Excluded what="AI 센티" />}
        </div>
        <div className="mo-eqc-col" data-testid="mo-semi">
          <div className="mo-eqc-head"><span><b className="mono">SEMICONDUCTOR</b>{semi ? <span className="mo-kick mono" data-testid="mo-semi-regime"> · {semi.regime.label}{semi.regime.composite !== null ? ` ${sg(semi.regime.composite)}` : ""}</span> : null}</span>
            {onDetail ? <button type="button" className="mo-detail mono" onClick={() => onDetail("semi")}>DETAIL →</button> : null}</div>
          {semi ? (
            <>
              {obj ? <p className="mo-eqc-h" data-testid="mo-semi-headline">{obj.semiconductor.headline}</p> : <span />}
              <span />
              {axes.map((a) => row(a.axis, a.state === "UNAVAILABLE" ? "Unavailable" : a.state, [a.sub, a.missing ? `${a.missing} 없음` : ""].filter(Boolean).join(" · ") || null, WORD_TONE[a.state], a.state === "UNAVAILABLE"))}
            </>
          ) : <Excluded what="반도체 사이클" />}
        </div>
      </div>
      {obj ? (
        <>
          <div className="mo-impact" style={{ borderColor: CONF_TONE[obj.confirmation.status] }} data-testid="mo-as-confirmation">
            <div className="mo-impact-h"><span className="mo-k mono">AI ↔ SEMICONDUCTOR</span><b className="mono" style={{ color: CONF_TONE[obj.confirmation.status] }}>{obj.confirmation.status} CONFIRMATION</b>
              <small className="mono" title={RELATION_KO[obj.confirmation.relation]}>{obj.confirmation.relation}</small></div>
            <p>{obj.confirmation.read}</p>
          </div>
          <div className="mo-impact" style={{ borderColor: STANCE_TONE[obj.equity_implication.stance] }} data-testid="mo-as-implication">
            <div className="mo-impact-h"><span className="mo-k mono">EQUITY IMPLICATION</span><b className="mono" style={{ color: STANCE_TONE[obj.equity_implication.stance] }}>{obj.equity_implication.stance}</b></div>
            <p>{obj.equity_implication.read}</p>
          </div>
        </>
      ) : <Read k="AI ↔ SEMICONDUCTOR READ" t={legacy} testid="mo-aisemi-read" />}
    </div>
  );
}

export function MarketOverviewView({ cockpit: c, overview, overviewError, rates, oil, ai, semi, onDetail, archived }: {
  cockpit: Cockpit | null; overview: MarketOverview | null; overviewError?: string | null; rates: RatesRegime | null; oil: OilRegime | null; ai: AiRegime | null;
  semi: SemiconductorCycle | null; onDetail?: (t: DetailTarget) => void; archived?: boolean;
}) {
  const v = overview?.status === "ok" ? overview.view : null;
  const now = c?.market_now;
  const st = now?.state ?? null;
  const days = c?.history?.days ?? [];
  const caRows = c?.cross_asset.rows ?? [];
  const sdate = overview?.snapshot_date ?? null;
  const upcoming = (rates?.events?.upcoming ?? []).filter((u) => !sdate || u.date >= sdate);
  const why = new Map((v?.catalysts ?? []).map((x) => [`${x.date}|${x.event}`, x]));
  return (
    <div className="mo" data-testid="market-overview">
      {/* 1. MARKET VIEW — 가장 먼저 읽히는 판단 */}
      <section className="panel mo-sec mo-view" style={{ gridArea: "view" }} data-testid="mo-view">
        <header className="panel-head"><h2 className="panel-title"><span className="mo-n mono">1</span> Market View <em className="mo-ko">시장 종합</em></h2>
          <div className="panel-note mono">{overview?.status === "ok" ? `${overview.source === "llm" ? "AI 종합" : "AI 종합 · 세션"}${sdate ? ` · ${sdate} Daily Snapshot` : ""}` : ""}</div></header>
        <div className="panel-body">
          {v ? (
            <>
              <span className="mo-k mono">CURRENT MARKET CALL</span>
              <p className="mo-headline" data-testid="mo-headline">{v.headline}</p>
              <span className="mo-k mono">MARKET SYNTHESIS</span>
              <p className="mo-synth" data-testid="mo-synthesis">{v.market_view}</p>
              <div className="mo-labels mono" data-testid="mo-labels">
                <span><i>REGIME</i><b style={{ color: st ? keyColor(st.official) : "var(--ink)" }}>{v.labels.regime}</b></span>
                <span><i>EQUITY</i><b style={{ color: TONE[v.labels.equity] }}>{v.labels.equity.toUpperCase()}</b></span>
                <span><i>MACRO</i><b style={{ color: TONE[v.labels.macro] }}>{v.labels.macro.toUpperCase()}</b></span>
                <span><i>RISK</i><b style={{ color: TONE[v.labels.risk] }}>{v.labels.risk.toUpperCase()}</b></span>
              </div>
            </>
          ) : (
            <p className="mo-none mono" data-testid="mo-view-none">
              MARKET VIEW 종합 코멘트 없음 — {overviewError ?? overview?.reason ?? (archived ? "이 날짜 저장본에는 종합 코멘트가 없다(NOT ARCHIVED)" : "불러오는 중")}. 아래 칸의 숫자는 같은 날짜 저장 데이터 그대로다.
            </p>
          )}
        </div>
      </section>

      {/* 2. REGIME & MARKET STATE — 공식 → 후보 · 전환 진행 · 주식 확인을 세 줄로(같은 값, 표시만 압축) */}
      <Sec n={2} title="Regime & Market State" area="regime" detail="live" onDetail={onDetail} testid="mo-regime">
        {now ? <RegimeState c={c!} summary={v?.state_summary} /> : <Excluded what="실시간 regime" />}
        {now && days.length ? (
          <div className="mo-strip" data-testid="mo-regime-strip" title={days.map((d) => `${d.date} ${d.display_label}`).join("\n")}>
            <span className="mo-k mono">OFFICIAL · 1M</span>
            <span className="mo-strip-c">{days.map((d) => <i key={d.date} style={{ background: KEY_COLOR[d.display_regime] ?? "var(--rule)" }} />)}</span>
          </div>
        ) : null}
        {now ? <Read k="REGIME READ" t={v?.regime_read} testid="mo-regime-read" /> : null}
      </Sec>

      {/* 3. WHAT IS DRIVING THE MARKET */}
      <Sec n={3} title="What Is Driving the Market?" area="drivers" testid="mo-drivers">
        {v ? (
          <ul className="mo-list">
            {v.key_drivers.map((d) => (
              <li key={d.name} data-testid="mo-driver"><div className="mo-li-h"><b>{d.name}</b><span className="mono" style={{ color: TONE[d.direction] }}>{d.direction}</span><span className="mono mo-sub">{d.strength}</span></div><div className="mo-li-t">{d.read}</div></li>
            ))}
          </ul>
        ) : <Read k="KEY DRIVERS" t={null} />}
      </Sec>

      {/* 4. EQUITY MARKET */}
      <Sec n={4} title="Equity Market" ko="미국 · 한국" area="equity" detail="live" onDetail={onDetail} testid="mo-equity">
        {c ? <Equity c={c} ov={overview} /> : <Excluded what="주식시장" />}
      </Sec>

      {/* 5. RATES & INFLATION — 판단 → 원인 → 핵심 4개 → 주식 영향 */}
      <Sec n={5} title="Rates & Inflation" area="rates" detail="rates" onDetail={onDetail} testid="mo-rates">
        {rates ? <RatesBlock rates={rates} rv={v?.rates_view} /> : <Excluded what="금리" />}
      </Sec>

      {/* 6. OIL / MACRO / CROSS-ASSET — 자산 관계 먼저, 유가는 보조(주요 driver 일 때만 LLM 이 headline 에 올린다) */}
      <Sec n={6} title="Oil / Macro / Cross-Asset" area="cross" detail="oil" onDetail={onDetail} testid="mo-cross">
        <CrossBlock rows={caRows} oil={oil} cv={v?.cross_asset_view} />
      </Sec>

      {/* 7. AI & SEMICONDUCTOR CYCLE — 통합 판단 → AI 주가 → 반도체 업황 → 서로 확인되는가 → 주식 의미 */}
      <Sec n={7} title="AI & Semiconductor Cycle" area="aisemi" testid="mo-aisemi">
        <AiSemiBlock ai={ai} semi={semi} av={v?.ai_semiconductor_view} onDetail={onDetail} />
      </Sec>

      {/* 8. MARKET LEADERSHIP */}
      <Sec n={8} title="Market Leadership" area="lead" detail="live" onDetail={onDetail} testid="mo-lead">
        <Read k="LEADERSHIP" t={v?.leadership_view} testid="mo-lead-read" />
        {c ? <Leadership c={c} /> : <Excluded what="리더십" />}
      </Sec>

      {/* 9. STYLE & SECTOR VIEW */}
      <Sec n={9} title="Style & Sector View" area="style" testid="mo-style">
        {v ? (
          <div className="mo-eq">
            <div className="mo-eq-col">
              <span className="mo-k mono">STYLE</span>
              <table className="mo-tbl"><tbody>{v.style_view.map((s) => <tr key={s.style} data-testid="mo-style-row"><td className="mono">{s.style}</td><td className="mono" style={{ color: TONE[s.view] }}>{s.view}</td><td>{s.read}</td></tr>)}</tbody></table>
            </div>
            <div className="mo-eq-col" data-testid="mo-sector">
              <span className="mo-k mono">SECTOR</span>
              {(["positive", "watch", "negative"] as const).map((b) => (
                <div key={b} className="mo-sector-r"><b className="mono" style={{ color: b === "positive" ? "var(--ok)" : b === "negative" ? "var(--crit)" : "var(--warn)" }}>{b.toUpperCase()}</b><span>{v.sector_view[b].length ? v.sector_view[b].join(" · ") : "–"}</span></div>
              ))}
              {v.sector_view.read ? <p className="mo-li-t">{v.sector_view.read}</p> : null}
            </div>
          </div>
        ) : <Read k="STYLE & SECTOR" t={null} />}
      </Sec>

      {/* 10. RISK MAP */}
      <Sec n={10} title="Risk Map" area="risk" testid="mo-risk">
        {v ? (
          <ul className="mo-list">{v.top_risks.map((r) => <li key={r.risk} data-testid="mo-risk-row"><div className="mo-li-h"><b>{r.risk}</b><span className="mono" style={{ color: TONE[r.level] }}>{r.level}</span></div><div className="mo-li-t">{r.read}</div></li>)}</ul>
        ) : <Read k="RISK MAP" t={null} />}
      </Sec>

      {/* 11. CATALYSTS & EVENTS — 저장된 일정(그 날짜 이후)만, 의미는 LLM */}
      <Sec n={11} title="Catalysts & Events" area="cat" detail="rates" onDetail={onDetail} testid="mo-cat">
        {upcoming.length ? (
          <ul className="mo-list">
            {upcoming.slice(0, 6).map((u) => {
              const w = why.get(`${u.date}|${u.name}`);
              return (
                <li key={`${u.date}-${u.name}`} data-testid="mo-cat-row"><div className="mo-li-h"><b className="mono">{u.date.slice(5).replace("-", "/")}</b><b>{u.name}</b>{w ? <span className="mono" style={{ color: TONE[w.sensitivity] }}>{w.sensitivity}</span> : <span className="mono mo-sub">{u.importance}</span>}</div>
                  {w ? <div className="mo-li-t">{w.why}</div> : null}</li>
              );
            })}
          </ul>
        ) : <Excluded what="예정 이벤트" />}
      </Sec>

      {/* 12. WHAT MATTERS NEXT */}
      <Sec n={12} title="What Matters Next" area="next" testid="mo-next">
        {v ? (
          <ol className="mo-next">{v.what_matters_next.map((x) => <li key={x.title} data-testid="mo-next-row"><b>{x.title}</b><span>{x.condition}</span><em>→ {x.implication}</em></li>)}</ol>
        ) : <Read k="WHAT MATTERS NEXT" t={null} />}
      </Sec>

      {/* 13. PORTFOLIO IMPLICATION — 매매 지시가 아니라 관점 */}
      <Sec n={13} title="Portfolio Implication" area="port" testid="mo-port">
        {v ? (
          <div className="mo-port">
            <Kv k="EQUITY STANCE" v={v.portfolio_implication.equity_stance} />
            <Kv k="STYLE" v={v.portfolio_implication.style} />
            <Kv k="SECTOR" v={v.portfolio_implication.sector} />
            <Kv k="RISK CONTROL" v={v.portfolio_implication.risk_control} />
            <Kv k="HEDGE / WATCH" v={v.portfolio_implication.hedge_watch} />
            <div className="mo-note mono">투자 관점(Overweight bias · Neutral · Underweight bias · Watch)이며 매매 지시가 아니다</div>
          </div>
        ) : <Read k="PORTFOLIO IMPLICATION" t={null} />}
      </Sec>
    </div>
  );
}
