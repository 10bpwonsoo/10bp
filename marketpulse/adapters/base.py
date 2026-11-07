"""
Data Adapter 인터페이스 (요구 3, 12).

데이터 공급자와 분석 로직을 분리한다 (요구 15-5). 엔진은 어댑터를 모르고,
어댑터는 엔진을 모른다. 둘 사이에는 MarketSeries / RawNewsItem 만 오간다.

LIVE / DELAYED / MOCK 전환은 어댑터 교체로만 이뤄진다. 엔진 코드는
MARKETPULSE_DATA_MODE 를 바꿔도 한 줄도 바뀌지 않는다 (요구 15-9).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Sequence

from ..models.common import DataMode
from ..models.market import Instrument, MarketSeries
from ..models.news import RawNewsItem


class AdapterError(RuntimeError):
    """어댑터가 데이터를 가져오지 못했다. 파이프라인은 이것을 삼키고 진행한다."""


class MarketAdapter(ABC):
    """마켓데이터 공급자."""

    #: 이 어댑터가 제공하는 데이터의 모드
    mode: DataMode
    #: 로그와 DataMeta.source 에 쓰일 이름
    name: str

    @abstractmethod
    def fetch_series(
        self,
        instruments: Sequence[Instrument],
        *,
        bars: int,
        as_of: datetime | None = None,
    ) -> dict[str, MarketSeries]:
        """
        요청한 instrument 들의 시계열을 돌려준다.

        일부만 가져와도 된다. 빠진 것은 호출자가 missing 으로 처리하고
        coverage 와 confidence 를 낮춘다. 절대 0 으로 채우지 않는다.
        """

    def supports(self, instrument: Instrument) -> bool:
        """이 어댑터가 해당 instrument 를 다룰 수 있는가."""
        return True


class NewsAdapter(ABC):
    """뉴스 공급자."""

    mode: DataMode
    name: str

    @abstractmethod
    def fetch_news(
        self, *, limit: int = 100, as_of: datetime | None = None
    ) -> list[RawNewsItem]:
        """최신 기사부터 돌려준다."""
