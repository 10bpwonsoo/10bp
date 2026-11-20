"""
2026-10-14 23:32 UTC(10/15 08:32 KST, 한국 개장 전) 기준 13차 수기 태깅. 한국은 10/14 종가, 미국은 10/14 종가(9월 CPI 발표일),
FRED DGS 금리 계열은 10/13, BE10Y·BE5Y 는 10/14 가 마지막. 오늘은 Yahoo 일봉 빈 봉이 없어 보정 없이 그대로 썼다.

RSS 80건 중 테마와 관련 있는 것만 읽고 태깅했다. RSS 본문이 비어 있는 기사는 원문 페이지를 열어 확인한 사실만 reason 에 적었다
(유료·차단으로 본문을 못 읽은 기사는 제목·RSS 요약에서 확인되는 것만). extractor="manual". Anthropic API 호출 아님.

부호 규약: 테마가 강해지는 방향이 +. oil/inflation/rates/usd 는 directional 이라 유가·물가·금리·달러 '상승' 이 direction=up 이고,
sentiment 는 시장 호재/악재다. geopolitical_risk 는 risk polarity — 긴장 고조가 +.

맥락(10/14 한국 → 10/14 미국): 코스피 6,008.81(−0.44%) 6거래일 연속 하락(6일간 약 1,000p) — 장중 +2% 가까이 반등했다가 ASML 실적 뒤 하락 전환,
코스닥 823.88(−1.57%). 미국 9월 CPI 전년 3.7%(예상 3.6%, 전월 3.4%) · 근원 전년 2.6% · 전월 0.3%(모두 예상 상회). FFR 선물 10월 인상 반영 22.1% → 51.5% → 30%대.
다우 −0.09% 51,621.48, S&P −1.11% 7,718.94, 나스닥 −1.88% 26,692.87. 10년물은 장 초반 급등 뒤 안전자산 수요로 반납(오후 5.189%, −2.7bp),
DXY 장중 102.94(18개월 최고). 코어위브 −15.46%(2032년 만기 회사채 수익률 15% 돌파, CDS 사상 최고) — AI 부채 공포가 네오클라우드·반도체로.
미국 대형은행 3분기 FICC 트레이딩 부진(고금리). 앤트로픽 3분기 매출 +45% 약 170억달러, TSMC 6분기 연속 최대 이익 예상.
"""

def T(themes, ts, td, sentiment, impact, novelty, horizon, event_type, reason):
    return dict(themes=themes, theme_sentiment=ts, theme_direction=td, sentiment=sentiment,
                impact=impact, novelty=novelty, horizon=horizon, event_type=event_type, reason=reason)

TAGS = {
    # ── 미국 9월 CPI · 10/14 미국 ──
    "d962b0c6e11d1c3d": T(["inflation", "rates", "usd", "semiconductor", "ai"], {"inflation": 40, "rates": 25, "usd": 20, "semiconductor": -20, "ai": -15},
        {"inflation": "up", "rates": "up", "usd": "up", "semiconductor": "down", "ai": "down"}, -40, 80, 60, "short", "macro",
        "미국 9월 CPI 전년 3.7%(예상 3.6%, 전월 3.4%), 근원 전년 2.6%·전월 0.3% 모두 예상 상회. FFR 선물 10월 인상 반영 22.1% → 51.5% → 오후 30%대. "
        "다우 −0.09%, S&P −1.11% 7,718.94, 나스닥 −1.88% 26,692.87. 10년물 장 초반 급등 뒤 안전자산 수요로 반납(5.189%, −2.7bp), DXY 장중 102.94 18개월 최고."),
    "31d5f4a6f91b9fa3": T(["inflation", "oil"], {"inflation": 35, "oil": 15}, {"inflation": "up", "oil": "up"}, -30, 75, 55, "short", "macro",
        "CNBC: 9월 CPI 전년 3.7% — 휘발유 가격 급등. 다우존스 컨센서스는 전월 +0.6%·전년 +3.6%."),
    "75b063c54568264d": T(["inflation", "rates"], {"inflation": 20, "rates": 10}, {"inflation": "up", "rates": "up"}, -10, 35, 30, "medium", "macro",
        "CNBC: 높은 물가가 미국에서 '생활의 일부' 가 됐다 — 소비자가 고물가를 당연하게 기대하게 될까 연준이 우려(RSS 요약)."),
    "8a9b8ba6155cb10d": T(["ai", "semiconductor", "rates"], {"ai": -35, "semiconductor": -20, "rates": 10}, {"ai": "down", "semiconductor": "down", "rates": "up"}, -40, 65, 60, "short", "flow",
        "코어위브 −15.46% 65.78달러 — 2032년 만기 무담보 회사채 80센트 아래·수익률 15% 돌파, CDS 사상 최고(로이터). 오픈AI 매출 의구심(FT, 9월 말 연환산 약 500억달러)에 "
        "금리 부담이 겹쳐 네오클라우드·반도체 동반 하락."),
    "1d1dd3afc2870f6b": T(["rates"], {"rates": 10}, {"rates": "up"}, -10, 30, 30, "medium", "earnings",
        "미국 대형은행 3분기 — 전년 대비 매출·순이익은 늘었지만 전분기 대비 감소, 고금리로 채권(FICC) 트레이딩 둔화(JP모간 FICC −4%). 씨티 −5.6%·웰스파고 −3.1%."),
    "66fc8ef7853f71e0": T(["ai"], {"ai": 25}, {"ai": "up"}, 15, 40, 50, "medium", "earnings",
        "앤트로픽 3분기 매출 +45% 약 170억달러(제목에서 확인)."),
    "5203c2de4eec1b50": T(["ai", "semiconductor"], {"ai": -10, "semiconductor": -10}, {"ai": "down", "semiconductor": "down"}, -10, 30, 35, "medium", "other",
        "오픈AI 연환산 매출 논란에 이어 앤트로픽 매출 공개를 앞두고 AI 주가가 흔들린다 — 월가의 흐름 변화(해설)."),
    "b9befd9e0df39afe": T(["semiconductor", "ai"], {"semiconductor": 20, "ai": 15}, {"semiconductor": "up", "ai": "up"}, 15, 40, 30, "short", "earnings",
        "TSMC, AI 붐으로 6분기 연속 사상 최대 이익 예상(실적 발표 전 — 제목에서 확인)."),

    # ── 10/14 한국 ──
    "40d0d0677c1f4fdf": T(["semiconductor"], {"semiconductor": -20}, {"semiconductor": "down"}, -20, 55, 40, "short", "flow",
        "10/14 코스피 6,008.81(−0.44%) 6거래일 연속 하락(6일간 약 1,000p) — 반발 매수로 2% 가까이 올랐다가 ASML 실적 뒤 하락 전환, 6천피는 사수."),
    "e8ed514671a691d8": T(["semiconductor", "china", "shareholder_return"], {"semiconductor": -20, "china": 10, "shareholder_return": -10},
        {"semiconductor": "down", "china": "up", "shareholder_return": "down"}, -20, 40, 35, "medium", "flow",
        "글로벌 반도체 하락 속 한국 충격이 유독 큰 이유 — 메모리 두 종목에 시총 절반, 중국 추격 우려 + 외국인 매도, 자사주 매입 종료로 매수 여력 약화."),
    "131f9183c3e4e844": T(["semiconductor"], {"semiconductor": -15}, {"semiconductor": "down"}, -15, 35, 30, "medium", "flow",
        "끝없는 코스피 탈출 — 외국인 올해 200조원 넘게 순매도(제목에서 확인)."),
    "edcafd8553a315c7": T(["semiconductor"], {"semiconductor": -10}, {"semiconductor": "down"}, -10, 25, 30, "medium", "flow",
        "올해 200조 넘게 판 외국인 자금이 브라질로(제목에서 확인)."),
    "a82db49b13ed58be": T(["semiconductor"], {"semiconductor": -15}, {"semiconductor": "down"}, -15, 30, 30, "short", "flow",
        "이대로 가면 6천피 붕괴 — 개인은 물타기 할 돈도 없다(분석, 제목에서 확인)."),
    "1db741149155b7ad": T(["semiconductor"], {"semiconductor": -10}, {"semiconductor": "down"}, -10, 20, 25, "short", "flow",
        "빚내서 SK하이닉스 산 투자자, 두 달 만에 약 600억 손실(제목에서 확인)."),
    "7592ecab643e19fb": T(["semiconductor", "china"], {"semiconductor": 10, "china": 0}, {"semiconductor": "up", "china": "neutral"}, 5, 20, 25, "intraday", "flow",
        "CXMT 쇼크 하루 만에 초고수 태세 전환 — 10/14 오후 삼성전자·SK하이닉스 순매수 1·2위, 소부장은 매도."),
    "8793256671f8821a": T(["semiconductor", "china"], {"semiconductor": -15, "china": 15}, {"semiconductor": "down", "china": "up"}, -15, 20, 25, "medium", "other",
        "CXMT '삼성보다 먼저 4F² D램' 도발에 코스피 무너져 — 피난처 종목 찾기(해설)."),
    "613879de7b27f2e7": T(["korea_governance"], {"korea_governance": -10}, {"korea_governance": "down"}, -15, 25, 25, "medium", "flow",
        "현대차 외국인 14거래일 연속 매도, 넉 달 전 최고가 대비 반토막 — KB증권 목표가 90만 → 70만원."),
    "0de9f17de8b292c2": T(["ai", "semiconductor"], {"ai": 15, "semiconductor": 10}, {"ai": "up", "semiconductor": "up"}, 10, 25, 30, "long", "other",
        "댄 아이브스(웨드부시) 인터뷰: AI 혁명은 10년 이상, 지금 3년차 — 코스피 내년 중반 전고점 회복 가능(의견)."),
    "e503ad938ea0b56f": T(["semiconductor"], {"semiconductor": 10}, {"semiconductor": "up"}, 5, 15, 20, "long", "other",
        "월가 거물 '1년 안에 9천피' — 특정 종목 지목(제목에서 확인, 의견)."),
    "2f13711c58be68ca": T(["geopolitical_risk", "oil"], {"geopolitical_risk": 15, "oil": 10}, {"geopolitical_risk": "up", "oil": "up"}, 5, 25, 25, "short", "flow",
        "증시 급락 속 해운주 급등 — 중동발 지정학 리스크로 글로벌 해상 운임 급등, 3분기 실적 호조 전망."),
    "9a5359435a40af5b": T(["geopolitical_risk"], {"geopolitical_risk": 5}, {"geopolitical_risk": "neutral"}, 0, 15, 20, "short", "flow",
        "팬오션·HMM 수익률 두 배 차이 — 벌크 대 컨테이너(제목에서 확인)."),
    "74209c030884991c": T(["energy"], {"energy": 15}, {"energy": "up"}, 5, 20, 25, "short", "other",
        "알래스카 LNG 투자 기대에 철강주 급등 — 실적·신사업 성과로 선별해야(같은 흐름)."),
    "73029c555171ecca": T(["shareholder_return", "korea_governance"], {"shareholder_return": 15, "korea_governance": 5}, {"shareholder_return": "up", "korea_governance": "neutral"}, 5, 25, 30, "medium", "other",
        "삼성전자 최대 110조 주주환원 계획에 행동주의 펀드(英 팰리서) '우선주부터 매입·소각' 요구."),
    "81bf59c1ac5374e2": T(["shareholder_return"], {"shareholder_return": 20}, {"shareholder_return": "up"}, 10, 20, 25, "medium", "other",
        "에스원, 보유 자사주 11.02% 전량 소각 + 4,500억 추가 공개 매입(소각 예정)."),
    "b708cb78508e5b2b": T(["korea_governance"], {"korea_governance": -5}, {"korea_governance": "neutral"}, -5, 15, 20, "short", "other",
        "'승자의 저주' 걱정에 롯데손보 인수 신한지주 급락(같은 건 — 10/14 보도와 동일)."),
    "c64fb52c5a72db12": T(["shareholder_return"], {"shareholder_return": 5}, {"shareholder_return": "neutral"}, 5, 15, 20, "medium", "other",
        "미국보다 기대수익 높은 일본 증시 주목 — 밸류에이션 매력, 배당·자사주 확대(의견)."),
    "7a1ed7b1b7def115": T(["semiconductor", "ai", "energy"], {"semiconductor": 5, "ai": 5, "energy": 5}, {"semiconductor": "neutral", "ai": "neutral", "energy": "neutral"}, 5, 15, 20, "medium", "other",
        "반도체 소부장·전력 인프라·로봇주 — '천스닥' 기대 이어간다(제목에서 확인)."),
    "a82f0c6e441f6718": T(["ai"], {"ai": 0}, {"ai": "neutral"}, -5, 15, 30, "long", "other",
        "스페이스X, 통신사의 협력자에서 경쟁자로 — 스타십 성공과 통신산업 지각변동(해설)."),
}

FOREIGN: list[dict] = []   # 오늘도 RSS 에 CNBC·Investing 미국 기사가 들어와 웹검색 기사를 따로 붙이지 않았다
