/**
 * STOCK RADAR · MARKET LEADERSHIP 제목 한 줄 (2026-11-03).
 *
 * 카드에 이미 있는 값(신호 · 이유 · 테마 · 시스템 축 · 연결된 Leadership)만으로 "왜 잡혔는가" 를 사람이 읽는 한 줄로 만든다.
 * 새 판단을 만들지 않는다 — 근거가 없으면 억지로 해석하지 않고 "추가 확인 필요" 로 적는다.
 * 우선순위: 연결된 Leadership 동인(실제 이벤트·매크로) → 펀더멘털 → 테마 → 상대강도 → 단순 가격 이상.
 * 저장본(archive)을 고치지 않고 모든 날짜 화면에 같은 규칙을 쓰려고 화면에서 만든다.
 */
import type { Cockpit, CkLeaderRow, CkRadarStock } from "../api/types";

export type RadarStatus = "POSITIVE" | "WATCH" | "MIXED" | "NEGATIVE";
export interface RadarHeadline { title: string; sub: string; status: RadarStatus }

/** 테마·세그먼트 태그 → 짧은 한글 */
const THEME_KO: Record<string, string> = {
  Semiconductor: "반도체", AI: "AI", software: "AI 소프트웨어", China: "중국", Consumer: "소비", dc_infra: "데이터센터 인프라", Energy: "에너지",
  Defense: "방산", foundry: "파운드리", "foundry/packaging": "파운드리·패키징", USD: "달러", Inflation: "인플레이션", power: "전력·냉각", Rates: "금리",
  "Geopolitical Risk": "지정학", Oil: "유가", hyperscalers: "클라우드", "Shareholder Return": "주주환원", "Korea Corporate Governance": "지배구조 개선",
  memory: "메모리·HBM", equipment: "반도체 장비", compute: "AI 연산",
};
/** 펀더멘털 축의 세그먼트 이름 → 짧은 한글 */
const SEG_KO: Record<string, string> = {
  "Memory / HBM": "메모리·HBM", "Power / Cooling": "전력·냉각", "AI Software / Applications": "AI 소프트웨어", "Data Center Infrastructure": "데이터센터 인프라",
  "Semiconductor Equipment": "반도체 장비", Foundry: "파운드리", "Hyperscalers / Cloud": "클라우드", "Foundry / Advanced Packaging": "파운드리·패키징",
};
/** Leadership 라벨 → 종목군 이름 */
const LEADER_KO: Record<string, string> = {
  Utilities: "유틸리티", Financials: "금융주", Airlines: "항공주", "Consumer Discretionary": "경기소비재", "Geopolitical Risk": "지정학 수혜주", Defense: "방산주",
  Energy: "에너지주", Oil: "원유 관련주", China: "중국 관련주", Consumer: "소비주", Semiconductor: "반도체주", AI: "AI주", "Information Technology": "기술주",
};
/** 종목 태그 → 같은 Leadership 라벨(종목이 key_stocks 에 없어도 같은 테마면 잇는다) */
const TAG_TO_LEADER: Record<string, string[]> = {
  Defense: ["Defense"], Consumer: ["Consumer", "Consumer Discretionary"], Energy: ["Energy"], Oil: ["Oil"], China: ["China"], Semiconductor: ["Semiconductor"],
  "Geopolitical Risk": ["Geopolitical Risk", "Defense"], AI: ["AI"],
};

const UP = new Set(["↑", "↑↑"]); const DOWN = new Set(["↓", "↓↓"]);
const num = (s: string | undefined) => (s === undefined ? null : Number(s.replace("−", "-")));
const fmt = (v: number, d = 1) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;

function axis(r: CkRadarStock, key: string) { return r.system_axes.find((a) => a.key === key); }

function leaderOf(r: CkRadarStock, c: Cockpit): CkLeaderRow | undefined {
  const rows = [...(c.leadership?.leaders ?? []), ...(c.leadership?.laggards ?? [])];
  const direct = rows.find((l) => l.detail?.key_stocks.some((s) => s.id === r.id));
  if (direct) return direct;
  const labels = TAG_TO_LEADER[r.tag] ?? [];
  return rows.find((l) => labels.includes(l.label));
}

/** 동인 → 문장 조각. Relative strength 처럼 원인이 아닌 것은 null */
function driverPhrase(driver: string | undefined): string | null {
  if (!driver) return null;
  if (/^(Oil|Brent|WTI)\s*↓/.test(driver)) return "유가 하락";
  if (/^(Oil|Brent|WTI)\s*↑/.test(driver)) return "유가 상승";
  if (/geopolitical/i.test(driver)) return "지정학 긴장";
  if (/AI Infrastructure/i.test(driver)) return "AI 인프라 투자";
  return null;
}

/** "필라델피아 반도체 (SOX) -3.1σ 영향" → { name: "SOX", z: -3.1 } */
function driverInWhy(why: string): { name: string; z: number } | null {
  const m = why.match(/\(([A-Z0-9 ]+)\)\s*([-+−]?\d+(?:\.\d+)?)σ 영향/) ?? why.match(/([^·(]+?)\s+([-+−]?\d+(?:\.\d+)?)σ 영향/);
  if (!m) return null;
  return { name: m[1]!.trim(), z: num(m[2]) ?? 0 };
}

function relWeek(r: CkRadarStock): number | null {
  const m = (axis(r, "market")?.detail ?? "").match(/상대 ([-+−]?\d+(?:\.\d+)?)%p/) ?? r.why.match(/상대 ([-+−]?\d+(?:\.\d+)?)%p/);
  return m ? num(m[1]) : null;
}

function relSigma(r: CkRadarStock): number | null {
  const m = r.why.match(/시장 대비 ([-+−]?\d+(?:\.\d+)?)σ/) ?? (axis(r, "relative")?.detail ?? "").match(/([-+−]?\d+(?:\.\d+)?)σ/);
  return m ? num(m[1]) : null;
}

function dayZ(r: CkRadarStock): number | null {
  const m = (axis(r, "market")?.detail ?? "").match(/하루 z ([-+−]?\d+(?:\.\d+)?)σ/);
  return m ? num(m[1]) : null;
}

function segmentOf(r: CkRadarStock): string | null {
  const m = (axis(r, "fundamental")?.detail ?? "").match(/세그먼트 펀더멘털 (.+?) (?:[-+−]\d|–|\?)/);
  if (m) return SEG_KO[m[1]!.trim()] ?? m[1]!.trim();
  // AI radar 의 이유("데이터센터 인프라 1주 +12.2% · …")에 세그먼트 이름이 먼저 온다
  const w = r.why.match(/^([^·]+?) 1주 [-+−]/);
  if (w) return w[1]!.trim();
  return THEME_KO[r.tag] ?? null;
}

function unusualKind(r: CkRadarStock): string | null {
  const m = r.why.match(/이상 거동 ([A-Z_]+)/);
  return m ? m[1]! : r.signals.includes("UNUSUAL") ? "UNUSUAL" : null;
}

function direction(r: CkRadarStock): number {
  if (r.change_1d !== null) return Math.sign(r.change_1d);
  const z = dayZ(r);
  if (z !== null) return Math.sign(z);
  const a = axis(r, "market")?.arrow ?? "";
  return UP.has(a) ? 1 : DOWN.has(a) ? -1 : 0;
}

export function radarHeadline(r: CkRadarStock, c: Cockpit): RadarHeadline {
  const dir = direction(r);
  const fund = axis(r, "fundamental")?.arrow ?? "?";
  const seg = segmentOf(r);
  const rel = relWeek(r);
  const z = dayZ(r);
  const drv = driverInWhy(r.why);
  const un = unusualKind(r);
  const themeOk = /테마 확인/.test(r.why);
  const sig = new Set(r.signals);
  const lead = leaderOf(r, c);
  const leadUp = lead ? UP.has(lead.arrow) : false;
  const breadth = lead?.breadth ?? null;
  // 하루 움직임 — |z| ≥ 2 일 때만 급등·급락이라 부른다
  const spikeSub = z !== null && Math.abs(z) >= 2 ? `하루 ${fmt(z)}σ ${z >= 0 ? "급등" : "급락"}` : r.change_1d !== null ? `하루 ${fmt(r.change_1d)}%` : "";
  const rs = relSigma(r);
  const relSub = rel !== null ? `시장 대비 ${fmt(rel)}%p (1주)` : rs !== null ? `시장 대비 ${fmt(rs)}σ` : "";

  const grp = lead ? (LEADER_KO[lead.label] ?? lead.label) : "";
  const leadWhy = lead ? driverPhrase(lead.detail?.driver) : null;
  const leadSub = breadth !== null && breadth >= 70 ? `${grp} 전반 상승 · breadth ${breadth.toFixed(0)}%` : rel !== null ? `시장 대비 ${fmt(rel)}%p (1주)` : spikeSub;
  // 1) 연결된 Leadership 의 실제 동인(유가 · 지정학 …)이 있고 같은 방향이면 그것이 이유다
  if (lead && leadUp && dir >= 0 && leadWhy) {
    const title = leadWhy === "유가 하락" ? `유가 하락 수혜 + ${grp} 동반 강세` : `${leadWhy} 속 ${grp} 동반 강세`;
    return { title, sub: leadSub, status: "POSITIVE" };
  }
  // 2) 펀더멘털이 확인된 종목
  if (UP.has(fund) && seg) {
    if (dir < 0) return { title: `${seg} 개선에도 주가 조정`, sub: drv && drv.z < 0 ? `${drv.name} ${fmt(drv.z)}σ 약세 영향` : relSub || "가격이 펀더멘털을 아직 따라가지 않음", status: "MIXED" };
    if (rel !== null && rel > 0) {
      const sub = drv && drv.z < 0 ? `${drv.name} 약세에도 시장 대비 견조` : `시장 대비 ${fmt(rel)}%p (1주)`;
      return { title: `${seg} 개선 속 상대강도 유지`, sub, status: "POSITIVE" };
    }
    return { title: `${seg} 개선 · 주가 확인 대기`, sub: drv ? `${drv.name} ${fmt(drv.z)}σ 영향권` : "", status: "WATCH" };
  }
  if (DOWN.has(fund) && seg) return { title: `${seg} 둔화 · 주가 약세`, sub: relSub, status: "NEGATIVE" };
  // 3) 테마가 가격으로 확인된 종목 — 같은 테마의 Leadership 이 강하면 그 종목군 이름으로
  if (lead && leadUp && dir >= 0) return { title: `${grp} 강세 동반`, sub: un ? (spikeSub || leadSub) : leadSub, status: "POSITIVE" };
  if (themeOk && THEME_KO[r.tag]) {
    const t = THEME_KO[r.tag]!;
    if (dir >= 0) return { title: `${t} 테마 강세 동반`, sub: un ? spikeSub || relSub : "테마 종목 동반 상승", status: "POSITIVE" };
    return { title: `${t} 테마 약세 동반`, sub: spikeSub || relSub, status: "NEGATIVE" };
  }
  // 4) AI 세그먼트 상대강도(펀더멘털 미확인)
  if ((sig.has("IMPROVING") || sig.has("STRONGEST")) && seg) {
    const relTxt = rel !== null ? `시장 대비 ${fmt(rel)}%p (1주)` : "";
    const sub = [relTxt, fund === "?" ? "펀더멘털 확인 전" : ""].filter(Boolean).join(" · ");
    if (dir < 0) return { title: `${seg} 1주 강세 속 하루 조정`, sub, status: "MIXED" };
    return { title: `${seg} 상대강도 개선`, sub, status: fund === "?" ? "WATCH" : "POSITIVE" };
  }
  if (sig.has("NARRATIVE_AHEAD")) return { title: "뉴스 관심 대비 주가 부진", sub: seg ? `${seg} · 가격 확인 대기` : "가격 확인 대기", status: "WATCH" };
  if (sig.has("MACRO_PRESSURE") && !sig.has("NEWS")) return { title: "금리·위험회피 부담 속 약세", sub: seg ?? "", status: "NEGATIVE" };
  // 5) 시장 대비 상대강도만
  if (sig.has("REL") && !un) {
    const up = rs !== null ? rs > 0 : dir >= 0;
    return { title: up ? "시장 대비 강세 지속" : "시장 대비 약세 지속", sub: relSub, status: up ? "POSITIVE" : "NEGATIVE" };
  }
  // 6) 단순 가격 이상 — 원인을 만들지 않는다
  if (un) {
    const noFund = "확인된 펀더멘털 근거 부족";
    if (un === "NEWS_DRIVEN_MOVE") return { title: "뉴스성 움직임 · 원인 확인 중", sub: spikeSub || noFund, status: "WATCH" };
    if (un === "RELATIVE_MOVE") return { title: "시장과 다른 움직임 · 확인 필요", sub: spikeSub || noFund, status: "WATCH" };
    if (un === "UNEXPLAINED_ACTIVITY") return { title: "설명되지 않은 움직임 · 원인 확인 중", sub: noFund, status: "WATCH" };
    return { title: `${dir < 0 ? "급락" : "급등"} 포착 · 추가 확인 필요`, sub: noFund, status: "WATCH" };
  }
  // 7) 뉴스 · 실적 · 수급 · 대체데이터만
  if (sig.has("EPS")) return { title: "실적 추정 변화 반영", sub: "", status: "WATCH" };
  if (sig.has("NEWS")) return { title: "뉴스·이벤트 반영 움직임", sub: drv ? `${drv.name} ${fmt(drv.z)}σ 영향권` : "", status: "WATCH" };
  if (sig.has("FLOW")) return { title: "수급 전환 포착", sub: "", status: "WATCH" };
  if (sig.has("ALT")) return { title: "대체데이터 신호 포착", sub: "", status: "WATCH" };
  return { title: r.why.split(" · ")[0] || r.name, sub: "", status: "WATCH" };
}

/** Leadership 행 아래 한 줄 — 무엇 때문에 강(약)한가 */
export function leaderTitle(r: CkLeaderRow): string {
  const grp = LEADER_KO[r.label] ?? r.label;
  const up = UP.has(r.arrow) || ((r.z_1d ?? 0) > 0 && !DOWN.has(r.arrow));
  const why = driverPhrase(r.detail?.driver);
  if (up) {
    if (why === "유가 하락") return "유가 하락 수혜로 상대강도 확대";
    if (why === "지정학 긴장") return r.label === "Geopolitical Risk" ? "지정학 긴장 수혜주 동반 강세" : `지정학 리스크 확대로 ${grp} 강세`;
    if (r.label === "Geopolitical Risk") return "지정학 긴장 수혜주 동반 강세";
    if (why) return `${why} 수혜로 ${grp} 강세`;
    return r.detail?.quality === "BROADENING" || (r.breadth ?? 0) >= 70 ? `${grp} 시장 대비 강세 · 종목 전반 확산` : `${grp} 시장 대비 강세`;
  }
  if (why === "유가 하락") return `유가 하락으로 ${grp} 약세`;
  if (why) return `${why} 부담 속 ${grp} 약세`;
  return `${grp} 시장 대비 약세`;
}
