"""
2026-09-23 00:50 UTC 기준 5차 수기 태깅 (시장 봉은 9/22 종가까지).

RSS 80건 중 테마와 관련 있는 것만 읽고 태깅했다. 해외 기사는 이 세션의 웹검색으로
찾아 같은 규약으로 적었다. extractor="manual". Anthropic API 호출 아님.

부호 규약: 테마가 강해지는 방향이 +. oil/inflation/rates 는 directional 이라
유가·물가·금리 '상승' 이 direction=up 이고, sentiment 는 시장 호재/악재다.
geopolitical_risk 는 risk polarity — 긴장 고조가 +.

이번 주 맥락: 9/18 BoJ 25bp 인상(1.25%, 7:2, 엔 약세) · 9/18 뉴욕 보합 · 9/21 나스닥 사상 최고(SOX +4.3%,
AMD 시총 1조, 메타 AI 에이전트 '뮤즈') · 코스피 7,000 회복(반도체 수출 9/1~20 +259%) · 9/22 이란 "호르무즈 7일 내 재개" 제안,
사우디 파이프라인 재가동에 브렌트 100달러 아래(97.69) · 코스피 장초 +2.2% 반납 후 +0.15% · 미 10년 4.95%.
"""

def T(themes, ts, td, sentiment, impact, novelty, horizon, event_type, reason):
    return dict(themes=themes, theme_sentiment=ts, theme_direction=td, sentiment=sentiment,
                impact=impact, novelty=novelty, horizon=horizon, event_type=event_type, reason=reason)

TAGS = {
    # ── 지정학 · 유가 ──
    "320fc08f71255dd6": T(["ai", "geopolitical_risk", "oil"], {"ai": 30, "geopolitical_risk": -35, "oil": 20},
        {"ai": "up", "geopolitical_risk": "down", "oil": "down"}, 40, 65, 55, "short", "geopolitical",
        "나스닥 장중 사상 최고 — 미·이란 회담 기대. 4개월 만의 신고가."),
    "293f59ae6e6685ce": T(["ai", "geopolitical_risk"], {"ai": 25, "geopolitical_risk": -25}, {"ai": "up", "geopolitical_risk": "down"},
        25, 55, 40, "short", "macro", "9/22 뉴욕 혼조 마감, 나스닥 사상 최고. 미·이란 협상을 주시."),
    "1560a0e388e9e7c1": T(["geopolitical_risk"], {"geopolitical_risk": -20}, {"geopolitical_risk": "down"}, 25, 30, 30, "medium", "other",
        "신영증권 센터장 '중동전쟁 종결 시 랠리'. 긴장 완화를 상승 재료로 본다."),
    "7c3815c0272cc810": T(["oil", "consumer"], {"oil": 30, "consumer": 15}, {"oil": "down", "consumer": "up"}, 30, 40, 40, "short", "earnings",
        "유가 하락에 대한항공 +8.8%. 증권가 3분기 실적 개선 기대."),
    "424ae57e44fb5e0b": T(["oil", "consumer"], {"oil": 15, "consumer": 15}, {"oil": "down", "consumer": "up"}, 30, 30, 35, "medium", "earnings",
        "KB: 대한항공 내년 영업이익 전망 상향, 목표가 상향. 연료비 부담 완화 전제."),
    "fe6a1f2dfe0bfcdf": T(["oil", "usd"], {"oil": 25, "usd": 15}, {"oil": "down", "usd": "down"}, 35, 40, 35, "short", "macro",
        "유가 하락·환율 안정 겹호재에 일제히 상승, 신고가. 유가와 원화가 같은 방향으로 호재."),
    "9c043afc681765ec": T(["ai", "oil"], {"ai": 15, "oil": -15}, {"ai": "up", "oil": "up"}, -10, 45, 35, "intraday", "macro",
        "9/22 코스피: 메타 AI 기대로 급등 출발했다가 유가 부담에 상승분 반납. 장초 +2.2% → +0.15%."),
    "a73678b896a84d3b": T(["ai", "oil"], {"ai": 15, "oil": -15}, {"ai": "up", "oil": "up"}, -10, 40, 30, "intraday", "macro",
        "메타에 웃다가 유가에 발목 잡힌 코스피 — 같은 날 마감 기사."),
    "fe6d29589c04f743": T(["oil"], {"oil": 0}, {"oil": "neutral"}, -5, 20, 30, "medium", "regulation",
        "원유 ETP 잔고 47% 급증, 88% 가 레버리지·인버스. 금감원 투자 주의보 — 유가 변동성이 개인 자금을 끌어들였다."),

    # ── 반도체 · AI ──
    "653acfc89d02b587": T(["ai", "semiconductor"], {"ai": 30, "semiconductor": 30}, {"ai": "up", "semiconductor": "up"}, 35, 40, 35, "intraday", "other",
        "메타 '뮤즈' 흥행에 AI 기대감. 삼성전자·SK하이닉스 나란히 상승(장중)."),
    "298e41dc0c4b8c0f": T(["ai"], {"ai": 35}, {"ai": "up"}, 35, 45, 50, "short", "other",
        "메타의 AI 에이전트 '뮤즈' 하루 19조원 시총 증가 — 코스피도 깨울까. AI 수요 내러티브 재점화."),
    "20528c9619a4fa92": T(["ai", "semiconductor"], {"ai": 20, "semiconductor": 20}, {"ai": "up", "semiconductor": "up"}, 35, 40, 30, "intraday", "flow",
        "미 증시 급등과 외국인·기관 순매수에 코스피 7,100선 출발."),
    "c70341fd4250c381": T(["semiconductor", "ai"], {"semiconductor": -15, "ai": 10}, {"semiconductor": "down", "ai": "up"}, -10, 40, 30, "intraday", "flow",
        "AI 훈풍에도 '팔자' 에 뒷심 떨어진 코스피, SK하이닉스 하락 마감."),
    "c6847800e4cf839c": T(["rates", "semiconductor"], {"rates": 10, "semiconductor": 20}, {"rates": "up", "semiconductor": "up"}, 30, 40, 30, "short", "macro",
        "미 금리 인상에도 7,000선 회복. '변동성 줄고 기초체력 양호' — 인상은 소화됐다는 톤."),
    "1f5f97aaa1f67a9f": T(["rates", "oil", "semiconductor"], {"rates": 15, "oil": 15, "semiconductor": 25}, {"rates": "down", "oil": "down", "semiconductor": "up"},
        30, 45, 35, "short", "flow", "금리·유가 불안 낮아져 외국인 매수 재개, 매수 원톱은 반도체."),
    "e4b91baaba875fdc": T(["ai", "semiconductor"], {"ai": 30, "semiconductor": 30}, {"ai": "up", "semiconductor": "up"}, 35, 35, 40, "short", "other",
        "AMD·인텔 폭등 뒤 한국 반도체 소부장 25% 급등. 미국 세션의 칩 랠리가 국내로 전이."),
    "a61a11dd6d50a00d": T(["semiconductor", "ai"], {"semiconductor": 25, "ai": 25}, {"semiconductor": "up", "ai": "up"}, 30, 30, 30, "short", "other",
        "메타 타고 날아오른 반도체 소부장주 — 같은 랠리의 국내 기사."),
    "41b613ca98762098": T(["semiconductor"], {"semiconductor": -15}, {"semiconductor": "down"}, -15, 40, 40, "medium", "earnings",
        "키움: 삼성전자 3분기 실적이 전망을 밑돌 것. 파운드리 주목. 실적 눈높이 하향."),
    "06ea67d9885f72b9": T(["ai", "semiconductor"], {"ai": 20, "semiconductor": 15}, {"ai": "up", "semiconductor": "up"}, 25, 30, 30, "medium", "earnings",
        "메리츠: 삼성전기 환율 악재에도 AI 부품 호조, 목표가 상향."),
    "351791929babdee5": T(["semiconductor"], {"semiconductor": -20}, {"semiconductor": "down"}, -25, 40, 45, "short", "other",
        "해외 큰손이 20조를 잃었다는 소식에 'SK하이닉스 초긴장' — 포지션 청산 우려."),
    "06349dfcc6a267b9": T(["semiconductor"], {"semiconductor": 0}, {"semiconductor": "neutral"}, 0, 20, 25, "short", "flow",
        "초고수는 삼성전자·삼성전기를 담고 SK하이닉스를 던졌다. 종목 간 로테이션, 테마 방향 중립."),
    "75cd32ff41eb6316": T(["semiconductor"], {"semiconductor": 5}, {"semiconductor": "up"}, -5, 35, 25, "intraday", "macro",
        "미 반도체주 급등에도 코스피는 7천선을 겨우 지켰다 — 국내가 미국 랠리를 다 따라가지 못했다."),
    "319323b2d81b3a23": T(["ai"], {"ai": 20}, {"ai": "up"}, -10, 40, 45, "short", "other",
        "메타 AI 에이전트에 JP모건 급락 — 'AI 가 소프트웨어·금융 밸류체인을 흔든다'. 나스닥 기록에도 월가 경계."),
    "a1162170074f00ef": T(["ai"], {"ai": 20}, {"ai": "up"}, 20, 25, 30, "short", "other",
        "엔비디아·MS 강세에 LG그룹주 들썩. AI 밸류체인 확산."),
    "3ba40cfd053f0278": T(["ai"], {"ai": 15}, {"ai": "up"}, 15, 20, 30, "medium", "other",
        "삼아알미늄, AI 데이터센터 숨은 수혜주 부상."),

    # ── 금리 · 통화 ──
    "1a62fb4a52208e03": T(["rates"], {"rates": -15}, {"rates": "up"}, 5, 30, 30, "medium", "other",
        "'5%대 금리에 증시 무너질까' — 60년 데이터로는 의외로 버텼다는 칼럼. 금리 부담 인정, 공포는 부정."),
    "6ad75d7cce9d5d67": T(["rates", "usd"], {"rates": -25, "usd": 10}, {"rates": "up", "usd": "up"}, -10, 35, 30, "medium", "policy",
        "미·일 금리 더 간다 — 포트폴리오 재구성. 연준·BoJ 동반 긴축 전제."),
    "53d3a8e9bcf7ae5d": T(["rates", "consumer"], {"rates": -15, "consumer": -15}, {"rates": "up", "consumer": "down"}, -15, 25, 30, "medium", "macro",
        "은행 대출 문턱 상승, 고신용자 20% 도 거절. 긴축의 실물 전이."),

    # ── 주주환원 · 지배구조 ──
    "6a0ad9d869d50d3e": T(["shareholder_return"], {"shareholder_return": 20}, {"shareholder_return": "up"}, 15, 20, 25, "medium", "other",
        "'1000주 사면 460만원' 역대급 배당 기대."),
    "bfa8e03c57d631ba": T(["shareholder_return"], {"shareholder_return": 15}, {"shareholder_return": "up"}, 20, 20, 25, "medium", "earnings",
        "NH: KCC 실리콘 실적 개선, 주주환원 확대 긍정."),
    "27fc43e563205393": T(["korea_governance"], {"korea_governance": 15}, {"korea_governance": "up"}, 5, 25, 40, "medium", "regulation",
        "카카오, 카카오모빌리티 ADR 상장에 제동 — 모회사가 자회사 상장 반대. 지배구조 논의."),
}

FOREIGN = [
    dict(url="https://www.cnbc.com/2026/09/18/japan-raises-rates-30-year-high-yen-jgb.html",
         title="Bank of Japan raises interest rates to 31-year high, flags concerns over inflation", date="2026-09-18",
         themes=["rates", "usd"], theme_sentiment={"rates": -20, "usd": 15}, theme_direction={"rates": "up", "usd": "up"},
         sentiment=-10, impact=55, novelty=50, horizon="short", event_type="policy",
         reason="BoJ 25bp 인상 1.25%(1995년 이후 최고), 7:2 분열. 우에다 발언이 덜 매파적이라 엔은 오히려 약세(156.6)."),
    dict(url="https://www.thestreet.com/stock-market-today/stock-market-today-dow-jones-sp-500-nasdaq-updates-sept-18-2026",
         title="Stock Market Today (Sept. 18, 2026): Nasdaq, S&P 500 close a touch higher to end Fed hike week", date="2026-09-18",
         themes=["rates"], theme_sentiment={"rates": 5}, theme_direction={"rates": "neutral"},
         sentiment=10, impact=35, novelty=25, horizon="short", event_type="macro",
         reason="인상 주간 마감: 다우 -0.18%, S&P +0.17%, 나스닥 +0.39%. 트리플 위칭."),
    dict(url="https://www.koreatimes.co.kr/economy/20260921/kospi-regains-7000-as-samsung-electronics-shares-surge-on-record-chip-exports",
         title="KOSPI regains 7,000 as Samsung Electronics shares surge on record chip exports", date="2026-09-21",
         themes=["semiconductor", "ai"], theme_sentiment={"semiconductor": 45, "ai": 25}, theme_direction={"semiconductor": "up", "ai": "up"},
         sentiment=45, impact=65, novelty=55, horizon="short", event_type="macro",
         reason="코스피 7,007.72(+1.65%), 9/9 이후 첫 7,000. 삼성전자 +4.98% 274,000원. 9/1~20 반도체 수출 341억달러(+259%). 기관 1.49조 순매수, 외국인은 1,719억 순매도."),
    dict(url="https://www.staradvertiser.com/2026/09/21/breaking-news/nasdaq-hits-record-high-as-ai-chip-rally-lifts-tech-stocks/",
         title="Nasdaq hits record high as AI chip rally lifts tech stocks", date="2026-09-21",
         themes=["ai", "semiconductor", "oil", "rates"], theme_sentiment={"ai": 40, "semiconductor": 40, "oil": 15, "rates": 10},
         theme_direction={"ai": "up", "semiconductor": "up", "oil": "down", "rates": "down"},
         sentiment=45, impact=70, novelty=55, horizon="short", event_type="macro",
         reason="나스닥 27,270 사상 최고, SOX +4.3%, AMD 시총 1조 달러, 인텔 +12%, Arm +17%. 유가·금리 하락이 뒷받침."),
    dict(url="https://www.cnbc.com/2026/09/22/us-iran-war-trump-hormuz.html",
         title="Iran reportedly says it can reopen Strait of Hormuz within 7 days if U.S. eases military pressure", date="2026-09-22",
         themes=["geopolitical_risk", "oil"], theme_sentiment={"geopolitical_risk": -40, "oil": 30}, theme_direction={"geopolitical_risk": "down", "oil": "down"},
         sentiment=35, impact=70, novelty=60, horizon="short", event_type="geopolitical",
         reason="이란, 미국이 압박을 완화하면 7일 내 호르무즈 재개 제안. 백악관은 '직접 대화 없다'. 협상 기대만으로 유가 하락."),
    dict(url="https://www.thenationalnews.com/business/energy/2026/09/22/oil-falls-below-100-on-hormuz-reopening-hopes-and-saudi-pipeline-restarting/",
         title="Oil falls below $100 on Hormuz reopening hopes and Saudi pipeline restarting", date="2026-09-22",
         themes=["oil", "geopolitical_risk", "inflation"], theme_sentiment={"oil": 40, "geopolitical_risk": -30, "inflation": 15},
         theme_direction={"oil": "down", "geopolitical_risk": "down", "inflation": "down"},
         sentiment=35, impact=65, novelty=50, horizon="short", event_type="supply",
         reason="브렌트 97.69(-2.64%), 9/9 이후 첫 100달러 아래. 사우디 동서 파이프라인 감량 재가동, 얀부 수출 재개."),
    dict(url="https://finance.yahoo.com/markets/live/stock-market-today-tuesday-september-22-nasdaq-dow-sp-500-080625961.html",
         title="Stock market today: Dow slips, Nasdaq posts fresh record with AI trade, Trump diplomacy in focus", date="2026-09-22",
         themes=["ai"], theme_sentiment={"ai": 25}, theme_direction={"ai": "up"},
         sentiment=15, impact=45, novelty=30, horizon="short", event_type="macro",
         reason="S&P 보합, 나스닥 +0.4% 이틀째 최고, 다우 -0.3%. 유가 하락과 미·이란 외교를 저울질."),
    dict(url="https://www.cnbc.com/2026/09/22/treasury-yield-us-bond-market-trump.html",
         title="Treasury yields are little changed as traders await Fed comments", date="2026-09-22",
         themes=["rates"], theme_sentiment={"rates": 5}, theme_direction={"rates": "neutral"},
         sentiment=5, impact=30, novelty=20, horizon="short", event_type="macro",
         reason="10년물 4.951%(-1bp), 2년 4.741%, 30년 5.287%. 인상 뒤 금리는 5% 바로 아래에서 정체."),
    dict(url="https://www.koreatimes.co.kr/economy/20260922/kospi-loses-early-gains-as-us-tech-rally-fails-to-lift-market",
         title="KOSPI loses early gains as US tech rally fails to lift market", date="2026-09-22",
         themes=["semiconductor"], theme_sentiment={"semiconductor": -10}, theme_direction={"semiconductor": "down"},
         sentiment=-5, impact=45, novelty=35, horizon="short", event_type="flow",
         reason="코스피 7,017.91(+0.15%), 장초 +2.2% 반납. 삼성전자 276,500(+0.91%), SK하이닉스 1,840,000(-1.5%). 외국인 +851억, 개인 -1.61조."),
]
