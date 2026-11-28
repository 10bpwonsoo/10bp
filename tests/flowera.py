"""
수급 신호가 켜져 있던 시절의 설정으로 잠시 되돌리는 도우미.

운영 설정은 2026-09-15 부터 theme.use_flow=false 다. 그래도 요구 7 의 예시
(뉴스·가격 대 수급 괴리)와 수급 경로의 코드는 계속 검증해야 하므로, 그 테스트들은
이 컨텍스트 안에서 돈다. load_scoring() 이 lru_cache 로 같은 dict 를 돌려주므로
그 dict 를 제자리에서 바꿨다가 되돌린다.
"""

from __future__ import annotations

import contextlib
import copy

from marketpulse.config.settings import CONFIG_DIR
from marketpulse.engines.scoring import load_scoring

FLOW_ERA_THEME = {
    "use_flow": True,
    "weights": {
        "price_momentum": 0.30,
        "news_sentiment": 0.25,
        "flow_momentum": 0.20,
        "news_momentum": 0.15,
        "volatility": -0.10,
    },
}


@contextlib.contextmanager
def flow_era():
    # lru_cache 는 load_scoring() / load_scoring(None) / load_scoring(CONFIG_DIR) 을
    # 서로 다른 항목으로 캐시한다. 엔진마다 부르는 모양이 달라 셋 다 바꿔야 한다.
    variants = [load_scoring()["theme"], load_scoring(None)["theme"], load_scoring(CONFIG_DIR)["theme"]]
    saved = [copy.deepcopy(t) for t in variants]
    for t in variants:
        t.update(copy.deepcopy(FLOW_ERA_THEME))
    try:
        yield
    finally:
        for t, s in zip(variants, saved):
            t.clear()
            t.update(s)
