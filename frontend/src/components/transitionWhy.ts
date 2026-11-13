/**
 * RECENT TRANSITIONS — 레짐 전환 이유를 사람이 읽는 문장으로 (2026-11-04).
 *
 * 새 판단을 만들지 않는다. 화면이 이미 가진 값(전환 기록의 factor 변화)과, 그 전환 날짜의 데이터를 담은
 * 저장 스냅샷(다음 평일 07:30 KST 저장본 — Today's Market Drivers · 정책/지표 이벤트 · 태깅된 뉴스)만 읽어
 * "무슨 일이 있었고 → 시장이 어떻게 반응했고 → 그래서 왜 이 regime 으로 갔는지" 를 고른다.
 *
 * 고정 우선순위가 없다 — 이벤트 · 뉴스 · 가격 · 신용 · 변동성 · 금리 · 유동성 · 원자재 후보를 모두 같은 저울
 * (그날 실제로 움직인 크기 × 새 regime 쪽으로 미는가)에 올려 2~3개만 쓴다. 이벤트 · 뉴스는 그 자체로 점수가
 * 없고, 같은 날 그와 이어지는 시장 반응이 실제로 컸을 때만 그 반응의 크기로 후보가 된다(이벤트가 있다는 이유만으로
 * 원인이 되지 않는다). 저장 스냅샷이 없는 날(10/12 이전)은 factor 변화로만 쓰고 "이벤트 없음" 을 단정하지 않는다.
 *
 * Look-ahead 없음: 날짜 D 행의 스냅샷 = D 다음 평일 07:30 KST 저장본(그 cutoff 까지 알려진 것만 담긴 파일).
 * 이벤트는 (직전 행 날짜, D] 에 발표된 것만, 뉴스는 그 스냅샷 cutoff 이전 · 직전 행 이후 발행분만.
 */
import type { CkRegimeTransition } from "../api/types";

/** 전환 날짜의 스냅샷에서 이 모듈이 읽는 부분만 */
export interface TransitionDayDoc {
  snapshot_date: string;
  cutoff?: string | null;
  cockpit?: { drivers?: DayDriver[] | null; history?: { days?: { date: string }[] } | null } | null;
  rates_regime?: { events?: { recent?: DayRelease[] | null; policy?: DayPolicy[] | null } | null } | null;
  snapshot?: { events?: DayNews[] | null } | null;
}
export interface DayDriver { key: string; direction: string; strength: number; importance: number; persistent?: boolean; source?: string; evidence?: { label: string; z: number | null; available?: boolean }[] }
export interface DayRelease { kind?: string; key?: string; date: string; title: string; label: string; importance?: string }
export interface DayPolicy { bank: string; name?: string; date: string; decision: string; tone?: string; decision_label?: string }
export interface DayNews { event?: string; event_type?: string; themes?: string[]; theme_sentiment?: Record<string, number>; theme_direction?: Record<string, string>; sentiment?: number; impact_score?: number; timestamp?: string; reason?: string }

export type Basis = "event" | "news" | "market" | "internal" | "llm";
export interface Cand { id: string; group: string; kind: "event" | "news" | "market" | "factor"; phrase: string; chip: string; sign: number; score: number; raw: string; context?: { neg: string; pos: string }; persistent?: boolean; links?: string[] }
export interface TransitionWhy {
  why: string;
  chips: string[];
  meaning: string;
  basis: Basis;
  /** 화면 아래 작은 글씨 — 원자료 */
  evidence: string[];
  used: Cand[];
  dayDoc: string | null;
}

const RANK: Record<string, number> = { liquidity_stress: 0, risk_off: 0, neutral: 1, risk_on: 2 };

/** 새 regime 으로 가려면 시장이 어느 쪽으로 움직여야 하는가: +1 위험선호 쪽, -1 스트레스 쪽 */
export function neededSign(from: string, to: string): number {
  const a = RANK[from] ?? 1, b = RANK[to] ?? 1;
  return b > a ? 1 : b < a ? -1 : 0;
}

/* ── 그날 Today's Market Drivers 한 줄 → 사람이 읽는 말. sign = 위험선호(+) / 스트레스(−) 쪽, 0 = 맥락(물가 등) ── */
type DrvText = { phrase: (strong: boolean) => string; chip: string; sign: number; group: string; context?: { neg: string; pos: string } };
const DRV: Record<string, DrvText> = {
  "credit_stress:up": { phrase: () => "신용 스프레드 확대", chip: "Credit Stress ↑", sign: -1, group: "credit" },
  "credit_stress:down": { phrase: () => "신용 스프레드 안정", chip: "Credit 안정", sign: 1, group: "credit" },
  "equity_beta:down": { phrase: (s) => (s ? "주식 전반의 급락" : "주식 전반의 약세"), chip: "주식 ↓", sign: -1, group: "equity" },
  "equity_beta:up": { phrase: (s) => (s ? "주식 전반의 강한 반등" : "주식 전반의 반등"), chip: "주식 ↑", sign: 1, group: "equity" },
  "volatility_regime:up": { phrase: () => "변동성 확대", chip: "변동성 ↑", sign: -1, group: "vol" },
  "volatility_regime:down": { phrase: () => "변동성 완화", chip: "변동성 ↓", sign: 1, group: "vol" },
  "long_end_rates:down": { phrase: () => "안전자산 쪽 장기금리 하락", chip: "장기금리 ↓", sign: -0.5, group: "rates" },
  "long_end_rates:up": { phrase: () => "장기금리 상승에 따른 금리 부담", chip: "장기금리 ↑", sign: -0.4, group: "rates" },
  "fed_path:down": { phrase: () => "정책금리 인하 기대", chip: "단기금리 ↓", sign: 0.3, group: "policy" },
  "fed_path:up": { phrase: () => "정책금리 부담", chip: "단기금리 ↑", sign: -0.5, group: "policy" },
  "oil:down": { phrase: (s) => (s ? "유가 급락" : "유가 하락"), chip: "유가 ↓", sign: 0, group: "oil", context: { neg: "물가 부담은 덜었지만", pos: "물가 부담이 줄어든 가운데" } },
  "oil:up": { phrase: (s) => (s ? "유가 급등" : "유가 상승"), chip: "유가 ↑", sign: -0.4, group: "oil", context: { neg: "물가 부담이 커진 가운데", pos: "물가 부담이 커졌지만" } },
  "ai_semi_relative:down": { phrase: () => "AI·반도체주 약세", chip: "AI·반도체 ↓", sign: -0.7, group: "growth" },
  "ai_semi_relative:up": { phrase: () => "AI·반도체주 강세", chip: "AI·반도체 ↑", sign: 0.7, group: "growth" },
  "korea:down": { phrase: () => "한국 증시 약세", chip: "KOSPI ↓", sign: -0.5, group: "korea" },
  "korea:up": { phrase: () => "한국 증시 강세", chip: "KOSPI ↑", sign: 0.5, group: "korea" },
  "gold_real:down": { phrase: () => "금 약세", chip: "금 ↓", sign: 0, group: "gold" },
  "gold_real:up": { phrase: () => "금 강세", chip: "금 ↑", sign: -0.3, group: "gold" },
};

/* ── 전환 기록의 factor 변화("Risk Appetite -2.4 → -1.0") → 내부 변화 후보 ── */
const FACTOR: Record<string, { up: [string, string]; down: [string, string]; sign: (d: number) => number; group: string }> = {
  "Risk Appetite": { up: ["위험선호 회복", "위험선호 ↑"], down: ["위험선호 약화", "위험선호 ↓"], sign: (d) => Math.sign(d), group: "equity" },
  Liquidity: { up: ["유동성 여건 개선", "유동성 ↑"], down: ["유동성 여건 악화", "유동성 ↓"], sign: (d) => Math.sign(d), group: "liquidity" },
  Credit: { up: ["신용 부담 확대", "Credit ↑"], down: ["신용 부담 완화", "Credit ↓"], sign: (d) => -Math.sign(d), group: "credit" },
  Inflation: { up: ["물가 압력 확대", "물가 압력 ↑"], down: ["물가 압력 둔화", "물가 압력 ↓"], sign: () => 0, group: "inflation" },
};

/* 같은 부호 안에서 줄어든 변화: upNeg = 음수에서 덜 음수로(0 아래), downPos = 양수에서 덜 양수로(0 위) */
const FADE: Record<string, Record<string, string>> = {
  "Risk Appetite": { upNeg: "위험선호 약세의 완화", downPos: "위험선호 둔화" },
  Liquidity: { upNeg: "유동성 악화의 완화", downPos: "유동성 개선 흐름 둔화" },
  Credit: { upNeg: "신용 안정 흐름 약화", downPos: "신용 부담 완화" },
  Inflation: { upNeg: "물가 둔화 흐름 약화", downPos: "물가 압력 둔화" },
};

/* ── 전환 기록의 '주도 변수' 줄("주도 변수 US 30Y Yield -1.9σ · US 10Y Yield -1.5σ") → 시장 후보(약하게). 그날 스냅샷이 없을 때의 보조 ── */
const VAR: { re: RegExp; up: string; down: string }[] = [
  { re: /^US HY OAS$/, up: "credit_stress:up", down: "credit_stress:down" },
  { re: /^VIX$/, up: "volatility_regime:up", down: "volatility_regime:down" },
  { re: /^(S&P 500|Nasdaq 100|Russell 2000)$/, up: "equity_beta:up", down: "equity_beta:down" },
  { re: /^US (10Y|30Y) Yield$/, up: "long_end_rates:up", down: "long_end_rates:down" },
  { re: /^US 2Y Yield$/, up: "fed_path:up", down: "fed_path:down" },
  { re: /^(브렌트 원유|WTI 원유)$/, up: "oil:up", down: "oil:down" },
  { re: /^(KOSPI|KOSDAQ)$/, up: "korea:up", down: "korea:down" },
  { re: /^금$/, up: "gold_real:up", down: "gold_real:down" },
];
function varCands(t: CkRegimeTransition): Cand[] {
  const out: Cand[] = [];
  const line = t.evidence.find((e) => e.startsWith("주도 변수"));
  if (!line) return out;
  for (const part of line.replace(/^주도 변수\s*/, "").split(" · ")) {
    const m = /^(.+?) ([+-−]?[\d.]+)σ/.exec(part.trim()); if (!m) continue;
    const z = parseFloat(m[2]!.replace("−", "-")); const v = VAR.find((x) => x.re.test(m[1]!)); if (!v || !Number.isFinite(z)) continue;
    const k = z >= 0 ? v.up : v.down, d = DRV[k]; if (!d) continue;
    if (out.some((o) => o.id === k)) continue;
    out.push({ id: k, group: d.group, kind: "market", phrase: d.phrase(Math.abs(z) >= 2), chip: d.chip, sign: d.sign, score: Math.abs(z) * 0.35, raw: part.trim(), context: d.context });
  }
  return out;
}

/* ── history 행의 factor 값으로 본 최근 며칠 흐름(D 와 3행 전) ── */
const TREND: Record<string, { up: string; down: string; upChip: string; downChip: string; sign: (d: number) => number; group: string }> = {
  RiskAppetite: { up: "최근 며칠간의 위험선호 회복", down: "최근 며칠간의 위험선호 약화", upChip: "위험선호 ↑", downChip: "위험선호 ↓", sign: (d) => Math.sign(d), group: "equity" },
  Liquidity: { up: "최근 며칠간의 유동성 여건 개선", down: "최근 며칠간의 유동성 여건 악화", upChip: "유동성 ↑", downChip: "유동성 ↓", sign: (d) => Math.sign(d), group: "liquidity" },
  Credit: { up: "최근 며칠간 누적된 신용 부담", down: "최근 며칠간의 신용 부담 완화", upChip: "Credit ↑", downChip: "Credit ↓", sign: (d) => -Math.sign(d), group: "credit" },
};
export interface TrendDay { date: string; factors?: Record<string, number | null> }
function trendCands(days: TrendDay[] | undefined, date: string): Cand[] {
  if (!days?.length) return [];
  const i = days.findIndex((x) => x.date === date); if (i < 3) return [];
  const out: Cand[] = [];
  for (const [k, t] of Object.entries(TREND)) {
    const a = days[i - 3]!.factors?.[k], b = days[i]!.factors?.[k];
    if (a == null || b == null) continue;
    const d = b - a; if (Math.abs(d) < 1.0) continue;
    out.push({ id: `trend:${k}`, group: t.group, kind: "factor", phrase: d > 0 ? t.up : t.down, chip: d > 0 ? t.upChip : t.downChip, sign: t.sign(d), score: Math.abs(d) * 0.35, raw: `${{ RiskAppetite: "Risk Appetite", Liquidity: "Liquidity", Credit: "Credit" }[k] ?? k} 3거래일 전 ${a >= 0 ? "+" : ""}${a.toFixed(1)} → 그날 ${b >= 0 ? "+" : ""}${b.toFixed(1)}` });
  }
  return out;
}

/* ── 이벤트(지표 · 정책): 그날 이어지는 시장 반응이 있을 때만. 반응 = 아래 driver 중 실제 움직인 것 ── */
type EvText = { phrase: string; chip: string; react: string[] };
function releaseText(r: DayRelease): EvText | null {
  const t = r.title.toUpperCase();
  const name = t.includes("CPI") ? "CPI" : t.includes("PCE") ? "PCE" : t.includes("NFP") || t.includes("고용") || t.includes("PAYROLL") ? "고용지표" : r.title;
  const hot = ["HOT", "STRONG", "HIGH", "ABOVE"].includes(r.label), cool = ["COOL", "SOFT", "BELOW"].includes(r.label), weak = r.label === "WEAK";
  if (hot) return { phrase: name === "고용지표" ? "예상보다 강한 고용지표" : `예상보다 높은 ${name}`, chip: `${name} 상방 서프라이즈`, react: ["long_end_rates:up", "fed_path:up", "equity_beta:down", "ai_semi_relative:down", "volatility_regime:up", "credit_stress:up"] };
  if (cool) return { phrase: `예상보다 낮은 ${name}`, chip: `${name} 하방 서프라이즈`, react: ["long_end_rates:down", "fed_path:down", "equity_beta:up", "volatility_regime:down"] };
  if (weak) return { phrase: name === "고용지표" ? "예상보다 약한 고용지표" : `예상보다 약한 ${name}`, chip: `${name} 부진`, react: ["fed_path:down", "long_end_rates:down", "equity_beta:down", "credit_stress:up", "volatility_regime:up"] };
  return null;
}
function policyText(p: DayPolicy): EvText | null {
  const bank = p.bank === "FED" ? "연준" : p.bank === "ECB" ? "ECB" : p.bank === "BOJ" ? "일본은행" : p.bank === "BOK" ? "한국은행" : p.bank;
  const hawk = p.tone === "HAWKISH" || p.decision === "HIKE", dove = p.tone === "DOVISH" || p.decision === "CUT";
  if (hawk) return { phrase: `${bank}의 매파적 결정(${p.decision === "HIKE" ? "금리 인상" : "동결"})`, chip: `${bank} 매파`, react: ["fed_path:up", "long_end_rates:up", "equity_beta:down", "volatility_regime:up", "credit_stress:up"] };
  if (dove) return { phrase: `${bank}의 완화적 결정`, chip: `${bank} 완화`, react: ["fed_path:down", "long_end_rates:down", "equity_beta:up", "volatility_regime:down"] };
  return null;
}
/* 뉴스 주제 → 이어지는 시장 반응 */
const NEWS_LINK: Record<string, { ko: string; up: string[]; down: string[] }> = {
  oil: { ko: "유가", up: ["oil:up"], down: ["oil:down"] },
  energy: { ko: "에너지", up: ["oil:up"], down: ["oil:down"] },
  geopolitical_risk: { ko: "지정학 긴장", up: ["volatility_regime:up", "oil:up", "gold_real:up"], down: ["volatility_regime:down"] },
  defense: { ko: "지정학 긴장", up: ["volatility_regime:up", "oil:up"], down: [] },
  ai: { ko: "AI·반도체", up: ["ai_semi_relative:up"], down: ["ai_semi_relative:down"] },
  semiconductor: { ko: "AI·반도체", up: ["ai_semi_relative:up"], down: ["ai_semi_relative:down"] },
  rates: { ko: "금리", up: ["long_end_rates:up", "fed_path:up"], down: ["long_end_rates:down", "fed_path:down"] },
  inflation: { ko: "물가", up: ["long_end_rates:up", "fed_path:up"], down: ["long_end_rates:down"] },
  korea_governance: { ko: "한국 증시", up: ["korea:up"], down: ["korea:down"] },
};

/* ── 전환 쌍별 결론(그래서 왜 이 regime 인가)과 시장 의미 ── */
const CONSEQ: Record<string, { why: string; meaning: string }> = {
  "risk_on>neutral": { why: "Risk-On 을 받치던 확인 신호가 약해졌습니다", meaning: "강세는 약해졌지만 Risk-Off 로 넘어간 것은 아직 아님" },
  "neutral>liquidity_stress": { why: "유동성 스트레스 쪽 신호가 우세해졌습니다", meaning: "방어적 시장으로 이동" },
  "risk_on>liquidity_stress": { why: "위험선호가 무너지고 곧바로 유동성 스트레스로 넘어갔습니다", meaning: "강세 국면에서 방어 국면으로 급반전" },
  "liquidity_stress>neutral": { why: "스트레스 신호가 누그러져 Liquidity Stress 판정이 풀렸습니다", meaning: "스트레스는 풀렸지만 위험선호 회복은 아직 확인 전" },
  "neutral>risk_on": { why: "Risk-On 확인 신호가 갖춰졌습니다", meaning: "위험자산 선호가 다시 우세" },
  "liquidity_stress>risk_on": { why: "스트레스 국면이 끝나고 Risk-On 으로 돌아섰습니다", meaning: "방어 국면에서 위험선호 국면으로 빠르게 반전" },
};
function conseq(from: string, to: string): { why: string; meaning: string } {
  return CONSEQ[`${from}>${to}`] ?? { why: "시장 판정이 바뀌었습니다", meaning: "판정 전환" };
}

/* ── 한국어 조사 ── */
function batchim(word: string): boolean {
  const ch = word.trim().slice(-1);
  const c = ch.charCodeAt(0);
  if (c >= 0xac00 && c <= 0xd7a3) return (c - 0xac00) % 28 !== 0;
  return /[0-9LMNRlmnr]$/.test(ch);
}
const wa = (w: string) => `${w}${batchim(w) ? "과" : "와"}`;
const iga = (w: string) => `${w}${batchim(w) ? "이" : "가"}`;
const euro = (w: string) => { const ch = w.trim().slice(-1), c = ch.charCodeAt(0); const jong = c >= 0xac00 && c <= 0xd7a3 ? (c - 0xac00) % 28 : -1; return `${w}${jong > 0 && jong !== 8 ? "으로" : "로"}`; };

/* ── 후보 만들기 ── */
function driverCands(doc: TransitionDayDoc | null): Cand[] {
  const out: Cand[] = [];
  for (const d of doc?.cockpit?.drivers ?? []) {
    const k = `${d.key}:${d.direction}`, t = DRV[k];
    if (!t || d.source === "alternative") continue;
    const strong = Math.abs(d.strength) >= 0.8;
    const ev = (d.evidence ?? []).filter((e) => e.available !== false && e.z !== null).slice(0, 3).map((e) => `${e.label} ${e.z! >= 0 ? "+" : ""}${e.z!.toFixed(1)}σ`).join(" · ");
    out.push({ id: k, group: t.group, kind: "market", phrase: t.phrase(strong), chip: t.chip, sign: t.sign, score: Math.abs(d.strength) * (d.importance || 1), raw: `${t.chip}${ev ? ` (${ev})` : ""}`, context: t.context, persistent: !!d.persistent });
  }
  return out;
}
function factorCands(t: CkRegimeTransition): Cand[] {
  const out: Cand[] = [];
  for (const line of t.evidence) {
    const m = /^(Risk Appetite|Liquidity|Credit|Inflation) ([+-−]?[\d.]+) → ([+-−]?[\d.]+)$/.exec(line.trim());
    if (!m) continue;
    const a = parseFloat(m[2]!.replace("−", "-")), b = parseFloat(m[3]!.replace("−", "-")), d = b - a, f = FACTOR[m[1]!]!;
    if (!Number.isFinite(d) || Math.abs(d) < 0.8) continue;
    const fade = FADE[m[1]!]?.[d > 0 ? (b <= 0 ? "upNeg" : "") : (b >= 0 ? "downPos" : "")];
    const [phrase0, chip] = d > 0 ? f.up : f.down;
    out.push({ id: `factor:${m[1]}`, group: f.group, kind: "factor", phrase: fade || phrase0, chip, sign: f.sign(d), score: Math.abs(d) * 0.45, raw: line });
  }
  return out;
}
function inWindow(date: string, prev: string | null, d: string): boolean {
  return date <= d && (prev === null ? date >= addDays(d, -3) : date > prev);
}
function addDays(ymd: string, n: number): string {
  const t = new Date(`${ymd}T00:00:00Z`); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10);
}
/** 이벤트 · 뉴스 — 반응이 실제로 있을 때만, 그 반응 크기로 */
function catalystCands(doc: TransitionDayDoc | null, d: string, prev: string | null, market: Cand[], need: number): { cands: Cand[]; seen: number } {
  const out: Cand[] = []; let seen = 0;
  const react = (keys: string[]) => market.filter((c) => keys.includes(c.id) && Math.sign(c.sign) === need);
  const ev = doc?.rates_regime?.events;
  for (const r of ev?.recent ?? []) {
    if (!inWindow(r.date, prev, d)) continue;
    seen++;
    const tx = releaseText(r); if (!tx) continue;
    const rs = react(tx.react); if (!rs.length) continue;
    out.push({ id: `event:${r.key ?? r.title}:${r.date}`, group: "event", kind: "event", phrase: tx.phrase, chip: tx.chip, sign: need, score: Math.max(...rs.map((x) => x.score)), raw: `${r.date.slice(5).replace("-", "/")} ${r.title} ${r.label}`, links: rs.map((x) => x.id) });
  }
  for (const p of ev?.policy ?? []) {
    if (!inWindow(p.date, prev, d)) continue;
    seen++;
    const tx = policyText(p); if (!tx) continue;
    const rs = react(tx.react); if (!rs.length) continue;
    out.push({ id: `policy:${p.bank}:${p.date}`, group: "event", kind: "event", phrase: tx.phrase, chip: tx.chip, sign: need, score: Math.max(...rs.map((x) => x.score)), raw: `${p.date.slice(5).replace("-", "/")} ${p.name ?? p.bank} ${p.decision_label ?? p.decision}`, links: rs.map((x) => x.id) });
  }
  // 뉴스: 이 스냅샷 cutoff 이전 · 직전 행 이후 발행분, 영향 큰 것만, 주제별 톤을 모아 이어지는 반응이 있을 때만
  const cut = doc?.cutoff ? Date.parse(doc.cutoff) : NaN;
  const from = prev ? Date.parse(`${prev}T22:30:00Z`) : cut - 3 * 864e5;
  const tone: Record<string, number> = {};
  for (const n of doc?.snapshot?.events ?? []) {
    const ts = n.timestamp ? Date.parse(n.timestamp) : NaN;
    if (!Number.isFinite(ts) || (Number.isFinite(cut) && ts > cut) || ts <= from) continue;
    if ((n.impact_score ?? 0) < 45 || n.event_type === "flow" || n.event_type === "other") continue;
    seen++;
    for (const [th, v] of Object.entries(n.theme_sentiment ?? {})) tone[th] = (tone[th] ?? 0) + v * ((n.impact_score ?? 50) / 100);
  }
  for (const [th, v] of Object.entries(tone)) {
    const link = NEWS_LINK[th]; if (!link || Math.abs(v) < 15) continue;
    const rs = react(v > 0 ? link.up : link.down); if (!rs.length) continue;
    const good = th === "geopolitical_risk" || th === "defense" ? v < 0 : v > 0;
    out.push({ id: `news:${th}`, group: `news:${link.ko}`, kind: "news", phrase: th === "geopolitical_risk" || th === "defense" ? "지정학 긴장 관련 뉴스" : `${link.ko} 관련 ${good ? "호재" : "악재"} 뉴스`, chip: `${link.ko} 뉴스`, sign: need, score: Math.max(...rs.map((x) => x.score)) * Math.min(1, Math.abs(v) / 30), raw: `${link.ko} 뉴스 톤 ${v >= 0 ? "+" : ""}${v.toFixed(0)}`, links: rs.map((x) => x.id) });
  }
  return { cands: out, seen };
}

/** 한 전환의 이유 — dayDoc 은 그 전환 날짜 행의 데이터를 담은 저장 스냅샷(없으면 null) */
export function explainTransition(t: CkRegimeTransition, prevRowDate: string | null, dayDoc: TransitionDayDoc | null, days?: TrendDay[]): TransitionWhy {
  const need = neededSign(t.from_regime, t.to_regime);
  const c = conseq(t.from_regime, t.to_regime);
  // 그날 스냅샷의 driver 가 있으면 그것, 없으면 전환 기록의 '주도 변수' 로(약하게)
  const drv = driverCands(dayDoc);
  const market = drv.length ? drv : varCands(t);
  const { cands: cats } = catalystCands(dayDoc, t.date, prevRowDate, market, need);
  const fc = factorCands(t);
  const factors = [...fc, ...trendCands(days, t.date).filter((x) => !fc.some((f) => f.group === x.group))];
  // 같은 저울 — 새 regime 쪽으로 미는 크기. 맞는 방향이 아닌 것은 맥락 후보로만 남는다
  const aligned = [...cats, ...market, ...factors].filter((x) => need !== 0 && Math.sign(x.sign) === need).map((x) => ({ ...x, score: x.score * (0.6 + 0.4 * Math.min(1, Math.abs(x.sign))) }));
  aligned.sort((a, b) => b.score - a.score);
  const picked: Cand[] = []; const groups = new Set<string>();
  for (const x of aligned) {
    if (picked.length >= 3) break;
    if (groups.has(x.group)) continue;
    // 이벤트 · 뉴스는 하나만 — 원인 머리로 쓴다
    if ((x.kind === "event" || x.kind === "news") && picked.some((p) => p.kind === "event" || p.kind === "news")) continue;
    picked.push(x); groups.add(x.group);
  }
  const head = picked.find((p) => p.kind === "event" || p.kind === "news") ?? null;
  // 머리 사건이 있으면 그 사건과 이어진 반응을 먼저 — 이어지지 않은 반응을 사건의 결과처럼 쓰지 않는다
  if (head?.links?.length) {
    const linked = aligned.filter((x) => head.links!.includes(x.id) && !picked.includes(x));
    for (const x of linked) { if (picked.length >= 3) { const i = picked.findIndex((p) => p !== head && !head.links!.includes(p.id)); if (i < 0) break; picked.splice(i, 1); } picked.push(x); }
  }
  const linkedR = head ? picked.filter((p) => p !== head && head.links?.includes(p.id)) : [];
  const otherR = picked.filter((p) => p !== head && !linkedR.includes(p));
  // 머리 사건이 없으면 반응 둘까지 문장에(세 번째는 근거 칩에만). '며칠째' 는 첫 반응에만
  const reacts = (head ? linkedR : picked).slice(0, 2).map((p, i) => (!head && i === 0 && p.persistent ? { ...p, phrase: `며칠째 이어진 ${p.phrase}` } : p));
  // 맥락(유가 등): 반대 방향이거나 sign 0 인데 그날 가장 크게 움직였으면 앞에 한 마디
  const ctxPool = market.filter((x) => x.context && !groups.has(x.group) && x.score >= 0.7).sort((a, b) => b.score - a.score);
  const ctx = !head && ctxPool.length && ctxPool[0]!.score >= (picked[0]?.score ?? 0) * 0.8 ? ctxPool[0]! : null;

  let why: string;
  const join = (xs: Cand[]) => (xs.length >= 2 ? `${wa(xs[0]!.phrase)} ${xs[1]!.phrase}` : xs[0]?.phrase ?? "");
  const verb = (xs: Cand[]) => (xs.length >= 2 ? "겹치면서" : "나타나면서");
  let basis: Basis;
  if (!picked.length) {
    why = `뚜렷하게 한쪽을 가리키는 신호는 적었지만, 판정 조건이 이어지면서 ${c.why}.`;
    basis = "internal";
  } else if (head) {
    const extra = otherR[0];
    why = reacts.length
      ? extra ? `${head.phrase} 이후 ${iga(join(reacts))} 나타났고, ${extra.phrase}까지 겹치면서 ${c.why}.` : `${head.phrase} 이후 ${iga(join(reacts))} ${verb(reacts)} ${c.why}.`
      : `${head.phrase} 이후 ${c.why}.`;
    basis = head.kind === "event" ? "event" : "news";
  } else if (ctx) {
    const ctxText = need < 0 ? ctx.context!.neg : ctx.context!.pos;
    why = `${euro(ctx.phrase)} ${ctxText}, ${iga(join(reacts))} ${verb(reacts)} ${c.why}.`;
    basis = "market";
  } else {
    const internal = picked.every((p) => p.kind === "factor");
    // 그날 스냅샷을 확인했는데 반응과 이어지는 이벤트 · 뉴스가 없을 때만 "이벤트보다는" 이라고 쓴다(스냅샷이 없으면 단정하지 않는다)
    const lead = dayDoc ? (internal ? "특별한 사건 없이 시장 내부에서 " : "뚜렷한 단일 이벤트보다는 ") : "";
    why = `${lead}${iga(join(reacts))} ${verb(reacts)} ${c.why}.`;
    basis = internal ? "internal" : "market";
  }
  // 근거가 하나도 안 잡히면 엔진이 적어 둔 주도 driver 이름을 그대로(숫자 없이) 근거로 둔다 — 지어내지 않는다
  const chips0 = [...(ctx ? [ctx] : []), ...picked].slice(0, 3).map((p) => p.chip);
  const chips = chips0.length ? chips0 : t.primary_driver ? [t.primary_driver] : [];
  const evidence = [...picked, ...(ctx ? [ctx] : [])].map((p) => p.raw);
  return { why, chips, meaning: c.meaning, basis, evidence, used: [...(ctx ? [ctx] : []), ...picked], dayDoc: dayDoc?.snapshot_date ?? null };
}

/** 날짜 D 행의 데이터를 담은 저장 스냅샷 날짜 = D 보다 늦은 첫 저장일(그 스냅샷 history 의 마지막 행이 D 여야 쓴다) */
export function dayDocDateFor(d: string, archiveDates: string[]): string | null {
  const later = archiveDates.filter((x) => x > d).sort();
  return later[0] ?? null;
}
export function dayDocMatches(doc: TransitionDayDoc | null, d: string): boolean {
  const days = doc?.cockpit?.history?.days ?? [];
  return days.length > 0 && days[days.length - 1]!.date === d;
}
