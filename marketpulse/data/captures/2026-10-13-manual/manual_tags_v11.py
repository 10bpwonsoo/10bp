"""
2026-10-13 00:12 UTC(09:12 KST, 장 초반) 기준 11차 수기 태깅. 한국 봉은 10/12 종가가 마지막(오늘 봉은 Yahoo 지연으로 아직 없다),
미국은 10/12(콜럼버스데이 — 채권시장 휴장, 주식은 개장) 종가, FRED DGS 금리 계열은 10/8, BE10Y·BE5Y 는 10/9 가 마지막.
Yahoo 가 10/12 일봉 종가를 비운 채 meta 에만 그 날 시장가를 줘서(^KS11 · ^KQ11 · SOXX · XLU · XLK) 공급자 파서가 그 값을 쓰게 고쳤다 —
코스피 6,384.24 는 기사(전일 대비 −241.69p)와 맞는다.

RSS 80건 중 테마와 관련 있는 것만 읽고 태깅했다. RSS 본문이 비어 있는 기사는 원문 페이지를 열어 확인한 사실만 reason 에 적었다
(유료 구간이라 본문을 못 읽은 기사는 제목에서 확인되는 것만). extractor="manual". Anthropic API 호출 아님.

부호 규약: 테마가 강해지는 방향이 +. oil/inflation/rates/usd 는 directional 이라 유가·물가·금리·달러 '상승' 이 direction=up 이고,
sentiment 는 시장 호재/악재다. geopolitical_risk 는 risk polarity — 긴장 고조가 +.

맥락(10/12 한국 → 10/12 미국 → 10/13 한국 장 초반): 코스피 6,384.24(−3.65%, −241.69p) 4거래일 연속 하락 · 6,500 이 8/19 이후 처음 붕괴,
코스닥 849.19(−4.8%). 12개월 선행 PER 5.11배(작년 10월 11.30배), 외국인 이달 약 9조·올해 224조 순매도(삼성전자 171조). 미국 10/12: 다우 +0.38%
51,850.55, S&P −0.06% 7,807.24, 나스닥 −0.44% 27,245.90. 필라델피아 반도체 −2.6% — 중국 CXMT 의 4F² D램 기술 진전 주장, 마이크론 −3.9%,
SK하이닉스 ADR −4.0%, 엔비디아·브로드컴·AMD −1~2%; MS +1.4%·세일즈포스 +2.4% 로 비테크 순환. 후티의 리야드 공항 공격으로 브렌트 +1.84%
106.65·WTI +2.06% 93.74(사흘 연속). 이번 주 미국 은행 실적, 9월 CPI(10/14)·PPI. 블랙록: 미국채 6년 만에 비중확대(단기물 선호), 미국 주식 중립으로 축소.
"""

def T(themes, ts, td, sentiment, impact, novelty, horizon, event_type, reason):
    return dict(themes=themes, theme_sentiment=ts, theme_direction=td, sentiment=sentiment,
                impact=impact, novelty=novelty, horizon=horizon, event_type=event_type, reason=reason)

TAGS = {
    # ── 미국 10/12 · 반도체 급락 · 유가 ──
    "b85ac4297e5d46b6": T(["semiconductor", "ai", "oil", "geopolitical_risk"], {"semiconductor": -30, "ai": -15, "oil": 25, "geopolitical_risk": 20}, {"semiconductor": "down", "ai": "down", "oil": "up", "geopolitical_risk": "up"}, -25, 60, 55, "short", "macro",
        "뉴욕 10/12 — 다우 +0.38% 51,850.55, S&P −0.06% 7,807.24, 나스닥 −0.44% 27,245.90(콜럼버스데이 거래 한산). 중국 CXMT 의 D램 기술 진전(올해 차세대 서버 제품) 주장에 필라델피아 반도체 −2.6%, 마이크론 −3.88%, SK하이닉스 ADR −4.02%. 후티의 사우디 리야드 공항 공격에 브렌트 +1.84% 106.65·WTI +2.06% 93.74, 사흘 연속 상승."),
    "3b00b22c063d41f0": T(["semiconductor", "ai"], {"semiconductor": -25, "ai": -15}, {"semiconductor": "down", "ai": "down"}, -20, 45, 50, "short", "other",
        "혹 탄(브로드컴 CEO) '메모리 부족은 1년 내 완화…자금 조달이 가장 큰 문제' 발언과 함께 반도체 급락, 비테크로 순환매(김현석의 월스트리트나우 — 본문 유료, 제목·요약에서 확인)."),
    "b0ed06c219e35664": T(["semiconductor", "geopolitical_risk"], {"semiconductor": -20, "geopolitical_risk": 15}, {"semiconductor": "down", "geopolitical_risk": "up"}, -20, 40, 30, "short", "macro",
        "아침 7가지 — 미 반도체 지수 2%대 후반 하락(마이크론 −3.87%, 인텔 −3.15%, AMD −2.23%, 브로드컴 −1.87%), MS +1.4%·세일즈포스 +2.4%. 다시 커지는 중동 긴장."),
    "ba975e76d33a06b0": T(["semiconductor", "china"], {"semiconductor": -20, "china": 15}, {"semiconductor": "down", "china": "up"}, -20, 45, 60, "medium", "other",
        "중국 CXMT, 삼성·SK하이닉스가 아직 연구 단계인 4F² 기술을 쓴 서버용 D램을 올해 내놓겠다 — '삼성보다 2년 앞서겠다'."),
    "2baa8e11fa00a82d": T(["rates", "ai"], {"rates": -10, "ai": -5}, {"rates": "down", "ai": "neutral"}, 0, 40, 50, "medium", "flow",
        "블랙록 투자연구소: 미국채를 6년 만에 비중확대(단기물 선호, 장기물은 중립), 미국 주식은 중립으로 축소. 10년물 올해 +110bp(5.25%)는 실질금리 상승이 주도 — 연준 추가 긴축 160bp 반영은 과도하다고 판단."),
    "819de2d4ab5dd0a3": T(["semiconductor", "ai"], {"semiconductor": 10, "ai": 10}, {"semiconductor": "up", "ai": "up"}, 10, 25, 35, "medium", "other",
        "S&P, 샌디스크 신용등급 BBB 로 상향 — AI 메모리 수요로 현금흐름 230억달러 초과."),
    "0b856b903bcd25dd": T(["ai"], {"ai": -5}, {"ai": "neutral"}, -5, 15, 30, "short", "other",
        "일론 머스크발 미국 통신주 급락에 국내 통신사로 불똥."),

    # ── 국내 10/12 마감 · 수급 ──
    "a9447974aa674a2c": T(["semiconductor", "geopolitical_risk"], {"semiconductor": -35, "geopolitical_risk": 15}, {"semiconductor": "down", "geopolitical_risk": "up"}, -40, 70, 45, "short", "flow",
        "한글날 연휴 뒤 첫 거래일 코스피 −241.69p(−3%대) 급락 마감 — 삼성전자 역대급 실적에도 낙폭 확대, 코스닥 −4.8%."),
    "d363fd92c8a3de41": T(["semiconductor", "shareholder_return"], {"semiconductor": -15, "shareholder_return": -5}, {"semiconductor": "down", "shareholder_return": "down"}, -20, 45, 40, "medium", "flow",
        "코스피 −3.6% 로 6,400 붕괴, 12개월 선행 PER 5.11배(작년 10월 11.30배의 절반). 외국인 이달 약 9조 순매도 — 이익은 느는데 주가가 못 따라간다."),
    "ba0efd81d2194d93": T(["shareholder_return", "semiconductor"], {"shareholder_return": -15, "semiconductor": -10}, {"shareholder_return": "down", "semiconductor": "down"}, -20, 40, 40, "medium", "flow",
        "삼성전자·SK하이닉스 자사주 매입이 끝나자 코스피 6,500 붕괴(8/19 이후 처음) — 받아 줄 매수 주체가 없다."),
    "bc5a32632cc54402": T(["semiconductor"], {"semiconductor": -15}, {"semiconductor": "down"}, -15, 35, 30, "long", "flow",
        "삼성전자 호실적에도 외국인 매도 지속 — 올해 코스피 누적 순매도 약 224조, 이 중 171조가 삼성전자."),
    "2479210afd343a30": T(["semiconductor"], {"semiconductor": -10}, {"semiconductor": "down"}, -15, 30, 30, "medium", "flow",
        "100일간 외국인 50조 순매도 — 실적 급증에도 PER 하락, 코스피 속수무책."),
    "e3548f093320db6c": T(["semiconductor", "korea_governance"], {"semiconductor": -10, "korea_governance": -10}, {"semiconductor": "down", "korea_governance": "down"}, -10, 25, 30, "long", "flow",
        "'삼전닉스 보유하고도 B급 취급' — 외국인이 떠나는 이유(분석, 본문 유료 — 제목에서 확인)."),
    "c8819be25da4e28f": T(["semiconductor"], {"semiconductor": -5}, {"semiconductor": "neutral"}, -5, 20, 25, "medium", "flow",
        "9월 개인 국내주식 12.7조 순매도, 미국 주식 순매수도 7월 대비 78% 급감 — MMF 38조 증가."),
    "2ca1b408b7e165c2": T(["semiconductor"], {"semiconductor": 5}, {"semiconductor": "up"}, 0, 15, 25, "short", "flow",
        "서학개미, 미국 반도체 3배 레버리지 ETF 순매수 1위."),
    "2dd525379a54ac6a": T(["semiconductor", "ai"], {"semiconductor": -5, "ai": -5}, {"semiconductor": "neutral", "ai": "down"}, -5, 15, 20, "intraday", "flow",
        "12일 오후 초고수 순매수 삼성전기·삼성전자·티엘비, 순매도 LG이노텍·삼성전자우·SK하이닉스."),

    # ── 메모리 · 반도체 실적 ──
    "168727c03a7da9c5": T(["semiconductor", "ai"], {"semiconductor": 20, "ai": 5}, {"semiconductor": "up", "ai": "up"}, 15, 35, 35, "medium", "earnings",
        "하나증권(김록호): SK하이닉스 내년 영업이익 403 → 405조(매출 500조, +49%), 목표 360만원·매수 유지. 환율 가정 1,465 → 1,340원 하향에도 D램 가격 가정 상향(LPDDR 공급 부족, 장기 계약). 3분기 영업이익 77.9조로 낮아진 컨센서스 부합."),
    "5baae326a2d74acb": T(["semiconductor"], {"semiconductor": 20}, {"semiconductor": "up"}, 15, 30, 25, "medium", "earnings",
        "메리츠, SK하이닉스 목표가 320만원 — 3분기 영업이익 80조 어닝 서프라이즈 전망(전날 보도와 같은 건)."),
    "00316da2970d3f63": T(["semiconductor", "shareholder_return"], {"semiconductor": 0, "shareholder_return": -10}, {"semiconductor": "neutral", "shareholder_return": "down"}, -5, 20, 30, "long", "other",
        "솔리다임 IPO 를 보는 두 시각 — '주주 가치 훼손' vs '상장 필요'."),
    "b86194a4e50056a3": T(["ai", "semiconductor"], {"ai": 10, "semiconductor": 5}, {"ai": "up", "semiconductor": "up"}, 10, 20, 35, "medium", "other",
        "마벨이 선택한 아모텍 — 데이터센터용 MLCC 로 AI 밸류체인 편입."),
    "e66f301de5a3c2e7": T(["ai"], {"ai": -10}, {"ai": "down"}, -5, 20, 30, "long", "other",
        "엔비디아 GPU 의 수명(감가상각)이 AI 버블 여부를 결정한다는 논쟁."),

    # ── 중동 · 해운 · 유가 ──
    "e27505bd6347713e": T(["oil", "geopolitical_risk"], {"oil": 15, "geopolitical_risk": 20}, {"oil": "up", "geopolitical_risk": "up"}, -5, 35, 40, "short", "geopolitical",
        "중동 지정학 리스크 장기화로 항로 차질 — VLCC 하루 수익 일주일 새 +21.6%. 12일 STX그린로지스 +8.99%, 팬오션 +6.97%, HMM +4.81%."),
    "5c26884030cf6402": T(["oil", "geopolitical_risk"], {"oil": 10, "geopolitical_risk": 15}, {"oil": "up", "geopolitical_risk": "up"}, 0, 20, 20, "intraday", "geopolitical",
        "중동 불안 장기화로 운임 급등 — 해운주 줄줄이 상승(같은 흐름, 장 초반)."),

    # ── 금리 · 정책 ──
    "37c3bcc432040bb5": T(["rates", "inflation"], {"rates": 10, "inflation": 10}, {"rates": "up", "inflation": "up"}, -5, 35, 35, "short", "policy",
        "신현송 한은 총재(국감, 10/12): '금리 향방에서 가장 중요한 기준은 인플레이션 추이' — 10월 추가 인상 질문에 물가를 기준으로 답했다."),
    "b830b09650800275": T(["ai", "rates", "inflation"], {"ai": -10, "rates": 10, "inflation": 10}, {"ai": "down", "rates": "up", "inflation": "up"}, -10, 35, 25, "short", "macro",
        "이번 주 — 10/8 OpenAI 매출 보도가 흔든 AI 심리와 추가 금리 인상 논란, 금융·헬스케어 실적, 14일 미국 CPI 가 증시 향배를 가른다."),
    "c32eb0f95d546366": T(["rates", "ai"], {"rates": 5, "ai": 10}, {"rates": "up", "ai": "up"}, 5, 15, 20, "long", "macro",
        "미국 국채 5% 고금리를 이익의 힘으로 넘는다 — 90년대 버블과 다른 이유(칼럼)."),
    "cb831f19c549a983": T(["inflation"], {"inflation": 5}, {"inflation": "up"}, -5, 15, 25, "short", "macro",
        "인도 9월 소비자물가 5.54% — 예상 상회, 11개월 연속 상승, 추가 인상 가능성."),
    "77598b273e1cdece": T(["korea_governance"], {"korea_governance": -10}, {"korea_governance": "down"}, -10, 20, 30, "long", "macro",
        "'한국 마이너스 성장까지 4년' — 경제학계 경고."),
    "0c26ffad314c6405": T(["energy", "ai"], {"energy": 15, "ai": 5}, {"energy": "up", "ai": "up"}, 10, 20, 25, "medium", "other",
        "ESS 수주·중국산 규제 — 배터리 반등의 조건."),
}

FOREIGN: list[dict] = []   # 오늘은 RSS 에 CNBC·Investing 미국 기사가 들어와 웹검색 기사를 따로 붙이지 않았다
