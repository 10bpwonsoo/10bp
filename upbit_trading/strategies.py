"""
매매 전략 모듈 (Trading Strategies)
- 시그널 타입 정의 (Signal, TradeSignal)
- 추상 기본 클래스 (Strategy)
- 구체 전략은 strategy_historical_low.py, strategy_box_range.py에서 구현
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 시그널 정의
# ──────────────────────────────────────────────
class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    """전략이 반환하는 매매 시그널"""
    signal: Signal
    strategy_name: str
    confidence: float = 0.0       # 0.0 ~ 1.0
    reason: str = ""
    metadata: Dict = field(default_factory=dict)


# ──────────────────────────────────────────────
# 추상 기본 클래스
# ──────────────────────────────────────────────
class Strategy(ABC):
    """모든 매매 전략의 기본 클래스"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> TradeSignal:
        """
        OHLCV DataFrame을 받아 매매 시그널을 생성합니다.
        df 컬럼: open, high, low, close, volume (+ 날짜 인덱스)
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}('{self.name}')>"
