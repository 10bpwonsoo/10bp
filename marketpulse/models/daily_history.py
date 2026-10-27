"""
Daily snapshot history (2026-10-07).

History 는 날짜별로 **한 번 저장한 뒤 고정한** 시스템 판단의 기록이다. 오늘의 모델이 과거를 다시 평가한 값이 아니다.
  RECORDED   — 그 날짜 당시 시스템이 실제로 저장한 판정
  BACKFILLED — 당시 snapshot 이 없어서 나중에 현재 모델로 그 날짜(≤ D 데이터)를 1회 복원한 판정
  LIVE       — 오늘, Daily Finalization 전. 장중 바뀔 수 있다
RECORDED 와 BACKFILLED 는 저장 즉시 LOCKED 다. 자동 갱신은 locked snapshot 을 수정하지 못한다(명시적 correction 만, audit trail 남김).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from .common import Base

HistorySource = Literal["RECORDED", "BACKFILLED", "LIVE"]
Finalization = Literal["daily_close", "last_observation", "backfill", "live", "migrated"]


class Correction(Base):
    """예외적 수정의 audit trail. silent overwrite 는 없다."""

    original_value: dict[str, Any]
    corrected_value: dict[str, Any]
    correction_reason: str
    corrected_at: datetime
    corrected_by: str


class DailySnapshot(Base):
    snapshot_date: date
    tab_id: str
    state: str = Field(description="상태 키 — 탭별 taxonomy (예: RISK_ON, GREED, confirmed_risk_on, term_premium, UPCYCLE)")
    state_label: str = ""
    state_label_ko: str = ""
    state_score: float | None = Field(default=None, description="탭의 대표 점수 (시장 종합 온도 · AI 센티먼트 지수 · 지배 driver 점수 …). None 은 못 잰 것")
    confidence: float | None = None
    component_scores: dict[str, float | None] = Field(default_factory=dict, description="구성요소 점수. 결측은 None — 0 으로 채우지 않는다")
    key_drivers: list[str] = Field(default_factory=list)
    data_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    data_asof: datetime | None = Field(default=None, description="계산에 쓴 데이터의 마지막 시각 — snapshot_date 를 넘지 않는다(look-ahead 금지)")
    missing_components: list[str] = Field(default_factory=list)
    history_source: HistorySource
    calculated_at: datetime
    model_version: str = ""
    logic_version: str = ""
    is_final: bool = False
    is_locked: bool = False
    is_backfilled: bool = False
    finalization: Finalization = "live"
    summary: str = ""
    #: 탭별 상세 — 화면이 그날을 다시 그리는 데 필요한 값 전부(예: 시장 판정의 온도·factor·가설, 센티먼트의 구성요소). 같은 snapshot 에서만 읽는다.
    payload: dict[str, Any] = Field(default_factory=dict)
    corrections: list[Correction] = Field(default_factory=list)

    @property
    def key(self) -> tuple[str, date]:
        return self.tab_id, self.snapshot_date


class MergedRow(Base):
    """같은 KST snapshot 날짜로 이어져 daily 화면에서 빠진 저장 행 — 숨긴 것이 아니라 여기 남긴다 (2026-10-21)."""

    storage_date: date = Field(description="저장소 키(as_of 의 UTC 날짜)")
    source: str
    data_asof: datetime | None = None
    market_date: date | None = None
    reason: str = ""


class DailyHistoryPoint(Base):
    """화면용 한 날짜 — snapshot 에서 뽑은 값만. 오늘 데이터로 다시 설명하지 않는다."""

    #: date = KST Daily Snapshot 날짜 (date_basis='kst_snapshot'). 예전 저장본(date_basis='storage_utc')은 저장 키 그대로다
    date: date
    state: str
    label: str
    label_ko: str = ""
    score: float | None = None
    confidence: float | None = None
    source: HistorySource
    calculated_at: datetime
    model_version: str = ""
    logic_version: str = ""
    locked: bool = False
    coverage: float | None = None
    components: dict[str, float | None] = Field(default_factory=dict)
    drivers: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    summary: str = ""
    detail: dict[str, Any] = Field(default_factory=dict, description="탭별 표시용 상세(payload 의 일부)")
    #: ── 날짜 기준 분리 (2026-10-21) ── snapshot 날짜(date) 와 그 snapshot 이 쓴 미국 정규장 날짜를 따로 둔다
    market_date: date | None = Field(default=None, description="data_asof 시점에 이미 끝난 미국 정규장 날짜 (US close 기준)")
    storage_date: date | None = Field(default=None, description="저장소 키 — as_of 의 UTC 날짜")
    data_asof: datetime | None = None
    merged: list[MergedRow] = Field(default_factory=list, description="같은 snapshot 날짜로 이어져 daily 에서 빠진 다른 저장 행")


class DailyHistorySegment(Base):
    state: str
    label: str
    start: date
    end: date
    days: int


class DailyHistoryShare(Base):
    state: str
    label: str
    days: int
    share: float = Field(description="기간 중 일수 비중 % — 확률이 아니다")


class DailyHistoryTransition(Base):
    date: date
    from_state: str
    from_label: str
    to_state: str
    to_label: str


class DailyHistory(Base):
    tab_id: str
    label: str
    label_ko: str = ""
    as_of: datetime
    window_days: int
    points: list[DailyHistoryPoint] = Field(default_factory=list)
    segments: list[DailyHistorySegment] = Field(default_factory=list)
    share: list[DailyHistoryShare] = Field(default_factory=list)
    transitions: list[DailyHistoryTransition] = Field(default_factory=list)
    current_state: str | None = None
    current_label: str | None = None
    current_streak: int = 0
    previous_state: str | None = None
    previous_label: str | None = None
    changes: int = 0
    share_pct: float = 0.0
    score_label: str = ""
    score_range: list[float] = Field(default_factory=lambda: [-100.0, 100.0])
    score_current: float | None = None
    score_change_1w: float | None = None
    palette: dict[str, str] = Field(default_factory=dict, description="state → CSS 색 토큰")
    labels: dict[str, str] = Field(default_factory=dict, description="state → 라벨")
    recorded_days: int = 0
    backfilled_days: int = 0
    live_today: bool = False
    footnote: str = ""
    note: str = ""
    #: storage_utc = 저장 키(UTC 날짜) 그대로 · kst_snapshot = KST Daily Snapshot 날짜 (2026-10-21)
    date_basis: str = "storage_utc"
    #: 장중 LIVE — daily 띠에 넣지 않고 따로 둔다 (daily 값을 덮지 않는다)
    intraday: DailyHistoryPoint | None = None
    gaps: list[date] = Field(default_factory=list, description="창 안에서 저장된 daily snapshot 이 없는 평일 (KST snapshot 날짜)")
