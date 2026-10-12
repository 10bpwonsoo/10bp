"""
2026-10-12 06:09 UTC(15:09 KST 장중) 기준 10차 수기 태깅. 한국은 10/12 장중값(한글날 연휴 뒤 첫 거래일), 미국은 10/9(금) 종가
(지수·VIX·MOVE·섹터 ETF), FRED DGS 금리 계열은 10/8 이 마지막, BE10Y·BE5Y 는 10/9. 항셍·코스피200 은 Yahoo 가 계열을 주지 않아 결측.

RSS 80건 중 테마와 관련 있는 것만 읽고 태깅했다. RSS 본문이 비어 있는 기사는 원문 페이지를 열어 확인한 사실만 reason 에 적었다.
해외 기사 2건은 이 세션의 웹검색 결과로 제목·URL·날짜·수치가 확인된 것만 같은 규약으로 적었다(원문 페이지는 이 환경에서 열리지 않았다).
extractor="manual". Anthropic API 호출 아님.

부호 규약: 테마가 강해지는 방향이 +. oil/inflation/rates/usd 는 directional 이라 유가·물가·금리·달러 '상승' 이 direction=up 이고,
sentiment 는 시장 호재/악재다. geopolitical_risk 는 risk polarity — 긴장 고조가 +.

맥락(10/8~10/9 미국 → 10/12 한국 장중): 10/8 FT 보도 — OpenAI 가 투자자에게 밝힌 9월 말 연환산 매출 ~500억달러(9월 말 돌던 700억달러보다
200억 낮음, 회계 방식 차이). 나스닥 −1.25%(27,193.34, 8월 중순 이후 최악), S&P −0.47%(7,765.36), 엔비디아 −2.94%·오라클 −5%대.
10/9 반등: S&P +0.59% 7,811.54(10/6 최고치 근접)·다우 +0.83% 51,654.95·나스닥 +0.64% 27,366.17, 10년물 5.24%. 후티 미사일이
사우디에서 사상자(미국인 포함)를 내 미국 추가 공격 가능성 거론, 호르무즈 해협 통항 차질. 브렌트 104 안팎. 국내 10/12: 코스피 4거래일
연속 하락 — 9:02 6,558.9(−1.01%) 출발, 13:00 6,415.94(−3.17%), 코스닥 855.03(−4.17%). 외국인 1조5,600억 순매도·개인 1조900억 순매수.
삼성전자 −3.24%, SK하이닉스 −3.63%, SK스퀘어 −4.67%, LG이노텍 −15%대(애플 아이폰 18 Pro 부품 주문 축소 보도). 원·달러 장중 1,333.2원
(2024-10-04 이후 최저). 해운주 강세(HMM +3.9%, 팬오션 +5.0%). 이번 주 미국 9월 CPI(10/14, 전년 3.7% 전망)·PPI·소매판매(10/15).
"""

def T(themes, ts, td, sentiment, impact, novelty, horizon, event_type, reason):
    return dict(themes=themes, theme_sentiment=ts, theme_direction=td, sentiment=sentiment,
                impact=impact, novelty=novelty, horizon=horizon, event_type=event_type, reason=reason)

TAGS = {
    # ── 국내 급락 · 원인 ──
    "822cc6e31135930c": T(["semiconductor", "ai", "geopolitical_risk"], {"semiconductor": -30, "ai": -20, "geopolitical_risk": 25}, {"semiconductor": "down", "ai": "down", "geopolitical_risk": "up"}, -40, 70, 50, "intraday", "flow",
        "코스피 13:00 6,415.94(−3.17%) 4거래일 연속 하락, 코스닥 855.03(−4.17%). 외국인 1조5,600억 순매도·개인 1조900억 순매수. 원인: OpenAI 연환산 매출이 알려진 700억달러보다 약 29% 낮은 500억달러 수준이라는 보도 뒤 반도체 약세 + 후티 미사일로 사우디 사상자(미국인 포함)·미국 추가 공격 가능성. 삼성전자 −3.24%, SK하이닉스 −3.63%, SK스퀘어 −4.67%."),
    "58f9c39406c3cb1a": T(["geopolitical_risk", "semiconductor"], {"geopolitical_risk": 20, "semiconductor": -10}, {"geopolitical_risk": "up", "semiconductor": "down"}, -20, 45, 40, "intraday", "geopolitical",
        "연휴 마친 코스피 9:02 6,558.9(−1.01%) 출발 — 연휴 중 후티(친이란) 미사일 공격으로 사우디 사상자. 외국인 1,614억 순매도. 삼성전자 −0.86%, SK하이닉스 −2.38%, LG엔솔 +3.24%, 셀트리온 +2.34%(3분기 실적)."),
    "094e36ecdcbd5bf4": T(["ai", "semiconductor"], {"ai": -20, "semiconductor": -15}, {"ai": "down", "semiconductor": "down"}, -20, 45, 40, "short", "flow",
        "OpenAI 매출이 부풀려졌을 수 있다는 우려가 반도체 투자심리를 누르며 코스피 6,400선 후퇴. 수익률 상위 1% 투자자는 삼성전자·SK하이닉스를 팔고 SK텔레콤·SK이노베이션을 샀다."),
    "4766c30378004cf9": T(["ai", "rates", "inflation"], {"ai": -15, "rates": 15, "inflation": 10}, {"ai": "down", "rates": "up", "inflation": "up"}, -10, 40, 35, "short", "macro",
        "이번 주 점검 — 10/8 미국 증시에서 OpenAI 매출 보도가 AI 관련주 심리를 흔들었고 추가 금리 인상 가능성 논란. 고금리를 버틴 금융·헬스케어 실적 발표, 14일 美 CPI 가 증시 향배를 좌우."),
    "fe08b981b782b021": T(["rates", "inflation", "ai"], {"rates": 20, "inflation": 15, "ai": -5}, {"rates": "up", "inflation": "up", "ai": "down"}, -20, 35, 30, "medium", "macro",
        "치솟는 금리 — 미 10년물 지난달 5% 돌파 뒤 지난주 5.3% 안팎, 30년물 5.6%, 5.5~6% 전망도. 이란전쟁 이후 7개월 유가 100달러 안팎·이상기후 농산물·AI 투자 붐이 인플레이션을 지탱하고 중앙은행은 인상 기조. 고금리가 AI 투자 버블 붕괴 계기가 될 수 있다는 경고."),
    "3cc07f43fefbc392": T(["inflation", "rates"], {"inflation": 15, "rates": 10}, {"inflation": "up", "rates": "up"}, -5, 35, 30, "short", "macro",
        "이번 주 일정 — 10/14 미국 9월 CPI(전월 +0.6%·근원 +0.2%, 전년 3.7% 전망), 10/15 PPI(+0.5%)·소매판매, 워시 Fed 의장 IMF 대담, FOMC 10/27~28. 대형 금융사 3분기 실적."),
    "1b4ae8ed192e2d50": T(["rates"], {"rates": 10}, {"rates": "up"}, -10, 20, 25, "long", "macro",
        "'긴축의 시대 돌입' — 포트폴리오 대가 4인: 한국 주식은 줄이고 미국 주식 절반, 채권·금을 보험 형태로 저가 매수."),

    # ── 중동 · 유가 · 해운 ──
    "f92cbd49843cf6a1": T(["oil", "geopolitical_risk"], {"oil": 20, "geopolitical_risk": 20}, {"oil": "up", "geopolitical_risk": "up"}, -5, 40, 45, "short", "geopolitical",
        "중동 지정학 리스크 심화로 호르무즈 해협 등 해상 요충지 통항 차질, 우회 운항·대기 증가·오만만 환적 증가로 실질 선복 감소 → 탱커 운임 고수준(대신증권). STX그린로지스 +6.0%, 팬오션 +5.0%, HMM +3.9%."),
    "58a37b6f4a9d4dce": T(["semiconductor", "oil"], {"semiconductor": 10, "oil": -5}, {"semiconductor": "up", "oil": "down"}, 10, 30, 30, "short", "macro",
        "아침 7가지 — 뉴욕 9일 다우 +0.83% 51,654.95·S&P +0.59% 7,811.54·나스닥 +0.64% 27,366.17. 러시아산 경유 480만t 공급 합의(미 재무부 제재 완화 내년 4/7 까지). 반도체 소부장 강세가 이어질지."),
    "1ca5d41e3abc475f": T(["oil"], {"oil": 5}, {"oil": "up"}, 0, 15, 20, "medium", "supply",
        "Vår Energi, 2026 생산 전망 하향(3분기 36.9만 boepd) — 공급 측 소폭."),

    # ── 원화 · 수급 ──
    "24027e8356d9eac5": T(["usd", "semiconductor"], {"usd": -25, "semiconductor": 10}, {"usd": "down", "semiconductor": "up"}, 5, 40, 40, "medium", "macro",
        "원·달러 12일 장중 1,333.2원(2024-10-04 이후 최저), 6월 말 1,549.4원에서 −13.9%. 반도체 수출·경상수지 흑자(8월 461억달러)로 달러 공급, 수출기업 달러 매도. 외국인 주식 순매도(7일 2.6조)는 상승 압력."),
    "a0781d2379a0d016": T(["usd"], {"usd": -15}, {"usd": "down"}, 0, 25, 25, "medium", "macro",
        "환율 1,300원 초반 추가 하락 가능성(주간 전망)."),
    "b7194200ebf22f6e": T(["semiconductor", "usd"], {"semiconductor": -15, "usd": -10}, {"semiconductor": "down", "usd": "down"}, -15, 35, 35, "medium", "flow",
        "대만 +14%·일본 +7% 인데 코스피 +0.48% — AI 랠리 소외: ① 메모리 의존도 ② 원화 강세에 수출주 눈높이 하향 ③ 외국인 한 달 28조 순매도."),
    "8a53a7ee845f85bb": T(["semiconductor"], {"semiconductor": -10}, {"semiconductor": "down"}, -10, 35, 35, "medium", "flow",
        "삼성전자 3분기 영업이익 107조 역대 최대에도 외국인 보유율 46%대 — 2008년 금융위기 수준."),
    "eb86fc1f4a39ec09": T(["semiconductor"], {"semiconductor": -5}, {"semiconductor": "down"}, -5, 20, 15, "medium", "flow",
        "삼성전자 107조 실적에도 외국인 지분율 금융위기 수준(같은 건)."),
    "35fc6a14a6d8fca4": T(["semiconductor"], {"semiconductor": -10}, {"semiconductor": "down"}, -10, 25, 25, "medium", "flow",
        "3분기 주요 증시 중 한국 부진(중국 −12%·일본 −5%·한국 −18%, S&P·나스닥100 은 상승) — AI 반도체 랠리 뒤 급락한 롤러코스터 코스피의 4분기."),

    # ── 메모리 실적 · 반도체 ──
    "c6a370877d5ef78a": T(["semiconductor", "ai"], {"semiconductor": 30, "ai": 10}, {"semiconductor": "up", "ai": "up"}, 25, 45, 45, "medium", "earnings",
        "메리츠(김선우): SK하이닉스 3분기 영업이익 80.1조(+32% QoQ, 영업이익률 ~80%) 기대 상회, 적정주가 310 → 320만원. D램 ASP +22%·낸드 +15%, HBM4 기여 확대, 모바일 LTA 공급사 유리. 내년 1분기 모바일 D램 +65% 전망, '내년 메모리 공급 부족은 명확'."),
    "4f17ebf6cd7e0739": T(["semiconductor", "ai", "shareholder_return"], {"semiconductor": 25, "ai": 10, "shareholder_return": 10}, {"semiconductor": "up", "ai": "up", "shareholder_return": "up"}, 20, 40, 40, "medium", "earnings",
        "삼성전자 3분기 잠정 영업이익 107조 — 엔비디아(97조)를 넘어 글로벌 이익 1위. KB증권(김동원): 4분기 114조, HBM4 로 내년 HBM 판가 +100% 이상, 주주환원 확대 여지, PER 4배, 목표 60만원 유지."),
    "9e5a84d5ab7eebc9": T(["semiconductor"], {"semiconductor": 15}, {"semiconductor": "up"}, 10, 30, 30, "short", "flow",
        "코스피가 흔들리는데 반도체 소부장만 오른다 — 빅테크 AI 경쟁 심화 속 국내 반도체 업체 반사 수혜 기대."),
    "0f1ce9b6034bb591": T(["semiconductor"], {"semiconductor": 10}, {"semiconductor": "up"}, 10, 20, 20, "medium", "earnings",
        "메리츠: 원익IPS 2028년까지 실적 가시성 높아 목표가 상향."),
    "51448de6ae974b0a": T(["consumer", "semiconductor"], {"consumer": -15, "semiconductor": -5}, {"consumer": "down", "semiconductor": "down"}, -25, 40, 50, "short", "earnings",
        "LG이노텍 −15%대(48만7천원) — 닛케이: 애플이 아이폰 18 Pro 수요 부진으로 부품 주문 축소 요청. 상반기 매출의 78% 가 애플."),
    "4987af466216688b": T(["consumer"], {"consumer": -10}, {"consumer": "down"}, -15, 25, 40, "short", "earnings",
        "애플 아이폰 부품 주문 축소 — 어느 공급사가 가장 노출됐나."),

    # ── 전력 · ESS ──
    "df391a510843d06c": T(["energy", "ai"], {"energy": -10, "ai": -5}, {"energy": "down", "ai": "down"}, -15, 30, 35, "short", "earnings",
        "효성중공업 −6.7%(232.6만원) — 한화투자증권(김예인): 3분기 영업이익 2,920억, 컨센서스 3,208억 하회(중동향 물량 이연·인도시기 조정). 대신·하나도 납기 지연으로 하회 전망."),
    "cc6d4cf07b88ce2d": T(["energy", "ai"], {"energy": 20, "ai": 5}, {"energy": "up", "ai": "up"}, 20, 35, 40, "short", "earnings",
        "LG에너지솔루션 3분기 잠정 영업이익 7,560억(+25.7%, 컨센서스 +131.6%), 매출 9.64조(+59%) — ESS 물량 증가로 가동률 상승(LS증권). 주가 2거래일 연속 강세(+2.1%)."),
    "ce23f7df3de54b74": T(["energy", "ai"], {"energy": 15, "ai": 10}, {"energy": "up", "ai": "up"}, 15, 30, 30, "medium", "flow",
        "데이터센터용 ESS 수요 기대 + 호실적에 2차전지주 재충전."),
    "c7896080ca79b47a": T(["energy", "ai"], {"energy": 15, "ai": 10}, {"energy": "up", "ai": "up"}, 15, 25, 25, "medium", "other",
        "빅테크–원전 동맹: AI 데이터센터 전력 확보 경쟁에 콘스텔레이션 강세."),

    # ── 기타 ──
    "85f20a40e3e79bba": T(["china"], {"china": 10}, {"china": "up"}, -10, 20, 30, "long", "other",
        "역대급 실적에도 조선주 주가 반토막 — 2~3년 뒤 수주 둔화 우려, 중국이 신규 수주 76%."),
    "c58212020da895f2": T(["shareholder_return"], {"shareholder_return": -10}, {"shareholder_return": "down"}, -5, 20, 25, "medium", "other",
        "코스피 자사주 매입 5배 늘었지만 삼성전자·SK하이닉스를 빼면 오히려 줄었다 — 주주환원 저변 확대 미흡."),
    "cd69c40dc23cd2a2": T(["korea_governance"], {"korea_governance": 0}, {"korea_governance": "neutral"}, 0, 15, 30, "short", "other",
        "한화M&S, 김동선 1,285억 공개매수(지분 19%)에 +22% — 그룹 내 독립경영 강화."),
}

FOREIGN = [
    dict(url="https://www.wealthprofessional.ca/investments/equity-markets/ai-selloff-drags-nasdaq-down-125-as-tsx-holds-its-ground/393743",
         title="OpenAI revenue figure sinks AI stocks as Nasdaq drops 1.25%", date="2026-10-08",
         themes=["ai", "semiconductor"], theme_sentiment={"ai": -35, "semiconductor": -20}, theme_direction={"ai": "down", "semiconductor": "down"},
         sentiment=-35, impact=65, novelty=60, horizon="short", event_type="other",
         reason="FT: OpenAI 가 투자자에게 밝힌 9월 말 연환산 매출 ~500억달러 — 9월 말 돌던 ~700억달러보다 200억 낮음(회계 방식 차이, OpenAI 는 확인·부인 없음). 나스닥 −1.25% 27,193.34(8월 중순 이후 최악), S&P −0.47% 7,765.36. 엔비디아 −2.94%, 오라클 −5% 이상, 코어위브 압박."),
    dict(url="https://www.lanacion.com.ar/usa/how-major-us-stock-indexes-fared-friday-1092026-nid09102026/",
         title="How major US stock indexes fared Friday 10/9/2026", date="2026-10-09",
         themes=["ai", "rates"], theme_sentiment={"ai": 10, "rates": 5}, theme_direction={"ai": "up", "rates": "up"},
         sentiment=15, impact=40, novelty=30, horizon="short", event_type="macro",
         reason="S&P +0.6% 7,811.54(사흘 전 최고치 근접), 다우 +0.8% 51,654.95, 나스닥 +0.6% 27,366.17 — 10/8 하락 되돌림. 10년물 5.24% 로 상승, 브렌트는 장 초반 하락을 지우고 소폭 상승."),
]
