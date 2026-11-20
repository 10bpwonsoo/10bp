"""
2026-09-15 01:37 UTC 기준 2차 수기 태깅.

1차(manual_tags.py)의 28건에 새로 들어온 기사와 웹검색(이 세션의 검색 도구)으로
찾은 해외 기사를 더한다. extractor="manual". API 호출 아님.

geopolitical_risk 는 sentiment_polarity=risk 다 — 긴장 고조가 테마를 키우므로
악재일수록 +로 적는다 (rule_extractor 가 사전 값에 하는 것과 같은 부호 규약).
1차에서 -20 으로 적은 것은 이 규약에 어긋나 고쳤다.
"""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-10bp/d1217ff9-9e47-595a-ade2-530a334c6aba/scratchpad")
from manual_tags import TAGS as V1

TAGS = dict(V1)
TAGS["42823ede67b99776"] = dict(V1["42823ede67b99776"], theme_sentiment={"geopolitical_risk": 25})

TAGS.update({
    # ── 새로 들어온 국내 기사 ──
    "aaeb689725de9dad": dict(  # 라이프자산운용, 삼성전자에 우선주 매입·소각 우선해야
        themes=["shareholder_return", "korea_governance"],
        theme_sentiment={"shareholder_return": 40, "korea_governance": 35},
        theme_direction={"shareholder_return": "up", "korea_governance": "up"},
        sentiment=35, impact=40, novelty=65, horizon="medium", event_type="other",
        reason="행동주의 펀드가 삼성전자에 우선주 매입·소각을 요구 — 주주환원·지배구조 압력."),
    "d8f298b1dcf0e4f8": dict(  # SK Hynix squeezed inside Ichimoku cloud
        themes=["semiconductor"], theme_sentiment={"semiconductor": -25}, theme_direction={"semiconductor": "down"},
        sentiment=-20, impact=25, novelty=35, horizon="intraday", event_type="other",
        reason="기술적 분석 기사. 하이닉스가 저항 구간에 갇혔다는 약세 뉘앙스."),
    "1a351d93d819e6f1": dict(  # Global AI stocks fall as industry chiefs call for slowing development
        themes=["ai", "semiconductor"], theme_sentiment={"ai": -60, "semiconductor": -55},
        theme_direction={"ai": "down", "semiconductor": "down"},
        sentiment=-60, impact=85, novelty=80, horizon="short", event_type="other",
        reason="AI 업계 수장들의 개발 속도조절 요구로 전 세계 AI·반도체주 하락."),
    "c2375dbe5a0ed783": dict(  # 시지트로닉스 13% 급등 AI 로봇·드론용 APD
        themes=["ai"], theme_sentiment={"ai": 30}, theme_direction={"ai": "up"},
        sentiment=30, impact=15, novelty=50, horizon="intraday", event_type="other",
        reason="AI 부품 양산 소식으로 소형주 급등. 테마 심리에 소폭 긍정."),
    "7bb9bad5644e8567": dict(  # SK이노베이션 영업익 10조 전망 장초반 강세
        themes=["energy"], theme_sentiment={"energy": 45}, theme_direction={"energy": "up"},
        sentiment=40, impact=30, novelty=50, horizon="short", event_type="earnings",
        reason="고유가 수혜 실적 전망으로 에너지주 강세."),
    "e33ae13ccd564320": dict(  # 삼전닉스 AI 속도조절·미 반도체 삭풍에도 보합권 선방
        themes=["semiconductor", "ai"], theme_sentiment={"semiconductor": 10, "ai": -30},
        theme_direction={"semiconductor": "neutral", "ai": "down"},
        sentiment=-5, impact=55, novelty=60, horizon="intraday", event_type="other",
        reason="미국발 반도체 급락에도 국내 양대 반도체주가 보합 — 하방 경직성. AI 속도조절 우려는 남는다."),
    "2db4ecd894a4938d": dict(  # 미·일 줄줄이 금리 인상? 신흥국 덮친 엔캐리 공포
        themes=["rates", "usd"], theme_sentiment={"rates": -55, "usd": -35},
        theme_direction={"rates": "up", "usd": "up"},
        sentiment=-55, impact=75, novelty=70, horizon="short", event_type="policy",
        reason="미·일 동시 금리 인상 가능성과 엔캐리 청산 공포가 신흥국 자산을 압박."),
    "1c4ea018ab590eb2": dict(  # 박스피 장세…반도체주 비중 50% 지켜야
        themes=["semiconductor"], theme_sentiment={"semiconductor": 20}, theme_direction={"semiconductor": "neutral"},
        sentiment=10, impact=30, novelty=40, horizon="medium", event_type="other",
        reason="조정에도 반도체 비중 유지를 권하는 전략 리포트."),
    "e89628e9fd2c724d": dict(  # 고유가·고금리 덮친 증시…코스피 3일째 하락
        themes=["oil", "rates"], theme_sentiment={"oil": -55, "rates": -50},
        theme_direction={"oil": "up", "rates": "up"},
        sentiment=-55, impact=80, novelty=55, horizon="short", event_type="macro",
        reason="고유가·고금리가 증시를 사흘째 끌어내린 시황."),
    "2be38a19a29116b5": dict(  # 우려가 현실로 3조 던지더니 삼전닉스 와르르
        themes=["semiconductor"], theme_sentiment={"semiconductor": -70}, theme_direction={"semiconductor": "down"},
        sentiment=-65, impact=75, novelty=55, horizon="short", event_type="flow",
        reason="외국인 3조 매도에 반도체 대형주 급락."),
    "d7c886436d2944c0": dict(  # 美 기업에 날아드는 고금리 청구서
        themes=["rates"], theme_sentiment={"rates": -45}, theme_direction={"rates": "up"},
        sentiment=-40, impact=50, novelty=50, horizon="medium", event_type="macro",
        reason="고금리 장기화가 미국 기업 이자부담으로 전이."),
    "6bed506016a0cb57": dict(  # 美 빚 부담 커질수록 금·비트코인 뜬다
        themes=["rates"], theme_sentiment={"rates": -30}, theme_direction={"rates": "up"},
        sentiment=-15, impact=35, novelty=45, horizon="long", event_type="macro",
        reason="미국 부채 부담 확대를 전제로 한 대체자산 전망."),
})

# ── 웹검색으로 찾은 해외 기사. 제목·URL·게시일은 검색 결과의 것이다.
#    시각은 일 단위만 알 수 있어 12:00 UTC 로 둔다 (quality=PARTIAL).
FOREIGN = [
    dict(url="https://www.cnbc.com/2026/09/14/10-year-us-treasury-is-closing-in-on-5percent.html",
         title="10-year Treasury yield hits 5% before reversing as traders await Fed meeting", date="2026-09-14",
         themes=["rates"], theme_sentiment={"rates": -55}, theme_direction={"rates": "up"},
         sentiment=-50, impact=85, novelty=75, horizon="short", event_type="macro",
         reason="10년물 5% 터치 — 2023년 10월 이후 최고. FOMC 앞두고 긴축 경계."),
    dict(url="https://invezz.com/in/news/2026/09/14/us-10-year-yield-tops-5percent-as-markets-price-fed-hike/",
         title="US 10-year yield tops 5% as markets price Fed hike", date="2026-09-14",
         themes=["rates"], theme_sentiment={"rates": -50}, theme_direction={"rates": "up"},
         sentiment=-45, impact=70, novelty=55, horizon="short", event_type="macro",
         reason="시장이 9월 인상을 가격에 반영하며 10년물 5% 돌파."),
    dict(url="https://finance.yahoo.com/economy/policy/articles/fomc-september-2026-odds-rate-201618784.html",
         title="FOMC September 2026 Odds for a Rate Hike Surpass 50%", date="2026-09-12",
         themes=["rates"], theme_sentiment={"rates": -45}, theme_direction={"rates": "up"},
         sentiment=-40, impact=70, novelty=60, horizon="short", event_type="policy",
         reason="FedWatch 기준 9월 25bp 인상 확률이 과반을 넘었다는 보도."),
    dict(url="https://www.chase.com/personal/investments/learning-and-insights/article/september-2026-rate-hike-now-expected-amid-energy-shocks",
         title="Will the Fed Hike Rates in September? A 25-Basis-Point Move Is Now Expected Amid Energy Shocks", date="2026-09-12",
         themes=["rates", "inflation"], theme_sentiment={"rates": -40, "inflation": -40},
         theme_direction={"rates": "up", "inflation": "up"},
         sentiment=-40, impact=60, novelty=50, horizon="short", event_type="policy",
         reason="에너지 충격이 인플레 경로를 악화시켜 9월 인상이 기본 시나리오가 됐다는 분석."),
    dict(url="https://www.cnbc.com/2026/09/10/iran-us-oil-hormuz-supply-trump-military-brent-wti.html",
         title="U.S. crude oil tops $100 again – last seen in May – as market braces for prolonged Iran war", date="2026-09-10",
         themes=["oil", "geopolitical_risk"], theme_sentiment={"oil": -60, "geopolitical_risk": 60},
         theme_direction={"oil": "up", "geopolitical_risk": "up"},
         sentiment=-55, impact=90, novelty=70, horizon="short", event_type="geopolitical",
         reason="WTI 100달러 재돌파. 이란 전쟁 장기화와 호르무즈 차질 우려."),
    dict(url="https://www.cnbc.com/2026/09/09/oil-prices-today-wti-brent-us-iran-hormuz-attacks.html",
         title="Brent crude tops $100 as U.S.-Iran tit-for-tat strikes stoke oil supply worries", date="2026-09-09",
         themes=["oil", "geopolitical_risk"], theme_sentiment={"oil": -55, "geopolitical_risk": 55},
         theme_direction={"oil": "up", "geopolitical_risk": "up"},
         sentiment=-50, impact=85, novelty=60, horizon="short", event_type="geopolitical",
         reason="미·이란 상호 공습으로 브렌트 100달러 돌파."),
    dict(url="https://www.rigzone.com/news/brent_oil_price_breaks_100_per_barrel-09-sep-2026-184570-article/",
         title="Brent Oil Price Breaks $100 Per Barrel", date="2026-09-09",
         themes=["oil"], theme_sentiment={"oil": -45}, theme_direction={"oil": "up"},
         sentiment=-40, impact=65, novelty=45, horizon="short", event_type="supply",
         reason="사우디 송유관 폐쇄 등 공급 차질로 브렌트 100달러 돌파."),
    dict(url="https://www.cnbc.com/2026/09/07/stock-market-today-live-updates.html",
         title="European stocks close mixed and Asia-Pacific markets rise as investors assess renewed Middle East hostilities", date="2026-09-07",
         themes=["geopolitical_risk"], theme_sentiment={"geopolitical_risk": 35}, theme_direction={"geopolitical_risk": "up"},
         sentiment=-15, impact=50, novelty=40, horizon="short", event_type="geopolitical",
         reason="중동 적대행위 재개를 시장이 소화하는 국면."),
    dict(url="https://qz.com/nvidia-chip-stocks-drop-ai-slowdown-safety-091426",
         title="Nvidia, chip stocks fall as AI CEOs call for slowdown", date="2026-09-14",
         themes=["ai", "semiconductor"], theme_sentiment={"ai": -55, "semiconductor": -60},
         theme_direction={"ai": "down", "semiconductor": "down"},
         sentiment=-55, impact=85, novelty=75, horizon="short", event_type="other",
         reason="Anthropic·OpenAI·xAI 수장의 속도조절 발언에 엔비디아·반도체주 하락."),
    dict(url="https://www.investing.com/news/economy-news/ai-warnings-knock-nasdaq-futures-pressure-tech-stocks-4898987",
         title="Wall St falls as AI anxiety batters Nvidia, chipmakers", date="2026-09-14",
         themes=["ai", "semiconductor"], theme_sentiment={"ai": -55, "semiconductor": -60},
         theme_direction={"ai": "down", "semiconductor": "down"},
         sentiment=-55, impact=85, novelty=60, horizon="intraday", event_type="other",
         reason="PHLX 반도체지수 -5.9%. AI 불안이 월가 전반을 눌렀다."),
    dict(url="https://us.cnn.com/2026/09/14/business/ai-stocks-slide-slowdown-development-amodei-altman-intl",
         title="AI stocks slide after top industry CEOs call for slowdown of technology's development", date="2026-09-14",
         themes=["ai"], theme_sentiment={"ai": -50}, theme_direction={"ai": "down"},
         sentiment=-50, impact=80, novelty=65, horizon="short", event_type="other",
         reason="AI 투자 붐에 대한 가장 강한 경고라는 평가."),
    dict(url="https://fortune.com/2026/09/14/ai-slowdown-stocks-nvidia-meta/",
         title="Wall Street's AI doomsday trade is here: chipmakers sink while hyperscalers gain", date="2026-09-14",
         themes=["semiconductor", "ai"], theme_sentiment={"semiconductor": -55, "ai": -20},
         theme_direction={"semiconductor": "down", "ai": "neutral"},
         sentiment=-35, impact=65, novelty=70, horizon="short", event_type="other",
         reason="반도체는 빠지고 하이퍼스케일러는 오르는 차별화 — AI 테마 내부의 분화."),
]
