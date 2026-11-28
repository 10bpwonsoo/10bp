/**
 * 반도체 사이클 탭 상단의 설명 레이어 (2026-11-24) — 국면 · 지표 · 점수가 무엇을 뜻하는지의 고정 설명.
 *
 * 숫자와 판정은 서버가 만든 것을 그대로 쓴다. 여기에는 '그 값이 무엇을 재는가' 만 있다(엔진 engines/semiconductor_cycle.py 의 계산식을 옮긴 것).
 * 고정 설명이라 옛 저장본에서도 보인다. 그날의 해설(CYCLE READ · 지지/제약 메모)은 서버의 cycle_read(LLM)가 따로 준다 — 없으면 비운다.
 */
import type { SemiChip, SemiComponent, SemiconductorCycle } from "../api/semiconductor";

/** 국면 이름의 뜻 — 국면은 composite 구간으로 정한다(아래 REGIME_SCALE). 방향(올라온 것인지 내려온 것인지)은 이력에서 따로 보인다. */
export const REGIME_MEANING: Record<string, string> = {
  STRONG_UPSWING: "가격·수요·주가 증거가 함께 강하게 개선되는 상승 사이클",
  UPSWING: "주요 업황 증거가 상승 방향으로 정렬된 상태",
  EARLY_RECOVERY: "개선 신호가 조금 우세한 초기 회복 구간 — 가격·주가의 전면적 회복은 아직 확인되지 않음",
  NEUTRAL: "상승·하락 신호가 섞여 방향이 뚜렷하지 않은 상태",
  DOWNTURN: "가격·수요·주가 증거가 약해지는 하강 사이클",
  DEEP_DOWNTURN: "가격과 수요 전반에서 강한 하락 압력이 확인되는 상태",
  INSUFFICIENT_DATA: "증거가 모자라 국면을 정하지 않은 상태",
};

/** composite 구간 — config/semiconductor_cycle.yaml 의 regime.states 와 같아야 한다(tests/test_semi_cycle_read.py 가 대조한다). */
export const REGIME_SCALE = [
  { key: "STRONG_UPSWING", min: 55, label: "STRONG UPSWING" },
  { key: "UPSWING", min: 25, label: "UPSWING" },
  { key: "EARLY_RECOVERY", min: 8, label: "EARLY RECOVERY" },
  { key: "NEUTRAL", min: -8, label: "NEUTRAL" },
  { key: "DOWNTURN", min: -40, label: "DOWNTURN" },
];
export const SCALE_FLOOR_LABEL = "DEEP DOWNTURN";

export function compositeRead(v: number | null): string {
  if (v === null) return "증거 점수가 없어 계산하지 않음";
  if (v >= 55) return "상승 방향 신호가 강하게 우세";
  if (v >= 25) return "상승 방향이 뚜렷하게 우세";
  if (v >= 8) return "상승 방향이 우세하지만 강도는 아직 제한적";
  if (v > -8) return "상승·하락 신호가 비슷해 방향이 뚜렷하지 않음";
  if (v > -40) return "하락 방향이 우세";
  return "하락 방향 신호가 강하게 우세";
}

export const METRIC_MEANING = {
  composite: "전체 증거 점수의 가중 평균",
  confidence: "현재 Regime 판단의 확신도 — 증거가 한 방향으로 모일수록 높다",
  evidence: "판정에 쓰는 증거 중 실제 확보된 비율(가중치 기준)",
};

/** 증거 점수(Factor Score)가 무엇을 재는가 — 한 줄. */
export const FACTOR_MEANING: Record<string, string> = {
  memory_pricing: "표준 등급 현물 가격의 1주·1개월·3개월 변화율을 합친 모멘텀",
  spot_premium: "현물이 계약가보다 얼마나 높은가(프리미엄 수준) — 단기 수급이 빡빡할수록 높다",
  contract: "최근 공개 계약가의 직전 대비 변화 — 오래된 값(STALE)은 절반만 반영",
  premium_breadth: "표준 등급 제품 중 가격 모멘텀이 플러스인 제품의 비중(절반이면 0)",
  hbm: "HBM 계약가 앵커(비정기·추정)의 직전 대비 변화",
  export: "한국 반도체 수출 나우캐스트의 전년 대비 증가율 ± 지난달 대비 가속·둔화",
  eps_revision: "실적 컨센서스 변화 — 공급원이 없어 NO DATA",
  equity: "메모리 3사(SK hynix·Samsung·Micron) 1개월 주가 수익률 평균 — 주가의 방향과 크기",
  supply_news: "감산·재고·가격·증설 기사 감성의 평균",
};

export const SIDE_MIN = 10; // |점수| 가 이 이상이면 지지 · 제약으로 센다(서버 tone 기준 · ai/semi_cycle_read.py SIDE_MIN 과 같다)
export type Side = "support" | "constraint" | "neutral" | "no_data";
export const sideOf = (score: number | null): Side => (score === null ? "no_data" : score >= SIDE_MIN ? "support" : score <= -SIDE_MIN ? "constraint" : "neutral");

/** 지지 · 제약 묶음의 제목 — 국면에 맞춘 이름. 묶는 기준은 점수의 부호뿐이다. */
export function groupTitles(state: string): [string, string] {
  if (state === "EARLY_RECOVERY") return ["RECOVERY SUPPORT", "RECOVERY CONSTRAINT"];
  if (state === "UPSWING" || state === "STRONG_UPSWING") return ["UPSWING SUPPORT", "UPSWING CONSTRAINT"];
  if (state === "DOWNTURN" || state === "DEEP_DOWNTURN") return ["OFFSETTING SUPPORT", "DOWNTURN PRESSURE"];
  return ["UPSIDE SIGNALS", "DOWNSIDE SIGNALS"];
}

const strength = (s: number) => (s >= 50 ? "STRONG" : s >= SIDE_MIN ? "POSITIVE" : s <= -50 ? "WEAK" : s <= -SIDE_MIN ? "SOFT" : "FLAT");

/** 묶음 안에서 보일 상태 단어 — 같은 증거의 상태 칩이 있으면 그 단어, 없으면 점수 크기에서(새 계산이 아니라 표시). */
export function factorWord(x: SemiComponent, c: SemiconductorCycle): string {
  if (x.score === null) return "NO DATA";
  const chip = (k: string) => c.regime.chips.find((ch) => ch.key === k)?.value;
  if (x.key === "memory_pricing" || x.key === "contract" || x.key === "hbm") return chip(x.key) ?? strength(x.score);
  if (x.key === "premium_breadth") return c.breadth?.state && c.breadth.state !== "NO DATA" ? c.breadth.state : strength(x.score);
  return strength(x.score);
}

/** composite 에서 그 증거가 차지하는 몫 — 점수 × 가중치 ÷ (확보된 가중치 합). 전부 더하면 composite 다. */
export function contribution(x: SemiComponent, all: SemiComponent[]): number | null {
  if (x.score === null) return null;
  const w = all.filter((y) => y.score !== null).reduce((a, y) => a + y.weight, 0);
  return w > 0 ? (x.score * x.weight) / w : null;
}

/** 지금 그 점수가 나온 근거 — 서버가 준 값만 한 줄로. */
export function factorBasis(x: SemiComponent, c: SemiconductorCycle): string {
  const pct = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}%`);
  switch (x.key) {
    case "memory_pricing":
      return c.memory_prices.filter((p) => p.available && p.tier === "main").map((p) => `${p.label} ${p.momentum_state ?? "NO DATA"}`).join(" · ");
    case "spot_premium":
      return c.spot_premium.filter((p) => p.available).map((p) => `${p.spot_label} ${pct(p.current)}${p.proxy ? "(proxy)" : ""} ${p.direction ?? ""}`.trim()).join(" · ") || "비교 가능한 계약가 없음";
    case "contract": {
      const r = c.contract.rows[0];
      return r ? `${c.contract.rows.map((y) => `${y.label} ${pct(y.change_pct, 1)}`).join(" · ")} · 기준 ${r.period.slice(0, 7)}${c.contract.stale ? " · STALE(절반 반영)" : ""}` : "계약가 없음";
    }
    case "premium_breadth":
      return `모멘텀 플러스 제품 ${c.breadth.positive_momentum[0]}/${c.breadth.positive_momentum[1]} · ${c.breadth.state}`;
    case "hbm":
      return c.hbm_supply.anchors.filter((a) => a.available).map((a) => `${a.label.replace(" ($/GB)", "")} ${pct(a.change_pct ?? null)}(${a.date ?? "–"})`).join(" · ") || "앵커 없음";
    case "export": {
      const e = c.export_nowcast;
      return e.available ? `${e.latest_scope_label ?? ""} ${pct(e.latest_yoy)} YoY · 나우캐스트 ${pct(e.nowcast?.yoy_mid)} · 지난달 ${pct(e.prev_month_yoy)} · ${e.momentum ?? ""}` : "발표 없음";
    }
    case "eps_revision":
      return "컨센서스 공급원 없음 — Composite 분모에서 뺀다(0 으로 넣지 않음)";
    case "equity":
      return c.equity_confirmation.stocks.map((s) => `${s.label} ${pct(s.ret_1m, 1)}`).join(" · ") + " (1개월)";
    case "supply_news":
      return x.score === null ? "해당 기사 없음" : "감산·재고·가격·증설로 분류된 그날 기사의 감성";
    default:
      return "";
  }
}

const memDir = (c: SemiconductorCycle): "up" | "down" | "flat" | null => {
  const s = c.regime.components.find((x) => x.key === "memory_pricing")?.score;
  return s === null || s === undefined ? null : s > 0 ? "up" : s < 0 ? "down" : "flat";
};

/** 상태 칩 한 줄 설명 — 그 칩이 실제로 재는 것(엔진 정의). */
export function chipMeaning(ch: SemiChip, c: SemiconductorCycle): string {
  const v = ch.value;
  if (v.startsWith("NO DATA")) return ch.key === "eps" ? "컨센서스 공급원이 없어 계산에서 뺀다" : "관측값이 없어 계산에서 뺀다(0 으로 넣지 않음)";
  switch (ch.key) {
    case "memory_pricing":
      return ({ STRONG: "범용 메모리 현물 가격이 뚜렷하게 상승", FIRM: "범용 메모리 현물 가격이 완만하게 상승", FLAT: "범용 메모리 현물 가격이 거의 제자리",
        SOFT: "범용 메모리 현물 가격 모멘텀 약화", WEAK: "범용 메모리 현물 가격이 뚜렷하게 하락" } as Record<string, string>)[v] ?? "";
    case "spot_premium": {
      const s = c.regime.components.find((x) => x.key === "spot_premium")?.score ?? null;
      const level = s === null ? "" : s >= SIDE_MIN ? "현물이 계약가보다 높은 상태에서 " : s <= -SIDE_MIN ? "현물이 계약가보다 낮은 상태에서 " : "";
      return ({ EXPANDING: `${level}격차가 벌어지는 중`, STABLE: `${level}격차가 유지되는 중`, COMPRESSING: `${level}격차가 좁혀지는 중`, UNKNOWN: "프리미엄 방향을 정할 이력이 부족" } as Record<string, string>)[v] ?? "";
    }
    case "contract": {
      const base = v.startsWith("RISING") ? "계약가는 상승" : v.startsWith("FALLING") ? "계약가는 하락" : "계약가는 제자리";
      return v.includes("STALE") ? `${base}했지만 공개된 지 오래돼 점수는 절반만 반영` : `${base} — 최근 공개분 기준`;
    }
    case "hbm":
      return ({ TIGHT: "AI 메모리(HBM) 계약가가 모두 뚜렷이 올라 공급이 타이트", MIXED: "HBM 계약가 앵커가 엇갈림", SOFT: "HBM 계약가 상승이 약함" } as Record<string, string>)[v] ?? "";
    case "export": {
      const y = c.export_nowcast.nowcast?.yoy_mid ?? c.export_nowcast.latest_yoy ?? null;
      const grow = y !== null && y !== undefined && y > 0;
      return ({ ACCELERATING: grow ? "수출이 늘고 증가 속도도 빨라지는 중" : "수출 증가율이 지난달보다 높아짐",
        DECELERATING: grow ? "수출은 증가 중이지만 증가 속도는 둔화" : "수출 증가율이 지난달보다 낮아짐",
        STEADY: "수출 증가율이 지난달과 비슷", "N/A": "확정치 기준 — 가속·둔화는 판정하지 않음" } as Record<string, string>)[v] ?? "";
    }
    case "equity": {
      const d = memDir(c);
      const both = d === "down" ? " — 지금은 둘 다 하락" : d === "up" ? " — 지금은 둘 다 상승" : "";
      if (v === "BROAD CONFIRMATION") return `메모리 3사 주가가 현물 가격과 같은 방향${both}`;
      if (v === "DIVERGENCE") return `주가가 현물 가격과 반대 방향${d === "down" ? " — 현물은 하락, 주가는 상승" : d === "up" ? " — 현물은 상승, 주가는 하락" : ""}`;
      return "주가와 현물 가격의 방향이 종목마다 엇갈림";
    }
    case "turning":
      return ({ "EARLY SOFTENING": "현물 가격 쪽 선행 신호 둘 이상이 약해지는 방향", "EARLY TIGHTENING": "현물 가격 쪽 선행 신호 둘 이상이 강해지는 방향",
        NONE: "방향이 바뀌는 신호가 모이지 않음" } as Record<string, string>)[v] ?? "";
    default:
      return "";
  }
}

/** Equity Confirm 이 '확인' 한 방향이 하락이면 좋은 신호가 아니다 — 색을 그 방향에 맞춘다. */
export function chipTone(ch: SemiChip, c: SemiconductorCycle): "down" | null {
  return ch.key === "equity" && ch.value === "BROAD CONFIRMATION" && memDir(c) === "down" ? "down" : null;
}

export const EQUITY_NOTE = "Equity Confirm 은 주가가 현물 가격과 같은 방향인지(방향 일치), Equity 점수는 주가 자체의 방향과 크기입니다 — 현물과 주가가 함께 내리면 확인은 BROAD, 점수는 마이너스입니다.";
export const TURNING_NOTE = "현재 Regime 이 아니라 Regime 이 바뀔 조짐을 보는 지표입니다.";
export const SCORE_LEGEND = "점수가 높을수록 반도체 사이클 상승을, 낮을수록 하락을 지지합니다(−100 강한 악화 · 0 중립 · +100 강한 개선). 좋고 나쁨의 절대 평가가 아니라 방향 기여입니다.";
export const WEIGHT_LEGEND = "× 숫자 = Composite 에 반영되는 가중치. NO DATA 는 값이 없어 계산에서 뺀 증거입니다(0 으로 넣지 않음).";
