"""
2026-10-06 07:40 UTC(16:40 KST 장 마감 후) 기준 8차 수기 태깅. 한국은 10/6 종가, 미국은 10/5 종가(지수·VIX·MOVE·섹터 ETF),
FRED 금리 계열은 10/2 가 마지막(DGS 계열 지연), BE10Y·BE5Y 는 10/5. 항셍·니케이는 Yahoo 가 계열을 주지 않아 결측.

RSS 80건 중 테마와 관련 있는 것만 읽고 태깅했다. 해외 기사는 이 세션의 웹검색으로 제목·URL·날짜가 확인된 것만 같은 규약으로 적었다
(본문을 읽지 못한 기사는 넣지 않았다). extractor="manual". Anthropic API 호출 아님.

부호 규약: 테마가 강해지는 방향이 +. oil/inflation/rates/usd 는 directional 이라 유가·물가·금리·달러 '상승' 이 direction=up 이고,
sentiment 는 시장 호재/악재다. geopolitical_risk 는 risk polarity — 긴장 고조가 +.

맥락(10/5 미국 → 10/6 한국 마감): 나스닥 27,477.31(+1.05%) 사상 최고, S&P 7,773.95(+0.66%), 다우 51,267.90(+0.18%). 엔비디아 사상 최고가
(1,500억달러 자사주 매입·AI 수요 낙관), 테슬라 +2%, 메타·MS 상승. 10년물 5.311%(+3bp, 2002년 이후 최고권), 30년 5.664%. 금요일(10/2)
고용 둔화로 10월 인상 확률 ~20%(1주 전 ~70%). 브렌트는 10/5 -2%(중동 수출 회복·G7 1억 배럴 방출) 뒤 10/6 아시아 99~101달러.
AMD 리사 수, 타이베이에서 "2027년 공급 대폭 확대"(TSMC·폭스콘·삼성·하이닉스 면담). TrendForce: 2027년 HBM ASP +121%.
국내 10/6: 코스피 6,941.38(-0.89%) 7,000 아래, 코스닥 919.92(+2.98%) 910 탈환. 외국인 코스피 1조7,689억 순매도, 개인 7,256억 순매수.
SK하이닉스 -3.69%, 삼성전자 -1.45% / 삼성전기 +5.95%, 주성엔지니어링 +17.5%, LG에너지솔루션 +5.1%, 에코프로비엠 +11.4%. LG전자 5GW
AI DC 칠러 장기공급계약에 +5.8%. 원·달러 1,341.5(환율 급락 → 수출기업 순이익 쇼크 경고).
"""

def T(themes, ts, td, sentiment, impact, novelty, horizon, event_type, reason):
    return dict(themes=themes, theme_sentiment=ts, theme_direction=td, sentiment=sentiment,
                impact=impact, novelty=novelty, horizon=horizon, event_type=event_type, reason=reason)

TAGS = {
    # ── 미국 세션 · 금리 vs AI ──
    "c893da1b646718d6": T(["rates", "ai", "semiconductor"], {"rates": 30, "ai": 30, "semiconductor": 20}, {"rates": "up", "ai": "up", "semiconductor": "up"}, 25, 65, 50, "short", "macro",
        "24년 만의 美국채금리(10년 5.31%, 30년 5.664%)에도 나스닥 27,477(+1.05%)·엔비디아 사상 최고가 — AI 모멘텀과 견조한 성장이 금리를 눌렀다."),
    "32d060485bc70136": T(["rates", "ai"], {"rates": 30, "ai": 25}, {"rates": "up", "ai": "up"}, 15, 55, 40, "short", "macro",
        "기록적 금리 상승에도 나스닥·엔비디아 신고가 — '더 오르겠지만 변동성'. 고용·CPI(10/14)·3분기 실적이 다음 고비(김현석의 월스트리트나우)."),
    "4f9108e63f6f0aba": T(["rates", "ai", "oil"], {"rates": 10, "ai": 15, "oil": -10}, {"rates": "up", "ai": "up", "oil": "down"}, 15, 35, 35, "short", "macro",
        "美 선물 소폭 상승 — 9월 고용 둔화로 10월 인상 확률 ~20%(1주 전 70%). 10년물은 5.31% 로 2002년 고점권. 브렌트는 월요일 -2% 뒤 아시아장 약보합. 수요일 FOMC 의사록."),
    "4656d13045e13753": T(["ai", "energy"], {"ai": 20, "energy": 10}, {"ai": "up", "energy": "up"}, 15, 30, 25, "short", "macro",
        "엔비디아 사상 최고가 — 아침 7가지. 밴스 '알래스카 LNG 협의해야'."),
    "39f6f42373a35e1b": T(["ai", "energy", "oil"], {"ai": 15, "energy": 15, "oil": 5}, {"ai": "up", "energy": "up", "oil": "up"}, 20, 35, 35, "medium", "other",
        "S&P500 3분기 이익 전망 고공행진 — 에너지·IT 가 주도. 고유가와 AI 투자가 동시에 이익 전망을 밀어올린다."),
    "b23fe916efd7e66e": T(["ai", "geopolitical_risk"], {"ai": 10, "geopolitical_risk": 10}, {"ai": "up", "geopolitical_risk": "up"}, 10, 20, 20, "intraday", "macro",
        "FTSE 100 상승 — 美 기술주 랠리가 이란 전쟁 리스크를 상쇄."),
    "6809cc402478053d": T(["ai"], {"ai": 5}, {"ai": "up"}, 10, 15, 10, "intraday", "macro",
        "닛케이 +1.26% 마감 — 나스닥 신고가의 아시아 파급."),
    "77c5a2d8f43b3f5e": T(["china"], {"china": -5}, {"china": "neutral"}, -5, 10, 10, "intraday", "macro",
        "항셍, 24,365 저항 아래서 정체 — 중국 자산은 美 기술주 랠리에 동참하지 못함."),

    # ── AI 공급망 · 반도체 펀더멘털 ──
    "5b7a57466a319bbd": T(["ai", "semiconductor"], {"ai": 25, "semiconductor": 25}, {"ai": "up", "semiconductor": "up"}, 25, 50, 55, "medium", "other",
        "AMD 리사 수 '2027년 공급 대폭 확대' — 타이베이에서 TSMC·폭스콘 면담, 삼성·SK하이닉스와 메모리 조율. 3~5년 앞 계획이 필요할 만큼 AI 칩 수요 지속."),
    "fb75d7d1e0c10ac6": T(["ai"], {"ai": 15}, {"ai": "up"}, 15, 25, 35, "short", "other",
        "세레브라스 +9% — 올트먼 '핵심 추론 파트너' 발언으로 엔비디아 단독 선택 소문 해명. 5거래일 -19.5% 뒤 반등."),
    "540b9634414f18c7": T(["ai", "energy"], {"ai": 15, "energy": 15}, {"ai": "up", "energy": "up"}, 5, 30, 40, "medium", "other",
        "광통신 ETF 1주 +10~11% — 그러나 美 데이터센터 전력난이 납품 일정의 복병. 전력설비·ESS 가 반사이익."),
    "ac8fcf8edf3622c4": T(["ai", "energy"], {"ai": 20, "energy": 10}, {"ai": "up", "energy": "up"}, 20, 35, 50, "medium", "other",
        "LG전자, 북미 에어컨트롤콘셉트와 5GW 규모 AI DC 칠러 장기공급계약 — 주가 +5.8%. AI 인프라 수요가 냉각 장비까지 번짐."),
    "6f9f82176ec67f8c": T(["ai"], {"ai": 10}, {"ai": "up"}, 10, 15, 20, "medium", "other",
        "LG전자 AI 데이터센터 냉각·로보틱스 기대 — 증권사 목표가 상향 리포트(한경 보도)."),
    "4691b4d7db6eadbf": T(["semiconductor"], {"semiconductor": 10}, {"semiconductor": "up"}, 10, 15, 25, "medium", "other",
        "HPSP, 파운드리 넘어 메모리까지 확장 — 증권사 목표가 상향 리포트(한경 보도)."),
    "5bcf582e50c81e8c": T(["ai", "china"], {"ai": -5, "china": 5}, {"ai": "neutral", "china": "up"}, 0, 20, 30, "long", "macro",
        "세계은행, 동아시아 성장률 4.5% 로 상향하되 AI 집중 리스크 경고 — AI 관련재 밖의 교역은 '약하거나 마이너스'."),
    "b699e7555d6db5f7": T(["ai"], {"ai": 0}, {"ai": "neutral"}, -5, 20, 25, "medium", "other",
        "같은 AI 소프트웨어 ETF 인데 한 달 +9% vs -12% — 소프트웨어 안에서 승자·패자가 갈린다."),
    "9e446eb45e00012c": T(["ai"], {"ai": -10}, {"ai": "down"}, -5, 20, 25, "medium", "flow",
        "AI·반도체 숨고르기의 반사익으로 美 바이오 ETF 순풍 — 자금이 AI 밖으로 분산."),
    "a4a63cd7f0b03ff9": T(["semiconductor"], {"semiconductor": -10}, {"semiconductor": "down"}, -10, 25, 30, "medium", "other",
        "반도체 업황 꺾이면 ELS 도미노 충격 우려 — 횡보장에 ELS 로 뭉칫돈. 반도체 집중도가 시스템 리스크로 지목."),
    "33bb90a5b006e13e": T(["ai"], {"ai": 5}, {"ai": "up"}, 5, 10, 15, "long", "other",
        "국내 AI 소프트웨어 기업 'K-팔란티어' 포부 — 엔지니어 중심 조직."),
    "ef949cc9276d79bd": T(["ai"], {"ai": 5}, {"ai": "up"}, 5, 10, 20, "long", "other",
        "엘리스그룹 IPO — 'AI 교육' 에서 AI 인프라로 전환, 몸값 1조."),
    "612840ea97214e45": T(["ai", "semiconductor", "energy"], {"ai": 5, "semiconductor": 5, "energy": 5}, {"ai": "up", "semiconductor": "up", "energy": "up"}, 5, 10, 15, "long", "flow",
        "KB자산운용, 국민성장펀드로 AI·반도체·에너지 인프라 투자."),

    # ── 국내 수급 · 반도체 소부장 ──
    "69b0e1218433a24f": T(["rates", "semiconductor"], {"rates": 20, "semiconductor": -20}, {"rates": "up", "semiconductor": "down"}, -20, 55, 40, "short", "flow",
        "코스피 6,941.38(-0.89%) 7,000 아래, 코스닥 919.92(+2.98%) 910 탈환. 외국인 1조7,689억 순매도. SK하이닉스 -3.69%·삼성전자 -1.45% vs 삼성전기 +5.95%·주성 +17.5%."),
    "0e610f04096381ca": T(["ai", "semiconductor"], {"ai": 10, "semiconductor": 10}, {"ai": "up", "semiconductor": "up"}, 15, 30, 20, "intraday", "flow",
        "코스피 장초반 美 기술주 훈풍에 상승, 외인·기관 '사자' — 오후 금리 부담에 반락(마감 기사 참조)."),
    "99716a5c843c3640": T(["semiconductor", "ai"], {"semiconductor": 25, "ai": 15}, {"semiconductor": "up", "ai": "up"}, 25, 45, 35, "short", "flow",
        "반도체 소부장 급등 — 삼성전기 +5.8%, 주성엔지니어링 +8.4%, 심텍 +5.9%, HPSP +4%. 삼성전자 3분기 잠정실적을 계기로 외국인 수급 개선 기대."),
    "7cc410b33a27dcc9": T(["semiconductor"], {"semiconductor": 20}, {"semiconductor": "up"}, 15, 30, 30, "medium", "flow",
        "반도체 소부장 랠리에 ETF 출시 잇따라 — 업황 낙관과 빅테크 인프라 투자가 배경."),
    "dc4a61a74a7388ad": T(["semiconductor"], {"semiconductor": -5}, {"semiconductor": "neutral"}, 0, 15, 20, "short", "flow",
        "초고수, 삼성전자·SK하이닉스 팔고 '잭팟 계약' 종목에 풀베팅 — 대형 반도체에서 개별 재료주로 회전."),
    "b86b2b8e5c27a746": T(["semiconductor"], {"semiconductor": 5}, {"semiconductor": "neutral"}, 0, 10, 15, "medium", "regulation",
        "삼성전자·SK하이닉스 단일종목 레버리지, 매매단위 20좌 확대 앞두고 단주 출구 검토."),
    "e43a4ca7127c2233": T(["usd"], {"usd": -10}, {"usd": "down"}, 15, 25, 30, "short", "other",
        "LG이노텍 +12% — '3분기가 바닥', 환율 악재 지나고 우주·기판 기대."),
    "127e016d7dc6de2f": T(["usd"], {"usd": -25}, {"usd": "down"}, -15, 35, 40, "medium", "macro",
        "환율 12% 급락에 순이익 쇼크 주의보 — 영업이익은 좋아도 외화 자산 평가손으로 순이익이 기대에 못 미칠 수 있다(수출기업)."),
    "b0294e1bf6815912": T(["usd"], {"usd": 5}, {"usd": "up"}, 5, 20, 30, "medium", "macro",
        "2,000억달러 대미 전략투자 공개 — 증권가 '증시·환율 영향 제한적', 수혜 업종 선별."),
    "172957ec9138ab84": T(["energy", "china"], {"energy": 10, "china": -5}, {"energy": "up", "china": "down"}, 10, 20, 25, "medium", "other",
        "한화솔루션 1주 +22% — 美 수입관세 발효 앞두고 미국 공장 가동 효과, 대중관세 완화 우려 해소."),

    # ── 유가 ──
    "9e857956778e813d": T(["oil", "geopolitical_risk"], {"oil": 10, "geopolitical_risk": 5}, {"oil": "up", "geopolitical_risk": "up"}, -10, 30, 35, "medium", "macro",
        "걸프 원유 수출은 전쟁 이전 수준을 회복했는데 기름값은 왜 안 내려가나 — 유가가 공급 회복에도 높게 붙어 있다."),

    # ── 지배구조 · 주주환원 ──
    "3eddd9a3076de92f": T(["korea_governance"], {"korea_governance": 20}, {"korea_governance": "up"}, 10, 30, 40, "long", "regulation",
        "'한국형 베어허그' 입법 본격화 — 11월 정무위 소위 목표, 금융위와 '중대 인수제안' 기준 조율. 불발 시 내년 2~3월."),
    "8064afcfc8b0aa01": T(["korea_governance"], {"korea_governance": 15}, {"korea_governance": "up"}, 10, 20, 30, "long", "regulation",
        "'회사 2배 값에 사겠다는데 왜 안 파나' — 이사회 인수가격 의무공개로 대주주 주가누르기 방지, 소액주주 권익."),
    "82d6caa2371c4b9d": T(["korea_governance"], {"korea_governance": 10}, {"korea_governance": "up"}, 0, 20, 25, "long", "regulation",
        "'M&A 놀이터' vs '저평가 해소' — K베어허그법 진통. 의무공개매수 뒤 또 다른 뇌관."),
    "af0f5950acbdfd95": T(["korea_governance"], {"korea_governance": 15}, {"korea_governance": "up"}, 5, 20, 25, "long", "regulation",
        "與·금융위 '다음달 법안심사' — 보완책 병행 필요."),
    "a32520a7c7ac1b28": T(["shareholder_return"], {"shareholder_return": 10}, {"shareholder_return": "up"}, 5, 10, 15, "long", "other",
        "대신증권 자기자본 4.5조 돌파, 주주환원 늘린다."),
    "8de195a4340aaaa6": T(["shareholder_return"], {"shareholder_return": 10}, {"shareholder_return": "up"}, 5, 10, 15, "long", "other",
        "대신운용 '주주환원고배당펀드' 출시 — 주주환원에 진심인 기업 담는다."),
}

FOREIGN = [
    dict(url="https://finance.yahoo.com/markets/live/stock-market-today-monday-october-5-dow-sp-500-nasdaq-081220790.html",
         title="Stock market today: Nasdaq, Nvidia post record highs as tech strength outshines bond weakness", date="2026-10-05",
         themes=["rates", "ai", "semiconductor"], theme_sentiment={"rates": 30, "ai": 30, "semiconductor": 15}, theme_direction={"rates": "up", "ai": "up", "semiconductor": "up"},
         sentiment=25, impact=60, novelty=45, horizon="short", event_type="macro",
         reason="나스닥 27,477.31(+1.05%) 사상 최고(장중 27,544), S&P 7,773.95(+0.66%), 다우 51,267.90(+0.18%). 10년물 5.311%(+3bp), 30년 5.664%. 엔비디아·테슬라 +2%, 메타 +2%·MS +1%. 10월 인상 확률 ~20%(1주 전 ~70%)."),
    dict(url="https://www.rte.ie/news/business/2026/1005/1594005-world-oil-prices/",
         title="Oil falls as Middle East crude exports rise, G7 to release stocks", date="2026-10-05",
         themes=["oil", "geopolitical_risk"], theme_sentiment={"oil": -25, "geopolitical_risk": -15}, theme_direction={"oil": "down", "geopolitical_risk": "down"},
         sentiment=20, impact=50, novelty=45, horizon="short", event_type="geopolitical",
         reason="브렌트 12월물 101.58(-0.7%), WTI 90.14(-1.1%). G7 이 금요일 비축유·석유제품 1억 배럴 방출 합의(디젤 비중, 20일 내 공급). 중동 원유 수출 7일 평균 1,850만 b/d 로 전쟁 전(1,800만) 상회. 긴장 지속이 낙폭 제한."),
    dict(url="https://en.sedaily.com/finance/2026/10/01/hbm-prices-to-more-than-double-next-year-as-shortage",
         title="HBM Prices to More Than Double Next Year as Shortage Persists", date="2026-10-01",
         themes=["semiconductor", "ai"], theme_sentiment={"semiconductor": 30, "ai": 15}, theme_direction={"semiconductor": "up", "ai": "up"},
         sentiment=25, impact=50, novelty=50, horizon="long", event_type="other",
         reason="TrendForce: 내년 HBM 평균판매가 +121%. HBM4 12단 36GB 스택 2027년 약 1,300달러 전망. 삼성 2026년 HBM 생산능력 전량 선판매, 라인 증설 검토."),
]
