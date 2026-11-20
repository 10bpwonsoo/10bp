"""
신호 백테스트 (설계서 STEP 6.5).

**여기서 백테스트하는 것은 매매 전략이 아니라 신호다.** 이 시스템은 주문을
내지 않는다. 검증할 것은 "Market State 판정과 괴리 신호가 실제로 무언가를
앞섰는가" 다.

  · Risk-Off 판정 뒤 SPX 는 어떻게 되었나
  · PRICE_VS_FLOW 괴리 뒤 가격은 수급을 따라갔나, 수급이 가격을 따라갔나
  · 판정의 confidence 가 높을수록 결과가 좋았나

`upbit_trading/backtester.py::_calculate_metrics` 의 지표를 이식했다.
다만 거래 목록 대신 **신호 목록**을 받고, 자산 곡선 대신 **신호 이후 수익률
분포**를 본다. Sharpe·MDD 같은 이름을 그대로 쓰되 의미가 다르므로
`hit_rate`·`edge` 를 같이 낸다.

pandas 를 쓰지 않는다. 엔진 어디에도 pandas 의존이 없고, 여기만 들이면
데모가 죽을 경로가 하나 는다 (설계서 STEP 7.7).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Sequence

from ..models.market import MarketSeries
from ..models.snapshot import IntelligenceSnapshot

TRADING_DAYS = 252
#: 이보다 표본이 적으면 지표를 내지 않는다. 5건짜리 적중률 60% 는
#: 숫자가 아니라 인상이다.
MIN_SAMPLES = 10

SignalKind = Literal["state", "divergence", "alert"]


@dataclass(frozen=True)
class Signal:
    """평가 대상 신호 하나."""

    as_of: datetime
    kind: SignalKind
    label: str
    #: 이 신호가 무엇을 예상하는가. +1 상승, -1 하락, 0 방향 없음.
    expected_sign: int
    confidence: float = 0.5
    subject: str | None = None


@dataclass(frozen=True)
class Observation:
    """신호 이후 실제로 일어난 일."""

    signal: Signal
    horizon_bars: int
    forward_return: float

    @property
    def hit(self) -> bool:
        """예상 방향과 실제 부호가 같은가. 방향 없는 신호는 적중을 말하지 않는다."""
        if self.signal.expected_sign == 0:
            return False
        return (self.forward_return > 0) == (self.signal.expected_sign > 0)


@dataclass
class Metrics:
    """
    신호 하나의 성적.

    hit_rate 와 edge 를 같이 본다. 적중률만 보면 "작게 자주 맞고 크게 한 번
    틀리는" 신호가 좋아 보인다.
    """

    label: str
    samples: int = 0
    hit_rate: float | None = None
    mean_return: float | None = None
    median_return: float | None = None
    #: 같은 기간 전체 평균 대비 초과분. 이것이 없으면 상승장에서 모든
    #: 강세 신호가 우수해 보인다.
    edge: float | None = None
    sharpe: float | None = None
    max_drawdown: float | None = None
    worst: float | None = None
    best: float | None = None
    note: str = ""

    @property
    def usable(self) -> bool:
        return self.samples >= MIN_SAMPLES


@dataclass
class BacktestReport:
    horizon_bars: int
    baseline_return: float | None = None
    baseline_samples: int = 0
    by_signal: dict[str, Metrics] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def usable(self) -> list[Metrics]:
        return [m for m in self.by_signal.values() if m.usable]


# ── 지표 (upbit_trading/backtester.py::_calculate_metrics 이식) ─────
def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _stdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _median(xs: Sequence[float]) -> float:
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def max_drawdown(returns: Sequence[float]) -> float:
    """
    신호를 순서대로 이어 붙인 누적 곡선의 최대 낙폭.

    원본은 자산 곡선을 받았다. 여기서는 신호별 수익률을 복리로 이어 붙여
    "이 신호만 따라갔다면" 의 곡선을 만든다.
    """
    if not returns:
        return 0.0
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        worst = min(worst, (equity - peak) / peak)
    return worst * 100.0


def summarize(
    label: str, observations: Sequence[Observation], *, baseline: float | None
) -> Metrics:
    """관측 묶음 하나를 지표로."""
    m = Metrics(label=label, samples=len(observations))
    if not observations:
        m.note = "표본 없음"
        return m

    returns = [o.forward_return for o in observations]
    directional = [o for o in observations if o.signal.expected_sign != 0]

    m.mean_return = _mean(returns) * 100.0
    m.median_return = _median(returns) * 100.0
    m.worst = min(returns) * 100.0
    m.best = max(returns) * 100.0
    m.max_drawdown = max_drawdown(returns)

    if directional:
        m.hit_rate = sum(1 for o in directional if o.hit) / len(directional) * 100.0

    if baseline is not None:
        # 방향 신호는 부호를 맞춰서 비교한다. 하락을 예상한 신호가 실제로
        # 내렸다면 그것은 초과 성과다.
        signed = [
            o.forward_return * (o.signal.expected_sign or 1) for o in observations
        ]
        m.edge = (_mean(signed) - baseline * _sign_bias(observations)) * 100.0

    sd = _stdev(returns)
    if sd > 0:
        m.sharpe = _mean(returns) / sd * math.sqrt(TRADING_DAYS)

    if not m.usable:
        m.note = f"표본 {m.samples}건 — {MIN_SAMPLES}건 미만이라 참고용"
    return m


def _sign_bias(observations: Sequence[Observation]) -> float:
    """방향 신호의 평균 부호. 전부 상승 예상이면 1, 반반이면 0 에 가깝다."""
    signs = [o.signal.expected_sign for o in observations if o.signal.expected_sign]
    return _mean([float(s) for s in signs]) if signs else 1.0


# ── 스냅샷 히스토리에서 신호 뽑기 ─────────────────────────────────
#: 상태 판정이 무엇을 예상하는가. 벤치마크(SPX)에 대한 방향이다.
STATE_EXPECTATION: dict[str, int] = {
    "RISK_OFF": -1,
    "RISK_ON": 1,
    "INFLATION_SHOCK": -1,
    "GROWTH_SCARE": -1,
    "LIQUIDITY_SQUEEZE": -1,
    "GOLDILOCKS": 1,
    "NEUTRAL": 0,
}


def _name(value: object) -> str:
    """StrEnum 이든 문자열이든 같은 이름을 낸다. 저장소 왕복 후에도 동작한다."""
    return str(getattr(value, "value", value))


def extract_signals(history: Sequence[IntelligenceSnapshot]) -> list[Signal]:
    """
    스냅샷 히스토리에서 평가 가능한 신호를 뽑는다.

    상태는 **바뀐 순간**만 신호로 본다. 같은 판정이 20틱 이어지는 것을
    20개의 독립 신호로 세면 표본 수가 부풀고 지표가 거짓말을 한다.
    """
    signals: list[Signal] = []
    previous_label: str | None = None

    for snap in history:
        label = _name(snap.market_state.primary_label)
        if label != previous_label:
            signals.append(
                Signal(
                    as_of=snap.as_of,
                    kind="state",
                    label=label,
                    expected_sign=STATE_EXPECTATION.get(label, 0),
                    confidence=snap.market_state.confidence,
                )
            )
            previous_label = label

        for d in snap.divergences:
            # 새로 열린 괴리만 센다. 같은 괴리가 5틱 이어지는 것을 5개의
            # 독립 신호로 세면 표본이 부풀고 지표가 거짓말을 한다.
            if d.duration_periods > 1:
                continue
            signals.append(
                Signal(
                    as_of=snap.as_of,
                    kind="divergence",
                    label=_name(d.type),
                    # 괴리는 어느 쪽으로 수렴할지 말하지 않는다. 방향 없는
                    # 신호다 — 억지로 부호를 붙이면 없는 주장을 만든다.
                    expected_sign=0,
                    confidence=d.severity / 100.0,
                    subject=d.related_theme,
                )
            )
    return signals


def forward_returns(
    series: MarketSeries,
    stamps: Sequence[datetime],
    *,
    horizon_bars: int,
) -> dict[datetime, float]:
    """
    '스냅샷 시각 → 그 이후 horizon_bars 봉 수익률' 맵.

    각 스냅샷 시각에 대해 **그 시각 이하의 마지막 봉**을 찾고, 거기서
    horizon_bars 뒤의 봉과 비교한다. 시각 이후의 봉을 쓰면 판정 시점에
    없던 정보를 쓰는 것이다 — look-ahead 다.

    마지막 horizon_bars 개 스냅샷은 아직 결과가 나오지 않았으므로 맵에
    들어가지 않는다. 그 사실을 0 으로 채우지 않는다.
    """
    bars = sorted(zip(series.timestamps, series.values))
    if len(bars) <= horizon_bars:
        return {}

    out: dict[datetime, float] = {}
    for ts in stamps:
        # 판정 시각 이하의 마지막 봉. bisect 대신 역순 탐색으로 충분하다.
        index = None
        for i in range(len(bars) - 1, -1, -1):
            if bars[i][0] <= ts:
                index = i
                break
        if index is None:
            continue
        target = index + horizon_bars
        if target >= len(bars):
            continue
        entry, exit_ = bars[index][1], bars[target][1]
        if entry == 0:
            continue
        out[ts] = (exit_ - entry) / abs(entry)
    return out


def run_backtest(
    history: Sequence[IntelligenceSnapshot],
    returns_by_time: dict[datetime, float],
    *,
    horizon_bars: int = 5,
) -> BacktestReport:
    """
    히스토리와 '시각 → 이후 수익률' 맵을 받아 신호별 성적을 낸다.

    수익률 맵을 바깥에서 받는 이유는 검증 가능성 때문이다. 벤치마크를
    무엇으로 할지, 수익률을 어떻게 잴지는 분석가의 선택이고 엔진이 몰래
    정할 일이 아니다.
    """
    report = BacktestReport(horizon_bars=horizon_bars)
    if len(history) < MIN_SAMPLES:
        report.warnings.append(
            f"스냅샷 {len(history)}개 — {MIN_SAMPLES}개 미만이라 지표를 내지 않는다"
        )
        return report
    if not returns_by_time:
        report.warnings.append("수익률 데이터가 비어 있다")
        return report

    baseline_values = list(returns_by_time.values())
    report.baseline_return = _mean(baseline_values)
    report.baseline_samples = len(baseline_values)

    grouped: dict[str, list[Observation]] = {}
    unmatched = 0
    for signal in extract_signals(history):
        forward = returns_by_time.get(signal.as_of)
        if forward is None:
            unmatched += 1
            continue
        key = f"{signal.kind}:{signal.label}"
        grouped.setdefault(key, []).append(
            Observation(signal=signal, horizon_bars=horizon_bars, forward_return=forward)
        )

    if unmatched:
        report.warnings.append(
            f"{unmatched}개 신호는 대응하는 수익률이 없어 제외했다"
        )

    report.by_signal = {
        key: summarize(key, obs, baseline=report.baseline_return)
        for key, obs in sorted(grouped.items())
    }
    if not report.usable:
        report.warnings.append(
            f"표본 {MIN_SAMPLES}건을 넘는 신호가 없다. 스케줄러를 더 돌려야 한다"
        )
    return report
