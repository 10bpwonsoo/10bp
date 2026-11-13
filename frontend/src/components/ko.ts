/**
 * 영어 상태값 옆의 짧은 한글 의미 — 실시간 2 전용 표현 층. 영어는 시스템의 전문 상태값이고 한글은 지금 그 상태가 뜻하는 것.
 * 영어를 치환하지 않는다: 항상 `ENGLISH STATUS` 가 먼저, 한글이 보조.
 */
export const STATUS_KO: Record<string, string> = {
  // CROSS-ASSET
  CONFIRM: "현재 시장 판단과 같은 방향", HEADWIND: "현재 시장에 추가 부담", DIVERGE: "현재 판단과 다른 움직임", FLAT: "움직임이 작아 판단 없음", NEUTRAL: "이 판정엔 기대 방향 없음", MISSING: "데이터 없음",
  // PATH / STOCK
  CONFIRMED: "예상한 전파가 실제 시장에서도 확인됨", PARTIAL: "일부 시장에서만 확인됨", UNCONFIRMED: "아직 확인되지 않음", CONTRADICTED: "예상과 반대로 움직임 — 다른 driver 가 더 강하게 작용", "DATA MISSING": "판단할 데이터 없음", MIXED: "서로 다른 신호가 혼재",
  // WHAT MATTERS NEXT
  WATCH: "관찰 중", CONFIRMING: "현재 시나리오 확인 강화", REVERSING: "기존 흐름에서 반전 중",
  // TIERS
  DIRECT: "1차 영향", SECONDARY: "2차 영향", TERTIARY: "간접 영향",
};
/** 모바일용 짧은 꼬리 — `CONFIRM · 판단 지지` */
export const STATUS_KO_SHORT: Record<string, string> = {
  CONFIRM: "판단 지지", HEADWIND: "추가 부담", DIVERGE: "흐름 불일치", FLAT: "움직임 작음", NEUTRAL: "기대 없음", MISSING: "데이터 없음",
  CONFIRMED: "확인됨", PARTIAL: "일부 확인", UNCONFIRMED: "미확인", CONTRADICTED: "반대 움직임", "DATA MISSING": "데이터 없음", MIXED: "혼재",
  WATCH: "관찰 중", CONFIRMING: "확인 강화", REVERSING: "반전 중",
};
export const TIER_TIP: Record<string, string> = {
  DIRECT: "해당 driver 에 직접적인 민감도가 높은 종목", SECONDARY: "산업이나 사업구조를 통해 영향을 받는 종목", TERTIARY: "여러 요인 중 하나로 영향을 받는 종목",
};
/** 전문 용어 툴팁 — 용어는 그대로 두고 처음 등장할 때 뜻을 붙인다 */
export const GLOSSARY: Record<string, string> = {
  "Real Yield": "물가 영향을 제외한 실질금리", Duration: "금리 상승에 민감한 장기 성장자산 부담", "Credit Spread": "기업 신용위험에 대한 추가 금리", "Relative Strength": "시장 대비 상대적인 가격 강도",
  Breadth: "상승/하락이 얼마나 많은 종목으로 확산됐는지", Divergence: "보통 같이 움직이던 두 신호가 갈리는 것", "Discount Rate": "미래 현금흐름을 현재가치로 바꾸는 금리", Transmission: "한 변수의 변화가 다른 자산·산업·종목으로 옮겨가는 경로",
  "HY OAS": "하이일드 회사채와 국채의 금리 차 — 신용 스트레스 지표", MOVE: "미 국채 변동성 지수", VIX: "S&P 500 옵션 내재 변동성 — 시장 불안 지표", Breakeven: "명목금리 − 실질금리 = 시장의 기대인플레이션",
};
/** 문장 안 용어에 title 툴팁을 붙일 때 쓰는 매칭 목록(긴 것부터) */
export const GLOSSARY_TERMS = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length);
export function glossaryFor(text: string): string | undefined {
  const hit = GLOSSARY_TERMS.find((t) => text.toLowerCase().includes(t.toLowerCase()));
  return hit ? `${hit}: ${GLOSSARY[hit]}` : undefined;
}
/** 색은 수익률의 좋고 나쁨이 아니라 시나리오와 실제 시장의 일치 정도 */
export const MATCH_COLOR: Record<string, string> = {
  CONFIRM: "var(--ok)", CONFIRMED: "var(--ok)", CONFIRMING: "var(--ok)",
  PARTIAL: "var(--warn)", WATCH: "var(--warn)", HEADWIND: "var(--warn)", MIXED: "var(--warn)",
  DIVERGE: "var(--down)", CONTRADICTED: "var(--down)", REVERSING: "var(--down)",
  UNCONFIRMED: "var(--muted)", FLAT: "var(--muted)", NEUTRAL: "var(--faint)", MISSING: "var(--faint)", "DATA MISSING": "var(--faint)", "NO DATA": "var(--faint)",
};
export const COLOR_LEGEND = "색상은 수익률의 좋고 나쁨이 아니라 현재 시나리오와 실제 시장의 일치 여부를 뜻합니다.";
