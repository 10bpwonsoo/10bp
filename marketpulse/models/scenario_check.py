"""
시나리오 점검 — 모의 시나리오의 충격 서명을 실데이터에 대어 본 결과.

모의 탭을 실데이터로 바꾼 것이다. 시나리오의 shocks 는 '마지막 봉의 목표 z' 이고, 실데이터에서는
하루·5일 z 중 같은 방향으로 더 큰 쪽과 비교한다. 예측이 아니라 '지금 시장이 그 그림과 얼마나 닮았나' 다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Base
from .state import StateLabel

RowStatus = Literal["agree", "weak", "oppose", "quiet_ok", "quiet_broken", "missing"]


class ScenarioCheckRow(Base):
    instrument_id: str
    label: str
    expected_z: float = Field(description="시나리오가 가정한 마지막 봉 z")
    actual_z_1d: float | None = None
    actual_z_5d: float | None = None
    #: 비교에 쓴 값 — 같은 방향으로 더 큰 창의 z. 결측이면 None
    used_z: float | None = None
    used_window: int | None = None
    ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="기대 크기 대비 실제 (0~1, 반대 방향은 0)")
    weight: float = Field(ge=0.0)
    status: RowStatus
    #: 시장 층(스냅샷) 밖의 계열 — Investment 층의 대체·종목 z 로 채웠거나, 그것도 없으면 결측.
    #: theme 은 테마 뉴스 톤·가격 점수 조건(−100~+100 단위, z 가 아니다)
    layer: Literal["market", "alternative", "stock", "theme"] = "market"


class ScenarioThemeRef(Base):
    theme_id: str
    name: str
    theme_score: float
    news_sentiment: float | None = None


class ScenarioCheck(Base):
    name: str
    title: str
    description: str = ""
    as_of: datetime
    #: 이 시나리오가 가정하는 판정 라벨 (없는 시나리오도 있다)
    label: StateLabel | None = None
    #: 탭이 앞세우는 판정. rule · fear_greed · semiconductor · calm — 설정(scenario_checks.yaml)에서 온다
    focus: Literal["rule", "oil_regime", "rates_regime", "ai_regime", "ai_regime_full", "fear_greed", "semiconductor", "calm"] = "rule"
    #: focus=rule 일 때 펼쳐 보이는 팩터와 원자재 경로 (설정)
    factor: str | None = None
    commodities: list[str] = Field(default_factory=list)
    match_score: float = Field(ge=0.0, le=100.0, description="가중 일치도 0~100")
    match_label: str
    evaluated: int
    agree: int
    weak: int
    oppose: int
    quiet_ok: int = 0
    quiet_broken: int = 0
    missing: list[str] = Field(default_factory=list)
    rows: list[ScenarioCheckRow] = Field(default_factory=list)
    #: 판정 엔진 쪽 — 그 라벨의 가설 점수와 require 룰 상태
    hypothesis_score: float | None = None
    require_expression: str | None = None
    require_passed: bool | None = None
    require_observed: float | None = None
    current_label: StateLabel
    current_confidence: float
    themes: list[ScenarioThemeRef] = Field(default_factory=list)
    verdict: str
    note: str
