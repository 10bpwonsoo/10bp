"""
2026-10-14 01:26 UTC(10:26 KST, 장 초반) 기준 12차 수기 태깅. 한국 봉은 10/14 장중값(코스피 6,106), 미국은 10/13 종가, FRED DGS 금리 계열은 10/9,
BE10Y·BE5Y 는 10/13 이 마지막. Yahoo 일봉에서 10/13 봉이 통째로 비어(^KS11 · ^KQ11 · ^N225 · CL=F · BZ=F · GC=F · HG=F · NG=F · DX-Y.NYB)
같은 공급자의 60분봉 meta.previousClose 로 그 날 종가를 넣었다(fill_prev_close.py) — 코스피 6,035.35 는 기사(−348.89p, −5.46%)와 맞는다.

RSS 80건 중 테마와 관련 있는 것만 읽고 태깅했다. RSS 본문이 비어 있는 기사는 원문 페이지를 열어 확인한 사실만 reason 에 적었다
(유료·차단으로 본문을 못 읽은 기사는 제목·RSS 요약에서 확인되는 것만). extractor="manual". Anthropic API 호출 아님.

부호 규약: 테마가 강해지는 방향이 +. oil/inflation/rates/usd 는 directional 이라 유가·물가·금리·달러 '상승' 이 direction=up 이고,
sentiment 는 시장 호재/악재다. geopolitical_risk 는 risk polarity — 긴장 고조가 +.

맥락(10/13 한국 → 10/13 미국 → 10/14 한국 장 초반): 10/13 '검은 화요일' 코스피 6,035.35(−348.89p, −5.46%) 5거래일 연속 하락, 장중 5,911.11(−7.41%),
매도 사이드카(2개월 만), 삼성전자 −7.39% · SK하이닉스 −10.09%, 외국인 두 종목만 약 3.7조 순매도. 코스닥 837.03(−1.43%). 신용융자 34.3조(3개월 최대).
방아쇠: 중국 CXMT 의 차세대 서버 D램(4F²) 계획 + 브로드컴발 악재, 삼성전자 자사주 매입 종료로 수급 공백. 미국 10/13: 다우 −0.35% 51,670.10,
S&P −0.02% 7,805.45, 나스닥 −0.15% 27,204.38, 필라델피아 반도체 −0.23%(5일 연속) — 마이크론 −3.62% · 어플라이드 −6.69%, 엔비디아 +0.97%.
씨티 −5.6% · 웰스파고 −3.1% · 골드만 −0.2%(순이익 증가에도 기대 미달). 브렌트 105.69(−0.90%) · WTI 94.14(+0.43%) — 미·러 경유 거래 합의 vs 중동 긴장.
10/14 오전: 코스피 +1.2% 6,110 안팎(삼성전자 +3% · 하이닉스 +2%대 반발 매수), 코스닥 약세. 오늘 밤 미국 9월 CPI(컨센서스 전월 +0.6% · 전년 +3.6%, CNBC).
"""

def T(themes, ts, td, sentiment, impact, novelty, horizon, event_type, reason):
    return dict(themes=themes, theme_sentiment=ts, theme_direction=td, sentiment=sentiment,
                impact=impact, novelty=novelty, horizon=horizon, event_type=event_type, reason=reason)

TAGS = {
    # ── 10/13 한국 '검은 화요일' ──
    "90482cfd28cc93c1": T(["semiconductor", "china"], {"semiconductor": -40, "china": 15}, {"semiconductor": "down", "china": "up"}, -45, 80, 55, "short", "flow",
        "10/13 코스피 −348.89p(−5.46%) 6,035.35 마감, 장중 5,900선까지 — 외국인 거센 매도. 6,000선 턱걸이."),
    "81b683334be3f3b9": T(["semiconductor", "china"], {"semiconductor": -35, "china": 15}, {"semiconductor": "down", "china": "up"}, -40, 60, 40, "intraday", "flow",
        "10/13 장중 코스피 −6% 넘게 급락해 6,000선 아래 — 중국 반도체 기술 추격 우려 속 삼성전자·SK하이닉스 동반 급락, 코스닥도 −4%대 810선."),
    "2613a700504c38e1": T(["semiconductor"], {"semiconductor": -25}, {"semiconductor": "down"}, -30, 45, 35, "intraday", "flow",
        "10/13 오전 9시47분 코스피 매도 사이드카 — 올해 50번째, 매도로는 26번째."),
    "c46e50c0d02211f1": T(["semiconductor"], {"semiconductor": -20}, {"semiconductor": "down"}, -20, 30, 30, "short", "flow",
        "'이번엔 심상치 않다' — 삼전닉스 개인 투자자 손실 확대(분석, 제목에서 확인)."),
    "7321944b2ec7cb53": T(["semiconductor"], {"semiconductor": -5}, {"semiconductor": "neutral"}, -10, 25, 30, "short", "flow",
        "신용융자 잔고 34.29조(10/12 기준, +4,773억) — 7/15 이후 3개월 최대. 급락장 저가 매수 자금이 레버리지로 유입."),
    "5b10d61b312627ea": T(["semiconductor", "shareholder_return"], {"semiconductor": -15, "shareholder_return": -10}, {"semiconductor": "down", "shareholder_return": "down"}, -20, 35, 30, "medium", "flow",
        "10/13 코스피 장중 5,911.11(−7.41%)까지 — 방아쇠는 중국산 반도체, 삼성전자 자사주 매수 종료로 하단 수급이 약해졌다. 보수적 대응 vs 저가 매수 의견 엇갈림."),
    "70203c256ca1c51d": T(["semiconductor", "ai"], {"semiconductor": -30, "ai": -15}, {"semiconductor": "down", "ai": "down"}, -30, 45, 40, "short", "flow",
        "반도체 피크아웃 우려 확산 — 브로드컴발 악재와 CXMT 공세의 '쌍끌이 충격'. 고금리·수급 공백 속 반도체 서사로 버티던 코스피 직격."),
    "b9756399b6678f86": T(["shareholder_return", "semiconductor"], {"shareholder_return": -15, "semiconductor": -15}, {"shareholder_return": "down", "semiconductor": "down"}, -20, 40, 35, "medium", "flow",
        "삼성전자 15조 자사주 매입 조기 완료, 하이닉스도 종료 임박 — 외국인 매도에 반도체주 동반 급락, 받칠 수급이 없다."),
    "348aa6ea2ff72d40": T(["semiconductor", "china", "rates", "oil"], {"semiconductor": -30, "china": 15, "rates": 10, "oil": 10}, {"semiconductor": "down", "china": "up", "rates": "up", "oil": "up"}, -30, 50, 35, "short", "macro",
        "코스피 5거래일 연속 하락·장중 6,000 붕괴 — 고금리·고유가 압박 속 중국 메모리 기술 추격 우려가 투자심리를 얼렸다."),
    "251a2f127326b6b6": T(["semiconductor", "geopolitical_risk", "oil", "rates"], {"semiconductor": -25, "geopolitical_risk": 15, "oil": 15, "rates": 10},
        {"semiconductor": "down", "geopolitical_risk": "up", "oil": "up", "rates": "up"}, -25, 40, 30, "short", "macro",
        "중동발 유가 급등 → 금리 급등에 글로벌 증시가 흔들리지만 미국은 차분 — 반도체 비중이 큰 한국 증시 낙폭이 일본·대만의 3배."),
    "ca912bcfd7c8a5b6": T(["semiconductor", "china"], {"semiconductor": -25, "china": 20}, {"semiconductor": "down", "china": "up"}, -25, 40, 40, "medium", "other",
        "'창신메모리 쇼크' 긴급진단 — 중국과의 반도체 기술 격차 2~3년, 코스피 5,000까지 밀릴 수 있다는 의견."),
    "47d3c20e01c7fb55": T(["semiconductor", "china"], {"semiconductor": -20, "china": 15}, {"semiconductor": "down", "china": "up"}, -20, 30, 30, "medium", "flow",
        "전문가: 중국 기술 추격이 한국 반도체의 중장기 위협으로 부상 — 당분간 미국 주식 비중 확대 의견(기사 인용, 추천 아님)."),
    "54f09df1359db33e": T(["semiconductor", "china"], {"semiconductor": -15, "china": 15}, {"semiconductor": "down", "china": "up"}, -15, 30, 35, "medium", "other",
        "CXMT, 삼성·하이닉스도 연구 단계인 4F² 기술 서버용 D램 계획 — '삼성보다 2년 빠르다'(같은 건 해설)."),
    "5ce24cf92c79c3cd": T(["semiconductor"], {"semiconductor": 10}, {"semiconductor": "up"}, 10, 25, 30, "medium", "flow",
        "삼전닉스 폭락에도 '지금이 저점' — W자 반등 전망(분석, 본문 유료 — 제목에서 확인)."),
    "cfbda0ef91b1d288": T(["semiconductor"], {"semiconductor": -5}, {"semiconductor": "neutral"}, -5, 25, 25, "medium", "flow",
        "6천피 불안에 증권가 온도차 — KB·LS 분할매수, 삼성·미래 단기 반등 어렵다. 내년 반도체 이익이 관건."),

    # ── 미국 10/13 ──
    "52a1789d1255bb40": T(["semiconductor", "china", "oil", "geopolitical_risk"], {"semiconductor": -15, "china": 10, "oil": 0, "geopolitical_risk": 10},
        {"semiconductor": "down", "china": "up", "oil": "neutral", "geopolitical_risk": "up"}, -15, 55, 45, "short", "macro",
        "뉴욕 10/13 — 다우 −0.35% 51,670.10, S&P −0.02% 7,805.45, 나스닥 −0.15% 27,204.38, 필라델피아 반도체 −0.23%(5일 연속). 마이크론 −3.62%·어플라이드 −6.69%, "
        "엔비디아 +0.97%. 씨티 −5.6%·웰스파고 −3.1%(순이익 증가에도 기대 미달). 브렌트 105.69(−0.90%)·WTI 94.14(+0.43%) — 미·러 경유 거래 합의 vs 중동 긴장."),
    "3c2358a6d012b22e": T(["semiconductor", "ai"], {"semiconductor": -15, "ai": -5}, {"semiconductor": "down", "ai": "neutral"}, -10, 35, 30, "short", "macro",
        "나스닥 하락 마감 — 반도체 약세와 대형은행 실적 시즌 개막(제목에서 확인)."),
    "08070b5bcdc4c63c": T(["inflation", "rates", "semiconductor"], {"inflation": 10, "rates": 5, "semiconductor": -5}, {"inflation": "up", "rates": "neutral", "semiconductor": "neutral"}, -5, 40, 30, "short", "macro",
        "미국 지수선물 보합 — 반도체 손실이 월가를 끌어내린 뒤 CPI 대기(제목에서 확인)."),
    "75b387bfe2d9e8b1": T(["inflation", "rates"], {"inflation": 25, "rates": 10}, {"inflation": "up", "rates": "up"}, -10, 55, 45, "short", "macro",
        "CNBC 미리보기: 9월 CPI 컨센서스 전월 +0.6%·전년 +3.6% — 물가 상승이 다시 빨라질 것으로 예상(발표 전 전망치 — 실제치 아님)."),
    "5d2f4046de5831aa": T(["ai"], {"ai": -5}, {"ai": "neutral"}, -5, 15, 35, "short", "other",
        "FBI, 비밀 녹음 장치 혐의로 OpenAI 전 직원 체포(DOJ, 제목에서 확인)."),
    "348aa2fba297525b": T(["ai"], {"ai": 10}, {"ai": "up"}, 10, 20, 25, "medium", "other",
        "월가, 메타 목표가 1,000달러 — 성장주 매수 의견 확대(월가 업&다운, 제목에서 확인)."),

    # ── 10/14 한국 장 초반 ──
    "1ebdad9685ef2b2b": T(["semiconductor", "rates"], {"semiconductor": 15, "rates": -5}, {"semiconductor": "up", "rates": "neutral"}, 15, 45, 35, "intraday", "flow",
        "10/14 코스피 상승 출발 9시6분 6,110.41(+1.24%), 외국인 +177억·기관 +34억. 삼성전자 +2.59% 23.8만·하이닉스 +2.29% 147.6만. 키움 한지영: CPI 대기·중국발 반도체 노이즈에도 "
        "연준 인사들의 완화적 발언, 5거래일 연쇄 급락 뒤 저가 매수. 코스닥 −0.54% 832.55."),
    "767eb2f1bb519d14": T(["semiconductor"], {"semiconductor": 15}, {"semiconductor": "up"}, 15, 35, 25, "intraday", "flow",
        "10/14 9시44분 삼성전자 +3.13% 23.9만·하이닉스 +2.43% 147.8만 — 전날 −7.39%·−10.09% 급락 뒤 반발 매수. 외국인은 전날 두 종목만 약 3.7조 순매도."),
    "eb9c073683796aae": T(["energy", "geopolitical_risk"], {"energy": 20, "geopolitical_risk": 0}, {"energy": "up", "geopolitical_risk": "neutral"}, 10, 30, 40, "short", "other",
        "알래스카 LNG 개발 기대 재부각(백악관 언급) — 화성밸브 상한가, 대한제강 +24.6% 등 강관주 급등, 현대제철·POSCO홀딩스도 강세."),
    "16218eec32918091": T(["energy"], {"energy": 15}, {"energy": "up"}, 10, 20, 30, "intraday", "other",
        "미국 알래스카 LNG 투자 언급에 관련주 25% 급등(같은 흐름)."),
    "744842e48caee9c6": T(["oil", "geopolitical_risk"], {"oil": 5, "geopolitical_risk": 5}, {"oil": "neutral", "geopolitical_risk": "neutral"}, 10, 20, 25, "intraday", "earnings",
        "HMM +5.4% — 신한투자 3분기 영업이익 1.0조 추정, 목표 2.6만·매수 상향. 관세 변경 전 성수기 물동량·항만 적체·파나마 병목으로 컨테이너 운임 급등."),
    "d656603e670a72d4": T(["energy", "ai"], {"energy": 10, "ai": 5}, {"energy": "up", "ai": "up"}, 10, 15, 20, "short", "earnings",
        "삼성SDI, ESS 성장에 따른 3분기 호실적 전망으로 강세(제목에서 확인)."),
    "c82589900ac8f6ea": T(["korea_governance"], {"korea_governance": -5}, {"korea_governance": "neutral"}, -5, 15, 30, "short", "other",
        "신한지주 −2.2% — 롯데손보 지분 77.04% 6,933억 인수 계약, 한화투자 'CET1 0.19%p 하락' — 승자의 저주 우려."),
    "e09f2564fac0d427": T(["korea_governance"], {"korea_governance": 0}, {"korea_governance": "neutral"}, 0, 20, 35, "long", "other",
        "홍라희 관장, 이재용 회장에 2.6조 규모 삼성전자 지분 증여(제목에서 확인)."),
    "d73fd5762c94d00f": T(["rates"], {"rates": -10}, {"rates": "down"}, 0, 30, 20, "medium", "flow",
        "블랙록, 6년 만에 미국채 비중확대(같은 건 — 10/12 Investing 보도와 동일)."),
}

FOREIGN: list[dict] = []   # 오늘도 RSS 에 CNBC·Investing 미국 기사가 들어와 웹검색 기사를 따로 붙이지 않았다
