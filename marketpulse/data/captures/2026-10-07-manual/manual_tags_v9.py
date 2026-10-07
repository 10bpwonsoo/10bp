"""
2026-10-07 04:23 UTC(13:23 KST 장중) 기준 9차 수기 태깅. 한국은 10/7 장중값, 미국은 10/6 종가(지수·VIX·MOVE·섹터 ETF),
FRED DGS 금리 계열은 10/5 가 마지막, BE10Y·BE5Y 는 10/6. 항셍·니케이·코스피200 은 Yahoo 가 계열을 주지 않아 결측.

RSS 80건 중 테마와 관련 있는 것만 읽고 태깅했다. 해외 기사는 이 세션의 웹검색으로 제목·URL·날짜가 확인된 것만 같은 규약으로 적었다
(본문을 읽지 못한 기사는 넣지 않았다). extractor="manual". Anthropic API 호출 아님.

부호 규약: 테마가 강해지는 방향이 +. oil/inflation/rates/usd 는 directional 이라 유가·물가·금리·달러 '상승' 이 direction=up 이고,
sentiment 는 시장 호재/악재다. geopolitical_risk 는 risk polarity — 긴장 고조가 +.

맥락(10/6 미국 → 10/7 한국 장중): S&P 7,818.93(+0.58%)·나스닥 27,599.79(+0.45%) 사상 최고, 다우 51,521.28(+0.49%). 10년물 5.281%(−3bp,
장중 5.3% 재돌파), 30년 한때 5.7%. AMD +2.8%(씨티 목표가 800달러)·브로드컴 +3.7%·마벨 +5.8% vs 마이크론 −1.7%, SK하이닉스 ADR −6.4%.
콘스텔레이션–구글 3,590MW 원전 전력 계약에 +12.3%. 브렌트 100.6~101.5(후티의 사우디 공격). 삼성전자 15조 자사주 매입 10/6 종료,
10/8 3분기 잠정실적(컨센서스 105.5~106조, 8월 114조에서 하향 — 원화 강세 1,342원) 앞두고 골드만삭스 '세 이벤트 동시 발생' 변동성 경고.
LG전자 3분기 잠정 영업이익 7,818억(추정 9,417억 −17%) → −7.7%. 국내 10/7 장중: 코스피 6,864 개장(−1.11%) 뒤 6,882(−0.85%), 외국인
8,838억 순매도·개인 7,984억 순매수(10:40). 삼성전자 +0.5%, SK하이닉스 −1.8%. 코스닥 906(−1.5%) — 전날 +3% 뒤 소부장 차익실현.
"""

def T(themes, ts, td, sentiment, impact, novelty, horizon, event_type, reason):
    return dict(themes=themes, theme_sentiment=ts, theme_direction=td, sentiment=sentiment,
                impact=impact, novelty=novelty, horizon=horizon, event_type=event_type, reason=reason)

TAGS = {
    # ── 미국 세션 · AI vs 금리 ──
    "2a335eaba49c01d9": T(["ai", "semiconductor", "rates"], {"ai": 30, "semiconductor": 15, "rates": -5}, {"ai": "up", "semiconductor": "up", "rates": "down"}, 30, 60, 45, "short", "macro",
        "뉴욕증시 브리핑 10/6 — S&P 7,818.93(+0.58%)·나스닥 27,599.79(+0.45%) 최고치. AMD +2.8%·브로드컴 +3.7%·마벨 +5.8% 로 AI 반도체에 다시 자금, 마이크론 −1.7%·SK하이닉스 ADR −6.4%. 10년물 5.281%(−3bp), 브렌트 100.58."),
    "4493ea7f24ab507c": T(["ai", "semiconductor", "rates"], {"ai": 20, "semiconductor": -10, "rates": -5}, {"ai": "up", "semiconductor": "down", "rates": "down"}, 10, 40, 30, "short", "macro",
        "아침 7가지 — 뉴욕 최고치, 하이닉스 ADR 급락(−6.4%). 10년물 5.281% 로 조정, 유가 급등세 진정. '시장이 높은 금리보다 고금리를 견딜 이익 성장을 본다'."),
    "be5e8aa9376f4a1c": T(["ai", "rates", "semiconductor"], {"ai": 20, "rates": 15, "semiconductor": 0}, {"ai": "up", "rates": "up", "semiconductor": "neutral"}, 15, 45, 40, "medium", "macro",
        "엇갈리는 반도체(AI 가속기 ↑ · 메모리 ↓) + 넓어지는 폭 — 기술주 상승이 다른 업종으로 확산하는 순환매 조짐. AI 와 금리의 치킨게임(김현석의 월스트리트나우)."),
    "7e615016d8ee6205": T(["ai", "semiconductor"], {"ai": 25, "semiconductor": 15}, {"ai": "up", "semiconductor": "up"}, 25, 40, 45, "medium", "other",
        "씨티, AMD 목표가 575 → 800달러(메타 서버 CPU 수요). 미즈호 705달러, 델·인텔·슈퍼마이크로도 상향 — AI 서버·데이터센터 투자 낙관."),
    "a0367ed167dec4c1": T(["rates", "ai"], {"rates": 20, "ai": 15}, {"rates": "up", "ai": "up"}, 5, 30, 25, "short", "macro",
        "'한국 증시만 이런 거예요?' — 고금리 뚫고 신고가 찍은 美나스닥과 반대로 가는 국내 증시."),
    "6e5e085c67dcedab": T(["energy", "ai"], {"energy": 30, "ai": 20}, {"energy": "up", "ai": "up"}, 25, 45, 55, "medium", "other",
        "콘스텔레이션, 구글에 3,590MW 전력 공급(원전 890MW 20년 + 2,700MW 15년, 설비 43억달러) — 주가 +12.25%, 오클로 +7.2%·뉴스케일 +4.4%. AI 전력 수요가 원전으로."),
    "11d02bf4d01a4a45": T(["ai"], {"ai": 15}, {"ai": "up"}, 15, 25, 35, "medium", "other",
        "펭귄솔루션스(AI 인프라) 실적 서프라이즈 — EPS +30%·매출 5.67억달러, FY27 성장 가이던스 ~40%. 주간 +16.8%."),
    "ed3d5b7786780668": T(["rates", "oil", "semiconductor"], {"rates": 15, "oil": 15, "semiconductor": -15}, {"rates": "up", "oil": "up", "semiconductor": "down"}, -20, 40, 30, "intraday", "macro",
        "아시아 증시, 월가 신고가에도 하락 — 닛케이 −1%·코스피 −1.2%·항셍 −0.8%. 10년물 5.3%·30년 5.6% 부담, 후티의 사우디 공격에 브렌트 101 재돌파. SK하이닉스 −2%, 삼성전자 −0.6%."),
    "b7b8bdf54718777b": T(["usd"], {"usd": -5}, {"usd": "down"}, -5, 15, 25, "medium", "macro",
        "美 무역적자 1,056억달러 — 작년 관세 발효 직전 이후 최대."),
    "5bcf582e50c81e8c": T(["ai", "china"], {"ai": -5, "china": 5}, {"ai": "neutral", "china": "up"}, 0, 15, 20, "long", "macro",
        "세계은행, 동아시아 성장 4.5% 상향하되 AI 집중 리스크 경고(재송출)."),
    "7da9fc7a198ac79d": T(["ai", "china"], {"ai": 10, "china": 10}, {"ai": "up", "china": "up"}, 5, 20, 30, "long", "other",
        "中 딥시크, 투자 라운드 1,000억위안으로 두 배 — 중국 AI 자본 조달 확대."),

    # ── 삼성전자 · 메모리 실적 ──
    "a8ba19972682f470": T(["semiconductor", "usd", "shareholder_return"], {"semiconductor": -15, "usd": -15, "shareholder_return": -10}, {"semiconductor": "down", "usd": "down", "shareholder_return": "down"}, -25, 55, 50, "short", "other",
        "삼성전자 '운명의 8일' — 골드만삭스: 반도체 ETF 7개(19조) 리밸런싱 + 옵션 만기 + 15조 자사주 매입 종료(10/6) 가 겹쳐 단기 변동성. 3분기 영업이익 전망 112조 → 106조(원화 강세, 평균환율 1,418원). HBM 비트그로스는 +50% QoQ."),
    "7d78ab618d2c49f4": T(["shareholder_return", "semiconductor"], {"shareholder_return": -15, "semiconductor": -5}, {"shareholder_return": "down", "semiconductor": "neutral"}, -10, 35, 40, "short", "other",
        "삼성전자 15조 자사주 매입 10/6 종료 — 하루 5천억 고정 매수가 사라져 변동성 확대. 방향은 8일 잠정실적과 내년 초 주주환원 정책에 달렸다."),
    "3d13ee92ff90ee07": T(["semiconductor", "usd"], {"semiconductor": 10, "usd": -10}, {"semiconductor": "up", "usd": "down"}, 0, 40, 35, "short", "other",
        "삼성 3분기 프리뷰 — 영업이익 106.1조 4분기 연속 최대 예상이나 8월 말 이후 추정 −7.7%. 번스타인: 메모리 가격 상승률 3Q 10%대 중반 → 4Q 한 자릿수 후반. JPM: HBM 점유율 20 → 34%. 원화 1,342원 부담. 이틀 연속 하락."),
    "07a9f620d62fc80b": T(["semiconductor"], {"semiconductor": 25}, {"semiconductor": "up"}, 20, 40, 40, "medium", "other",
        "대신증권, 삼성전자 3분기 영업이익 106 → 110조, SK하이닉스 74 → 78조 상향 — 수급 불균형을 활용한 가격 전략이 환율 하락을 일부 상쇄. 4분기 서버 D램 +15% 기대."),
    "bc78c2c38e6f9391": T(["semiconductor", "ai"], {"semiconductor": 25, "ai": 10}, {"semiconductor": "up", "ai": "up"}, 20, 40, 45, "long", "other",
        "KB증권: 삼성전자 내년 HBM 판매가 +100% 이상, HBM4 는 D램 3사 중 가장 높은 가격에 계약 가능성. HBM4 매출 비중 40 → 80%."),
    "ed9c7bf8cbc94bcd": T(["semiconductor"], {"semiconductor": 15}, {"semiconductor": "up"}, 10, 30, 25, "short", "other",
        "삼성전자 '꿈의 영업이익' 눈앞 — 100조 훌쩍 넘나, 살짝 넘나(매경)."),
    "1fbdaab0b6ede014": T(["ai", "semiconductor"], {"ai": 10, "semiconductor": 10}, {"ai": "up", "semiconductor": "up"}, 10, 20, 25, "medium", "other",
        "삼성전기, AI 수요에 MLCC·기판 호조 — 증권사 목표가 상향 리포트(한경 보도)."),
    "d6fb13238b083379": T(["ai", "usd"], {"ai": -10, "usd": -10}, {"ai": "down", "usd": "down"}, -20, 35, 45, "short", "other",
        "LG전자 3분기 잠정 영업이익 7,818억 — 추정 9,417억에 17% 미달, 주가 −7.7%(214,500원). 전날 AI DC 냉각 계약 급등을 되돌림. 매출 23.83조(+8.9%)."),
    "39b2d84eb899fe1e": T(["ai"], {"ai": -5}, {"ai": "down"}, -10, 20, 20, "short", "other",
        "LG전자 주가 왜 빠지나 — 3분기 잠정실적 미달(같은 건)."),

    # ── 국내 수급 · 순환매 ──
    "464cab0a93e1baa9": T(["semiconductor", "rates"], {"semiconductor": -15, "rates": 10}, {"semiconductor": "down", "rates": "up"}, -20, 50, 35, "intraday", "flow",
        "'칠천피' 찍자마자 밀린 이유 — 외국인 8,838억 순매도(10:40), 개인 7,984억 순매수. 삼성전자 실적(8일)·한글날 휴장(9일) 경계. 소부장 전날 +18% 뒤 차익실현, 바이오·엔터·화장품으로 순환."),
    "9d32d3866fc25ddf": T(["semiconductor"], {"semiconductor": -10}, {"semiconductor": "down"}, -15, 35, 25, "intraday", "flow",
        "코스피 1%대 하락 출발(6,864) — 삼성전자 실적 발표 앞둔 경계. 외국인 3,467억·기관 1,283억 순매도. 삼성전자 +0.55%, SK하이닉스 −1.8%."),
    "fe1fa6012fc49d60": T(["semiconductor"], {"semiconductor": -5}, {"semiconductor": "down"}, -10, 20, 15, "intraday", "flow",
        "코스피 1.11% 내린 6,864 개장, 코스닥 0.27% 내린 917.45."),
    "2bd918a50db08374": T(["semiconductor"], {"semiconductor": 10}, {"semiconductor": "up"}, 10, 25, 20, "short", "flow",
        "'코스닥 상승장 시작됐나' — 10/6 코스닥 3% 가까이 급등, 코스피는 하락(매경)."),
    "298bef0713319f66": T(["semiconductor"], {"semiconductor": 15}, {"semiconductor": "up"}, 5, 35, 35, "medium", "flow",
        "코스닥 연저점(7/30 644.78) 대비 +42.7%, 900 회복 — 소부장은 삼성·하이닉스 설비투자 컨센서스 +34%/+51% 로 근거가 있지만 바이오·2차전지까지 확산할 근거는 부족(증권가 경고)."),
    "6f03aca3b45595ad": T(["energy", "ai"], {"energy": 15, "ai": 10}, {"energy": "up", "ai": "up"}, 15, 30, 35, "medium", "flow",
        "북미 ESS 기대에 2차전지 급등(10/6) — 삼성SDI +8.7%, 에코프로비엠 +11.4%, 엘앤에프 +9%, LG엔솔 +5.1%. AI 데이터센터 전력 보강용 ESS 수요 + 중국산 진입 장벽."),
    "fa8bd9a0311d811a": T(["semiconductor"], {"semiconductor": 20}, {"semiconductor": "up"}, 15, 30, 25, "short", "flow",
        "MK 시그널 — 소부장株 두 자릿수 상승, 이엔에프테크 +24%(10/6)."),
    "500284d7525347ce": T(["semiconductor", "energy"], {"semiconductor": 0, "energy": 10}, {"semiconductor": "neutral", "energy": "up"}, 0, 20, 25, "short", "flow",
        "초고수의 선택 — 하이닉스 대신 삼성전자, 소부장 대신 2차전지·전력으로 회전."),
    "6615e2e9d86ef80d": T(["semiconductor"], {"semiconductor": 0}, {"semiconductor": "neutral"}, 0, 15, 20, "short", "flow",
        "3% 내린 하이닉스 사고 18% 뛴 주성 팔았다 — 초고수의 역발상."),
    "5591a42c481dfbc0": T(["semiconductor"], {"semiconductor": -10}, {"semiconductor": "down"}, -10, 30, 30, "long", "flow",
        "올해 외국인 200조 순매도 — 그 와중에 꾸준히 사모은 톱10."),
    "613d4cc432d92734": T(["rates"], {"rates": 15}, {"rates": "up"}, -5, 25, 30, "medium", "flow",
        "고금리 덮치자 국민연금, 보험株 사고 증권株 팔아 — 금리 상승 대비 포지션(매경)."),
    "a452d57f5cc5f3de": T(["semiconductor"], {"semiconductor": 5}, {"semiconductor": "up"}, 5, 10, 20, "long", "flow",
        "신한운용 'SOL 글로벌DRAM반도체플러스' ETF 상장 — 메모리 테마 상품 추가."),
    "b7ba7c3404073246": T(["ai"], {"ai": 10}, {"ai": "up"}, 10, 15, 15, "short", "flow",
        "신고가 엔비디아 따라 두산·LG전자 랠리(10/6, 매경) — 이튿날 LG전자는 실적 미달로 반락."),
    "c902b6063e74008e": T(["korea_governance"], {"korea_governance": 5}, {"korea_governance": "neutral"}, 0, 10, 20, "long", "regulation",
        "레버리지 ETF 도입은 금융위가 최종 결정 — 국감 답변."),
}

FOREIGN = [
    dict(url="https://finance.yahoo.com/markets/live/stock-market-today-tuesday-october-6-dow-sp-500-nasdaq-080526166.html",
         title="Stock market today: S&P 500, Nasdaq hit record highs as Nvidia, AMD lead tech higher", date="2026-10-06",
         themes=["ai", "semiconductor", "rates", "oil"], theme_sentiment={"ai": 30, "semiconductor": 15, "rates": -5, "oil": -5}, theme_direction={"ai": "up", "semiconductor": "up", "rates": "down", "oil": "down"},
         sentiment=25, impact=55, novelty=40, horizon="short", event_type="macro",
         reason="S&P 7,818.93(+0.58%)·나스닥 27,599.79(+0.45%) 사상 최고, 다우 51,521.28(+0.49%). 10년물 5.275%(−3.6bp) 로 오후 하락, 장중 5.3%·30년 5.7% 재돌파. 유가 소폭 후퇴. 엔비디아·AMD 가 기술주 주도."),
    dict(url="https://www.investing.com/news/stock-market-news/samsung-sk-hynix-shares-drop-as-q3-earnings-loom-4933402",
         title="Samsung, SK Hynix shares drop as Q3 earnings loom", date="2026-10-06",
         themes=["semiconductor", "usd"], theme_sentiment={"semiconductor": -20, "usd": -10}, theme_direction={"semiconductor": "down", "usd": "down"},
         sentiment=-20, impact=45, novelty=35, horizon="short", event_type="other",
         reason="삼성전자 −1.8%, SK하이닉스 −3.4% — 원화 강세(해외 이익 축소), AI 호황 성과급 충당, 데이터센터 칩 수요 둔화 우려. 삼성 3분기 영업이익 100조 이상(사상 최대) 전망. 마이크론은 '메모리 공급 1년 이상 타이트'."),
]
