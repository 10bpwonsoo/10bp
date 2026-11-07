"""
2026-09-16 02:05 UTC 기준 3차 수기 태깅.

RSS 80건 중 이전 캡처와 겹치는 2건은 2차 태그를 그대로 쓰고, 새 78건 중
테마와 관련 있는 것만 읽고 태깅했다. 해외 기사는 이 세션의 웹검색으로 찾아
같은 규약으로 적었다. extractor="manual". Anthropic API 호출 아님.

부호 규약: 테마가 강해지는 방향이 +. oil/inflation/rates 는 directional 이라
유가·물가·금리 '상승' 이 direction=up 이고, sentiment 는 시장 호재/악재다.
geopolitical_risk 는 risk polarity — 긴장 고조가 +.
"""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-10bp/d1217ff9-9e47-595a-ade2-530a334c6aba/scratchpad")
from manual_tags_v2 import TAGS as V2

TAGS = dict(V2)  # 겹치는 기사는 이전 태그 유지 (빌드 스크립트가 raw 에 없는 id 는 버린다)

def T(themes, ts, td, sentiment, impact, novelty, horizon, event_type, reason):
    return dict(themes=themes, theme_sentiment=ts, theme_direction=td, sentiment=sentiment,
                impact=impact, novelty=novelty, horizon=horizon, event_type=event_type, reason=reason)

TAGS.update({
    # ── 금리 · 연준 ──
    "ffaa6c4217a56de8": T(["rates"], {"rates": -30}, {"rates": "up"}, -25, 55, 50, "short", "policy",
        "FOMC 인상이 워낙 반영돼 '동결이 오히려 악재' 라는 프레임. 인상 기대 자체는 유지."),
    "c7a53bf112140d12": T(["rates"], {"rates": -45}, {"rates": "up"}, -40, 60, 55, "medium", "policy",
        "한 번으로 끝나느냐 연속 인상이냐. 10% 조정론이 커진다는 월가 분위기 전달."),
    "9da81f070ee8bee6": T(["rates"], {"rates": -35}, {"rates": "up"}, -30, 45, 40, "medium", "policy",
        "연준 인상 사이클 진입을 가볍게 보지 말라는 칼럼. 긴축 장기화 경계."),
    "fbc09aaa2acae7d3": T(["rates"], {"rates": -10}, {"rates": "up"}, 5, 30, 25, "intraday", "macro",
        "선물은 소폭 반등. 인상은 기정사실이고 관심은 향후 경로."),
    "106778e9254178e4": T(["rates", "oil", "ai"], {"rates": -50, "oil": 40, "ai": -25},
        {"rates": "up", "oil": "up", "ai": "down"}, -50, 80, 60, "short", "macro",
        "10년물 5% 재돌파와 유가 급등에 뉴욕 3대 지수 하락, 나스닥 -0.78%."),
    "70a3d09e0e4a4bda": T(["rates", "defense", "usd"], {"rates": -55, "defense": -35, "usd": -20},
        {"rates": "up", "defense": "down", "usd": "down"}, -55, 65, 55, "short", "macro",
        "미 장기금리 급등과 원화 강세로 조선·방산·전력기기 등 중후장대 업종 급락."),
    "c15ce6bf0d960c8f": T(["rates", "ai"], {"rates": -25, "ai": -25}, {"rates": "up", "ai": "down"}, -10, 50, 40, "medium", "other",
        "금리·AI 두 악재를 진단하되 전문가들은 '쫄지 마라' — 악재 인정, 패닉은 부정."),

    # ── AI · 반도체 ──
    "eca408e79bccf7a6": T(["semiconductor", "ai"], {"semiconductor": -50, "ai": -30},
        {"semiconductor": "down", "ai": "down"}, -50, 70, 55, "short", "other",
        "외국인이 5일간 삼성전자·하이닉스 10조원 순매도. AI 속도조절론과 금리 부담."),
    "9fcecea8c67ce119": T(["ai", "semiconductor"], {"ai": -55, "semiconductor": -50},
        {"ai": "down", "semiconductor": "down"}, -55, 80, 70, "medium", "other",
        "올트먼·아모데이·머스크가 한목소리로 AI 속도 조절. 반도체 수요 둔화 우려."),
    "b10ab63e85270a94": T(["ai"], {"ai": -35}, {"ai": "down"}, -25, 45, 50, "short", "other",
        "AI 속도조절론으로 빅테크·반도체에서 사이버보안주로 자금 이동."),
    "aceba875fca5797c": T(["ai", "semiconductor"], {"ai": 15, "semiconductor": 15},
        {"ai": "up", "semiconductor": "up"}, 15, 35, 45, "medium", "other",
        "증권가는 AI 속도조절이 하드웨어 수요를 줄이지 않는다는 반전 해석."),
    "dd66840356ceb5ab": T(["ai", "semiconductor"], {"ai": 15, "semiconductor": 10},
        {"ai": "up", "semiconductor": "up"}, 15, 30, 35, "medium", "other",
        "박스권 코스피에도 증권가는 상승 전망. AI 인프라주 비관 해석은 불필요하다는 시각."),
    "3de983c364160de3": T(["semiconductor"], {"semiconductor": -20}, {"semiconductor": "down"}, -20, 30, 30, "short", "other",
        "'60만전자' 전망 뒤 급락으로 개인 투자자 혼란. 심리 위축."),
    "6ba56860472c0d43": T(["semiconductor"], {"semiconductor": 15}, {"semiconductor": "up"}, 15, 25, 40, "short", "other",
        "SK하이닉스 노조 성과급 합의 — 파업 리스크 해소."),
    "c70d8315a612a3a5": T(["semiconductor"], {"semiconductor": 10}, {"semiconductor": "up"}, 10, 20, 45, "medium", "other",
        "키옥시아 미국 ADR 100억달러 조달 추진. 메모리 투자 사이클 지속 신호."),
    "a67f681e429a7088": T(["china", "ai"], {"china": 15, "ai": 10}, {"china": "up", "ai": "up"}, 15, 30, 45, "medium", "policy",
        "엔비디아 CEO가 미중 정상 만찬 참석 — 대중 반도체 규제 완화 기대."),
    "3a1d501236a25d14": T(["ai"], {"ai": -10}, {"ai": "down"}, -10, 25, 40, "long", "policy",
        "뉴욕주가 데이터센터에 MW당 100만달러 지역투자 요구. AI 인프라 비용 상승."),
    "d895910a088de42c": T(["ai", "energy"], {"ai": 25, "energy": 20}, {"ai": "up", "energy": "up"}, 30, 35, 50, "medium", "other",
        "효성중공업 미 빅테크 초고압변압기 3865억 수주 — AI 데이터센터 전력 수요 실증."),

    # ── 지배구조 · 주주환원 ──
    "fe91e08c37ab710b": T(["shareholder_return", "korea_governance"], {"shareholder_return": 40, "korea_governance": 35},
        {"shareholder_return": "up", "korea_governance": "up"}, 35, 40, 50, "medium", "other",
        "라이프자산운용, 삼성전자에 우선주 매입·소각 우선 배정 요구 주주서한."),
    "96261dfdcc73b236": T(["korea_governance", "shareholder_return"], {"korea_governance": 30, "shareholder_return": 15},
        {"korea_governance": "up", "shareholder_return": "up"}, 30, 30, 45, "medium", "other",
        "한화 인적분할 후 합산 시총 33.9% 증가 — 지배구조 재편이 밸류에이션 재평가로."),
    "346702520af6c1b5": T(["korea_governance"], {"korea_governance": 30}, {"korea_governance": "up"}, 25, 35, 55, "long", "policy",
        "계열사 합병 외부평가 강화·공시 확대. 12월 시행. 소액주주 보호 제도 개선."),
    "bfe70b079889fc87": T(["korea_governance"], {"korea_governance": 25}, {"korea_governance": "up"}, 25, 30, 50, "medium", "policy",
        "첫 코리아 프리미엄 위크 — 정부·거래소가 해외 투자자 대상 통합 IR. 거래시간 연장 등 논의."),
    "4e05ca1b86e8e7e2": T(["shareholder_return"], {"shareholder_return": 25}, {"shareholder_return": "up"}, 20, 15, 35, "medium", "other",
        "주주행동 플랫폼이 중소형사 654억 배당 이끌어냄."),
    "81173794a9a80726": T(["shareholder_return", "consumer"], {"shareholder_return": 25, "consumer": 25},
        {"shareholder_return": "up", "consumer": "up"}, 25, 20, 30, "medium", "other",
        "BGF리테일 실적·주주환원 기대 목표가 상향."),
    "28d8c13f92a166da": T(["korea_governance"], {"korea_governance": -15}, {"korea_governance": "down"}, -15, 20, 45, "medium", "other",
        "대형 운용사 ETF 선행매매 조사 — 시장 신뢰 훼손."),
    "db79783ed789b84e": T(["korea_governance"], {"korea_governance": -10}, {"korea_governance": "down"}, -10, 15, 40, "short", "other",
        "에이비엘바이오 미공개정보 이용 혐의 압수수색."),

    # ── 달러 · 소비 · 방산 · 에너지 ──
    "df173c2d0c76a6ff": T(["usd"], {"usd": 20}, {"usd": "up"}, 15, 30, 35, "long", "other",
        "탈달러 논의는 말뿐이라는 CNBC 분석. 달러 기축 지위 유지."),
    "e8b5f5d5ab117d0f": T(["consumer"], {"consumer": -20}, {"consumer": "down"}, -20, 20, 30, "long", "other",
        "나이키 S&P100 제외, 글로벌 매출 감소. 소비재 브랜드 부진."),
    "d6daa8a4394078a2": T(["defense"], {"defense": 20}, {"defense": "up"}, 20, 15, 40, "medium", "other",
        "아고스 카자흐 국영기업과 대드론 방어 MOU. 방산 수출 저변 확대."),
    "20bbab59d69b223e": T(["energy"], {"energy": 20}, {"energy": "up"}, 20, 15, 35, "short", "other",
        "LS에코에너지 미 태양광 케이블 공급 소식에 급등."),
})

# ── 해외 기사 (이 세션의 웹검색). 48시간 안의 것만 ──
FOREIGN = [
    dict(url="https://qz.com/stock-futures-10-year-treasury-yield-5-percent-fed-091526",
         title="Stock futures fall as 10-year Treasury yield tops 5%", date="2026-09-15",
         themes=["rates"], theme_sentiment={"rates": -55}, theme_direction={"rates": "up"},
         sentiment=-50, impact=80, novelty=60, horizon="short", event_type="macro",
         reason="10년물 5% 돌파에 선물 하락. FOMC 인상 앞둔 긴축 경계."),
    dict(url="https://finance.yahoo.com/markets/live/stock-market-today-tuesday-september-15-dow-sp-500-nasdaq-081307838.html",
         title="Stock market today: Dow, S&P 500, Nasdaq fall as 10-year Treasury yield touches 2007 high ahead of Fed decision day", date="2026-09-15",
         themes=["rates", "ai", "oil"], theme_sentiment={"rates": -50, "ai": -20, "oil": 35},
         theme_direction={"rates": "up", "ai": "down", "oil": "up"},
         sentiment=-45, impact=85, novelty=65, horizon="short", event_type="macro",
         reason="10년물 2007년 이후 최고(5.04%), 유가 108달러. 3대 지수 하락, 나스닥 -0.8%."),
    dict(url="https://www.thestreet.com/stock-market-today/stock-market-today-sept-15-2026-dow-futures-slide-as-oil-prices-surge-and-treasury-yields-hit-2007-highs",
         title="Stocks sink as Fed meeting begins, Treasury yields hit 19-year highs", date="2026-09-15",
         themes=["rates", "oil"], theme_sentiment={"rates": -50, "oil": 40}, theme_direction={"rates": "up", "oil": "up"},
         sentiment=-45, impact=70, novelty=50, horizon="short", event_type="macro",
         reason="FOMC 첫날 유가 급등·금리 19년 최고에 주가 하락."),
    dict(url="https://www.cnbc.com/2026/09/15/oil-us-treasurys-stocks-pressure.html",
         title="Oil and 10-year Treasury yields move in near lockstep, strongest correlation since 2019", date="2026-09-15",
         themes=["oil", "rates", "inflation"], theme_sentiment={"oil": 45, "rates": -45, "inflation": 40},
         theme_direction={"oil": "up", "rates": "up", "inflation": "up"},
         sentiment=-45, impact=75, novelty=70, horizon="medium", event_type="macro",
         reason="유가와 10년물 금리 상관이 2019년 이후 최강. 유가발 인플레 우려가 금리를 민다."),
    dict(url="https://www.litefinance.org/blog/analysts-opinions/oil-price-prediction-forecast/brent-rises-as-diesel-crunch-tightens-market-forecast-as-of-15092026/",
         title="Brent rises as diesel crunch tightens market — Saudi East-West pipeline offline, Libya force majeure risk", date="2026-09-15",
         themes=["oil", "geopolitical_risk", "energy"], theme_sentiment={"oil": 45, "geopolitical_risk": 40, "energy": 30},
         theme_direction={"oil": "up", "geopolitical_risk": "up", "energy": "up"},
         sentiment=-30, impact=55, novelty=55, horizon="medium", event_type="geopolitical",
         reason="사우디 동서 파이프라인 가동 중단, 리비아 생산 차질, 디젤 공급 부족으로 브렌트 4개월 최고."),
    dict(url="https://achieverfx.com/fomc-september-2026-preview.html",
         title="FOMC September 2026 Preview: Fed Poised to Hike as Oil Reignites Inflation", date="2026-09-15",
         themes=["rates", "inflation", "oil"], theme_sentiment={"rates": -40, "inflation": 40, "oil": 20},
         theme_direction={"rates": "up", "inflation": "up", "oil": "up"},
         sentiment=-35, impact=60, novelty=45, horizon="short", event_type="policy",
         reason="8월 PPI +5.4%, 고용 +16.2만, 브렌트 107달러가 6주 만에 기본 시나리오를 동결에서 인상으로 바꿈. 시장 반영 88%."),
    dict(url="https://www.investing.com/news/stock-market-news/ai-chip-selloff-overblown-zero-gpu-slowdown-after-anthropic-essay-analyst-says-4901426",
         title="AI chip sell-off overblown: Zero GPU slowdown after Anthropic essay, analyst says", date="2026-09-15",
         themes=["ai", "semiconductor"], theme_sentiment={"ai": 30, "semiconductor": 35}, theme_direction={"ai": "up", "semiconductor": "up"},
         sentiment=30, impact=55, novelty=55, horizon="medium", event_type="other",
         reason="공급망에서 GPU 주문 둔화 증거가 전혀 없다는 애널리스트 반박."),
    dict(url="https://invezz.com/news/2026/09/15/ai-development-slowdown-what-it-means-for-nvidia-micron-and-other-chip-stocks/",
         title="AI development slowdown: what it means for Nvidia, Micron and other chip stocks", date="2026-09-15",
         themes=["ai", "semiconductor"], theme_sentiment={"ai": -35, "semiconductor": -35}, theme_direction={"ai": "down", "semiconductor": "down"},
         sentiment=-30, impact=50, novelty=40, horizon="medium", event_type="other",
         reason="AI 개발 속도조절이 반도체 주문 사이클에 미칠 영향 분석. 중립~약세."),
    dict(url="https://www.gurufocus.com/news/9080578/chip-stocks-decline-amid-ai-development-concerns",
         title="Chip Stocks Decline Amid AI Development Concerns — Nvidia -3.4%, Broadcom -4.8%, AMD -4.4%", date="2026-09-14",
         themes=["ai", "semiconductor"], theme_sentiment={"ai": -45, "semiconductor": -50}, theme_direction={"ai": "down", "semiconductor": "down"},
         sentiment=-50, impact=65, novelty=50, horizon="short", event_type="other",
         reason="AI 수장들의 속도조절 발언 뒤 반도체 대형주 일제 급락. 엔비디아 시총 1766억달러 증발."),
    dict(url="https://finance.biggo.com/news/94f97d1f-9b60-4796-8aca-b7c4cac40e14",
         title="KOSPI at risk of breaking below 6,600 as foreign and institutional investors stage coordinated 'Sell Korea' — Samsung, SK Hynix plunge", date="2026-09-15",
         themes=["semiconductor", "ai"], theme_sentiment={"semiconductor": -55, "ai": -35}, theme_direction={"semiconductor": "down", "ai": "down"},
         sentiment=-55, impact=60, novelty=50, horizon="short", event_type="other",
         reason="외국인·기관 동반 순매도 4일째, 합계 4조원. 삼성전자·하이닉스 3%대 급락."),
    dict(url="https://tradingeconomics.com/south-korea/stock-market",
         title="KOSPI falls 3.26% to 6,684, third straight loss as AI investment-cycle worries hit chipmakers", date="2026-09-14",
         themes=["semiconductor", "ai"], theme_sentiment={"semiconductor": -50, "ai": -40}, theme_direction={"semiconductor": "down", "ai": "down"},
         sentiment=-50, impact=65, novelty=45, horizon="short", event_type="other",
         reason="하이닉스 -6.35%, 삼성전자 -4.05%. AI 투자 사이클 지속성 우려."),
    dict(url="https://www.cnbc.com/2026/09/15/why-de-dollarization-discussions-are-more-talk-less-action.html",
         title="Why de-dollarization discussions are more talk, less action", date="2026-09-15",
         themes=["usd", "china"], theme_sentiment={"usd": 20, "china": -10}, theme_direction={"usd": "up", "china": "down"},
         sentiment=10, impact=30, novelty=35, horizon="long", event_type="other",
         reason="BRICS 탈달러 논의는 실행이 미미. 달러 기축 지위 유지."),
]
