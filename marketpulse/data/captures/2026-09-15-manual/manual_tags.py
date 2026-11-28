"""
2026-09-15 기사 60건에 대한 수기 태깅.

API 크레딧 없이 LLM 추출이 무엇을 만드는지 보여주기 위해, 이 세션(Claude)이
직접 기사를 읽고 테마·감성·방향을 분류했다. extractor="manual" 로 정직하게
표시한다 — 자동화된 Anthropic API 호출이 아니다.

theme_sentiment: 호재/악재 (-100~100). theme_direction: 그 값이 오르내리는
방향(up/down/neutral) — 감성과 다른 축이다.
"""

# id -> {themes, theme_sentiment, theme_direction, sentiment, impact, novelty,
#        horizon, event_type, reason}
TAGS = {
    "520bbd1ebdc5900a": dict(  # 원화 강세…은행·항공 방긋 자동차·식품 울상
        themes=["usd"], theme_sentiment={"usd": 10}, theme_direction={"usd": "down"},
        sentiment=5, impact=45, novelty=55, horizon="short", event_type="macro",
        reason="원화 강세(달러 약세 방향)가 업종별로 엇갈린 영향을 준다는 기사."),
    "fb5dfe45f66a9da8": dict(  # US futures flat, AI slowdown, Fed
        themes=["ai"], theme_sentiment={"ai": -20}, theme_direction={"ai": "down"},
        sentiment=-15, impact=55, novelty=50, horizon="short", event_type="macro",
        reason="AI 개발 속도 둔화 우려와 Fed 경계감이 뒤섞인 선물시장 기사."),
    "722b53aeeb2efe96": dict(  # 자사주 매입
        themes=["shareholder_return"], theme_sentiment={"shareholder_return": 45}, theme_direction={"shareholder_return": "up"},
        sentiment=35, impact=20, novelty=60, horizon="short", event_type="other",
        reason="경영진 자사주 매입은 주주환원 테마에 명확한 호재."),
    "9fd74282e37c17dc": dict(  # 美 3년만 금리인상…고유가·10년물 5%
        themes=["rates", "oil"], theme_sentiment={"rates": -60, "oil": -50},
        theme_direction={"rates": "up", "oil": "up"},
        sentiment=-55, impact=85, novelty=80, horizon="short", event_type="policy",
        reason="3년 만의 금리 인상 가능성과 고유가·10년물 5% 돌파 압박을 동시에 다룬 핵심 매크로 기사."),
    "f4452331125dc1f6": dict(  # 하이닉스 팔아라 경고 BNK, 삼성전자도 눈높이 낮춰
        themes=["semiconductor"], theme_sentiment={"semiconductor": -60}, theme_direction={"semiconductor": "down"},
        sentiment=-55, impact=60, novelty=65, horizon="short", event_type="other",
        reason="증권사가 목표가와 투자의견을 하향한 부정적 리포트."),
    "4b23f516fbdf90a7": dict(  # 삼전닉스 오를 만큼 올랐다 싸늘한 전망
        themes=["semiconductor"], theme_sentiment={"semiconductor": -50}, theme_direction={"semiconductor": "down"},
        sentiment=-45, impact=55, novelty=50, horizon="short", event_type="other",
        reason="증권가의 고점 논란·눈높이 하향 보도."),
    "ce1e78a684b6148b": dict(  # 금리 5%는 호재? 신중하라
        themes=["rates"], theme_sentiment={"rates": -20}, theme_direction={"rates": "up"},
        sentiment=-15, impact=50, novelty=45, horizon="short", event_type="policy",
        reason="금리 5% 국면에서 신중론을 제기하는 칼럼."),
    "917cc8eb26febe54": dict(  # SK이노베이션 영업익 대비 저렴 목표가↑
        themes=["energy"], theme_sentiment={"energy": 40}, theme_direction={"energy": "up"},
        sentiment=35, impact=25, novelty=55, horizon="medium", event_type="earnings",
        reason="목표가 상향 리포트, 에너지 관련 종목에 긍정적."),
    "82ca6670acf286be": dict(  # Stocks fall as oil and bond yields rise
        themes=["oil", "rates"], theme_sentiment={"oil": -50, "rates": -40},
        theme_direction={"oil": "up", "rates": "up"},
        sentiment=-50, impact=75, novelty=70, horizon="short", event_type="macro",
        reason="유가·채권금리 동반 상승이 주가 하락을 이끈 해외 매크로 기사."),
    "c6235d5bc0e60b07": dict(  # 금리·유가 상승에 AI 속도조절론까지 SK하닉 ADR -7.6%
        themes=["rates", "oil", "ai", "semiconductor"],
        theme_sentiment={"rates": -60, "oil": -60, "ai": -50, "semiconductor": -75},
        theme_direction={"rates": "up", "oil": "up", "ai": "down", "semiconductor": "down"},
        sentiment=-70, impact=90, novelty=85, horizon="intraday", event_type="macro",
        reason="금리·유가 상승과 AI 속도조절론이 겹쳐 SK하이닉스 ADR 급락 — 오늘 흐름을 요약하는 핵심 기사."),
    "9e3dba9e852e9af1": dict(  # Canada 10Y yield rises, inflation, oil
        themes=["rates", "oil", "inflation"], theme_sentiment={"rates": -35, "oil": -25, "inflation": -30},
        theme_direction={"rates": "up", "oil": "up", "inflation": "up"},
        sentiment=-30, impact=35, novelty=45, horizon="short", event_type="macro",
        reason="캐나다 채권시장의 인플레이션·유가 경계 기사, 글로벌 금리 흐름과 같은 맥락."),
    "e9ce86c6fe0bc70e": dict(  # BAE Systems $818M Army contract
        themes=["defense"], theme_sentiment={"defense": 45}, theme_direction={"defense": "up"},
        sentiment=40, impact=30, novelty=50, horizon="medium", event_type="supply",
        reason="미 육군과의 대형 계약 수정, 방산 업체 호재."),
    "6d1cc31de7023a9f": dict(  # Northrop Grumman $34M Navy contract
        themes=["defense"], theme_sentiment={"defense": 25}, theme_direction={"defense": "up"},
        sentiment=20, impact=15, novelty=40, horizon="medium", event_type="supply",
        reason="해군 소규모 계약, 방산 테마에 완만한 호재."),
    "085aba8bb284a9d6": dict(  # AI 다음 타자 젠슨 황이 콕 찍어 25% 급등
        themes=["ai"], theme_sentiment={"ai": 55}, theme_direction={"ai": "up"},
        sentiment=50, impact=35, novelty=70, horizon="short", event_type="other",
        reason="엔비디아 CEO 언급으로 개별 종목 급등, AI 테마 낙관 심리 보강."),
    "558ea849cf90213b": dict(  # Warsh, Fed 금리인상 앞두고 표대결
        themes=["rates"], theme_sentiment={"rates": -30}, theme_direction={"rates": "up"},
        sentiment=-25, impact=45, novelty=55, horizon="short", event_type="policy",
        reason="Fed 인선·금리 인상 경계 관련 정책 뉴스."),
    "afe654dbf3a7bee9": dict(  # 금리인상 충격을 노리라고? 9월 조정이 연말 랠리 기회
        themes=["rates"], theme_sentiment={"rates": -25}, theme_direction={"rates": "up"},
        sentiment=-10, impact=40, novelty=40, horizon="medium", event_type="policy",
        reason="금리 충격 우려 속 역발상 매수 시각을 다룬 칼럼."),
    "89dd2981d5aa8574": dict(  # 외국인 하루 3.2조 매도
        themes=["semiconductor", "ai"], theme_sentiment={"semiconductor": -65, "ai": -55},
        theme_direction={"semiconductor": "down", "ai": "down"},
        sentiment=-60, impact=80, novelty=75, horizon="short", event_type="flow",
        reason="하루 3.2조원 규모 외국인 순매도 — 반도체·AI 테마 수급 이탈을 직접 설명하는 기사."),
    "ce5863910d4df6fb": dict(  # 삼성전자 4%·하이닉스 6% 급락…아시아 반도체 직격탄
        themes=["semiconductor", "china"], theme_sentiment={"semiconductor": -80, "china": -30},
        theme_direction={"semiconductor": "down", "china": "down"},
        sentiment=-75, impact=90, novelty=85, horizon="intraday", event_type="other",
        reason="양대 반도체주 동반 급락과 아시아 전반 반도체주 타격을 전하는 헤드라인급 기사."),
    "4582e67ee647c7a4": dict(  # 테라다인 질주
        themes=["semiconductor"], theme_sentiment={"semiconductor": 45}, theme_direction={"semiconductor": "up"},
        sentiment=40, impact=25, novelty=50, horizon="short", event_type="other",
        reason="반도체 검사장비 업체 강세, 반도체 밸류체인 내 부분적 호재."),
    "9e51dd5f79adaa19": dict(  # 원화강세·유가폭등에 車·전기 유틸리티 추풍낙엽
        themes=["usd", "oil", "energy"], theme_sentiment={"usd": -25, "oil": -55, "energy": -35},
        theme_direction={"usd": "down", "oil": "up", "energy": "up"},
        sentiment=-45, impact=55, novelty=55, horizon="short", event_type="macro",
        reason="원화 강세와 유가 폭등이 자동차·유틸리티 업종에 동시 타격을 준 기사."),
    "c314feae7494ec32": dict(  # 국내증시 시총 한달새 270조 증발
        themes=["semiconductor"], theme_sentiment={"semiconductor": -70}, theme_direction={"semiconductor": "down"},
        sentiment=-65, impact=85, novelty=70, horizon="short", event_type="macro",
        reason="한 달 새 시가총액 270조원 증발 — 삼전닉스 부진이 지수 전체를 끌어내린 결과를 요약."),
    "f53c461c7f311ad8": dict(  # 국제유가 100달러 재돌파
        themes=["oil"], theme_sentiment={"oil": -60}, theme_direction={"oil": "up"},
        sentiment=-55, impact=90, novelty=80, horizon="short", event_type="macro",
        reason="국제유가 100달러 재돌파 — 오늘 매크로 흐름의 핵심 헤드라인."),
    "1eba8b4498a7adb9": dict(  # 100달러 돌파한 국제유가 (동일 사건 후속)
        themes=["oil"], theme_sentiment={"oil": -55}, theme_direction={"oil": "up"},
        sentiment=-50, impact=75, novelty=50, horizon="short", event_type="macro",
        reason="유가 100달러 돌파를 다룬 후속 보도, 동일 사건의 반복 확인."),
    "d9a56a03a925403c": dict(  # 코스피 급락, 유가 폭등
        themes=["oil"], theme_sentiment={"oil": -55}, theme_direction={"oil": "up"},
        sentiment=-55, impact=80, novelty=50, horizon="short", event_type="macro",
        reason="코스피 급락과 유가 폭등을 함께 전하는 헤드라인."),
    "ea4dc0c5538af9f5": dict(  # AI 규제 주장 급부상
        themes=["ai"], theme_sentiment={"ai": -40}, theme_direction={"ai": "down"},
        sentiment=-35, impact=55, novelty=60, horizon="medium", event_type="regulation",
        reason="AI 규제 논의 부상 — 투자자 대응을 다룬 규제 리스크 기사."),
    "4d12f7a0d3448e26": dict(  # 삼전닉스 팔고 이것 샀다 외국인 장바구니
        themes=["semiconductor"], theme_sentiment={"semiconductor": -50}, theme_direction={"semiconductor": "down"},
        sentiment=-45, impact=50, novelty=55, horizon="short", event_type="flow",
        reason="외국인이 반도체 대형주를 팔고 다른 종목으로 이동했다는 수급 기사."),
    "42823ede67b99776": dict(  # 전쟁만 끝나면 5000달러…금값 전망
        themes=["geopolitical_risk"], theme_sentiment={"geopolitical_risk": -20},
        theme_direction={"geopolitical_risk": "up"},
        sentiment=-10, impact=35, novelty=40, horizon="long", event_type="geopolitical",
        reason="지정학적 긴장 지속을 전제로 한 금값 전망 기사."),
    "698d2861e91f7aa6": dict(  # 삼전닉스 믿었는데 개미들 허탈
        themes=["semiconductor"], theme_sentiment={"semiconductor": -55}, theme_direction={"semiconductor": "down"},
        sentiment=-50, impact=45, novelty=45, horizon="short", event_type="other",
        reason="개인 투자자 손실을 다룬 후행적 반도체 테마 기사."),
}
