"""
ThemeEngine (설계서 STEP 5.7).

    ThemeScore = 100 · tanh( Σ(w_c · z_c/2) / Σ|w_c| )

가중치 설계의 요지: price_momentum 이 가장 크다(0.30). 가격은 유일하게
조작할 수 없는 실제 체결 정보이고, 뉴스는 후행하거나 과장될 수 있다.
news_sentiment 를 가격보다 낮게 둔 것은 이 시스템의 입장 때문이다 —
"뉴스가 시장을 움직인다" 가 아니라 "시장이 뉴스를 검증한다".

news_sentiment 와 price_momentum 이 재는 것이 다르다는 점이 중요하다.
  · news_sentiment  = 그 테마를 둘러싼 **내러티브의 톤**
  · price_momentum  = 시장이 **실제로 한 일**
둘의 불일치는 오류가 아니라 신호다. 그것을 잡아내는 것이 P2 의
DivergenceEngine 이고, 요구 1 의 네 번째 질문이 바로 그것이다.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from ..models.common import ScoreBreakdown, ScoreContribution
from ..models.market import AssetClass, Instrument, MarketSnapshot
from ..models.news import NewsEvent
from ..models.theme import (
    Confirmation,
    DataQualityBand,
    Theme,
    ThemeInstrument,
    ThemeState,
)
from .scoring import Component, load_scoring, squash, unsquash, weighted_z, renormalized_average
from .sentiment import aggregate_sentiment, news_momentum

ENGINE_VERSION = "0.1.0"


# ──────────────────────────────────────────────────────────
# 시장 측 구성요소
# ──────────────────────────────────────────────────────────
def _partition(
    mapping: Sequence[ThemeInstrument], by_id: Mapping[str, Instrument]
) -> tuple[list[ThemeInstrument], list[ThemeInstrument]]:
    """가격 자산과 수급 자산을 가른다. 둘은 다른 축이라 섞지 않는다."""
    price: list[ThemeInstrument] = []
    flow: list[ThemeInstrument] = []
    for ti in mapping:
        ins = by_id.get(ti.instrument_id)
        if ins is None:
            continue
        (flow if ins.asset_class is AssetClass.FLOW else price).append(ti)
    return price, flow


def _momentum(
    mapping: Sequence[ThemeInstrument],
    snapshot: MarketSnapshot,
    *,
    method: str,
    horizon: str = "1d",
) -> tuple[float | None, ScoreBreakdown, float]:
    components = [
        Component(key=ti.instrument_id, weight=ti.weight, sign=ti.direction)
        for ti in mapping
    ]
    if not components:
        return None, ScoreBreakdown.build(value=0.0, method=method, contributions=[]), 0.0
    return weighted_z(
        components,
        lambda iid: snapshot.z(iid, horizon),
        method=method,
        raw=lambda iid: (
            snapshot.features[iid].ret_1d if iid in snapshot.features else None
        ),
    )


def _vol_baselines(snapshot: MarketSnapshot, by_id: Mapping[str, Instrument]) -> dict[AssetClass, tuple[float, float]]:
    """
    자산군별 realized vol 의 평균·표준편차.

    주식 변동성과 금리 변동성은 단위가 달라 그대로 비교할 수 없다. 같은
    자산군 안에서 횡단면 표준화해야 "이 테마의 자산들이 평소보다 요동친다"
    를 말할 수 있다.
    """
    buckets: dict[AssetClass, list[float]] = defaultdict(list)
    for iid, feat in snapshot.features.items():
        ins = by_id.get(iid)
        if ins is None or feat.realized_vol_20d is None:
            continue
        buckets[ins.asset_class].append(feat.realized_vol_20d)

    out: dict[AssetClass, tuple[float, float]] = {}
    for cls, values in buckets.items():
        if len(values) < 2:
            continue
        sd = statistics.stdev(values)
        if sd > 0:
            out[cls] = (statistics.fmean(values), sd)
    return out


def _volatility(
    mapping: Sequence[ThemeInstrument],
    snapshot: MarketSnapshot,
    by_id: Mapping[str, Instrument],
    baselines: Mapping[AssetClass, tuple[float, float]],
) -> tuple[float | None, list[ScoreContribution]]:
    """테마 구성 자산의 변동성을 자산군 내 횡단면 z 로 환산해 가중 평균."""
    total = 0.0
    acc = 0.0
    contributions: list[ScoreContribution] = []
    for ti in mapping:
        ins = by_id.get(ti.instrument_id)
        feat = snapshot.features.get(ti.instrument_id)
        if ins is None or feat is None or feat.realized_vol_20d is None:
            continue
        base = baselines.get(ins.asset_class)
        if base is None:
            continue
        mu, sd = base
        z = (feat.realized_vol_20d - mu) / sd
        acc += ti.weight * z
        total += ti.weight
        contributions.append(
            ScoreContribution(
                key=ti.instrument_id,
                raw_value=feat.realized_vol_20d,
                normalized=z,
                weight=ti.weight,
                contribution=ti.weight * z,
                note=f"{ins.asset_class.value} 자산군 내 횡단면 z",
            )
        )
    return (acc / total if total > 0 else None), contributions


# ──────────────────────────────────────────────────────────
# 뉴스 측 구성요소
# ──────────────────────────────────────────────────────────
def _theme_events(events: Sequence[NewsEvent], theme_id: str) -> list[NewsEvent]:
    return [e for e in events if theme_id in e.themes]


def _theme_sentiment(events: Sequence[NewsEvent], theme_id: str, as_of: datetime, *, config_dir: Path | None) -> tuple[float, float]:
    """테마별 감성이 있으면 그것을, 없으면 기사 전체 감성을 쓴다."""
    scoped = [
        e.model_copy(update={"sentiment": e.theme_sentiment[theme_id]})
        if theme_id in e.theme_sentiment
        else e
        for e in events
    ]
    return aggregate_sentiment(scoped, as_of, config_dir=config_dir)


def cross_sectional_news_volume(counts: Mapping[str, int]) -> dict[str, float | None]:
    """
    테마별 기사 수를 다른 테마들과 비교해 표준화한다.

    설계서의 정의는 시계열 z(최근 3시간 vs 직전 7일 같은 시간대)다. 그것을
    쓰려면 뉴스 히스토리가 있어야 하는데 P1 의 MOCK 에는 없다. 그래서
    **지금은 횡단면 z** 를 쓴다 — "이 테마가 지금 다른 테마들보다 유별나게
    많이 언급되고 있는가". 다른 지표이므로 breakdown 의 method 에 그 사실을
    남긴다. 시계열 버전은 히스토리가 붙는 P4 에서 교체한다.
    """
    values = list(counts.values())
    if len(values) < 2:
        return {k: None for k in counts}
    mu = statistics.fmean(values)
    sd = statistics.stdev(values)
    if sd <= 0:
        return {k: 0.0 for k in counts}
    return {k: (v - mu) / sd for k, v in counts.items()}


# ──────────────────────────────────────────────────────────
# 합성
# ──────────────────────────────────────────────────────────
def _confirmation(
    signals: Mapping[str, float | None], cfg: dict
) -> tuple[float | None, Confirmation]:
    """news / price / flow 세 신호의 방향 합의."""
    threshold = float(cfg["signal_min_abs"])
    valid = [v for v in signals.values() if v is not None and abs(v) >= threshold]
    if len(valid) < 2:
        return None, Confirmation.LOW

    positives = sum(1 for v in valid if v > 0)
    negatives = len(valid) - positives
    majority = max(positives, negatives)
    minority = min(positives, negatives)
    score = 100.0 * (majority - minority) / len(valid)
    # 다수 방향이 음수면 부호까지 뒤집지는 않는다. 합의 '정도' 를 잰다.

    if score >= cfg["high"]:
        band = Confirmation.HIGH
    elif score >= cfg["medium"]:
        band = Confirmation.MEDIUM
    elif score >= cfg["low"]:
        band = Confirmation.LOW
    else:
        band = Confirmation.CONFLICT
    return score, band


def compute_theme_states(
    themes: Sequence[Theme],
    snapshot: MarketSnapshot,
    events: Sequence[NewsEvent],
    instruments_by_id: Mapping[str, Instrument],
    *,
    previous: Mapping[str, ThemeState] | None = None,
    history: Mapping[str, Sequence[float]] | None = None,
    config_dir: Path | None = None,
    horizon: str = "1d",
) -> list[ThemeState]:
    """순수 함수. 테마별 상태를 계산한다."""
    scoring = load_scoring(config_dir)
    tcfg = scoring["theme"]
    weights: dict[str, float] = dict(tcfg["weights"])
    sq = scoring["standardize"]
    scale, divisor = float(sq["squash_scale"]), float(sq["squash_divisor"])

    baselines = _vol_baselines(snapshot, instruments_by_id)
    counts = {t.id: len(_theme_events(events, t.id)) for t in themes}
    volume_z = cross_sectional_news_volume(counts)

    out: list[ThemeState] = []
    for theme in themes:
        theme_events = _theme_events(events, theme.id)
        price_map, flow_map = _partition(theme.instruments, instruments_by_id)
        # 수급 신호를 끈 상태(scoring.yaml theme.use_flow=false)에서는 수급 자산을
        # 애초에 매핑하지 않은 것으로 본다 — 점수·확인·커버리지 어디에도 들어가지
        # 않고, 결손이 아니라 구조적 부재로 기록된다.
        if not tcfg.get("use_flow", True):
            flow_map = {}

        price_z, price_bd, price_cov = _momentum(
            price_map, snapshot, method="theme_price_weighted_z_v1", horizon=horizon
        )
        flow_z, flow_bd, flow_cov = _momentum(
            flow_map, snapshot, method="theme_flow_weighted_z_v1", horizon=horizon
        )
        vol_z, vol_contribs = _volatility(price_map, snapshot, instruments_by_id, baselines)

        sentiment_value, sentiment_weight = _theme_sentiment(
            theme_events, theme.id, snapshot.as_of, config_dir=config_dir
        )
        sentiment_display = sentiment_value if sentiment_weight > 0 else None
        momentum_display = news_momentum(
            theme_events, snapshot.as_of, config_dir=config_dir
        )

        # 모든 구성요소를 z 단위로 맞춘다. 감성/모멘텀은 이미 -100~100 이라
        # squash 의 역함수로 z 로 되돌린다.
        z_parts: dict[str, float | None] = {
            "price_momentum": price_z,
            "flow_momentum": flow_z,
            "volatility": vol_z,
            "news_sentiment": (
                None if sentiment_display is None
                else unsquash(sentiment_display, scale=scale, divisor=divisor)
            ),
            "news_momentum": (
                None if momentum_display is None
                else unsquash(momentum_display, scale=scale, divisor=divisor)
            ),
        }

        contributions: list[ScoreContribution] = []
        missing: list[str] = []
        acc = 0.0
        weight_sum = 0.0
        for name, w in weights.items():
            z = z_parts.get(name)
            if z is None:
                missing.append(name)
                continue
            acc += w * (z / divisor)
            weight_sum += abs(w)
            contributions.append(
                ScoreContribution(
                    key=name,
                    normalized=z,
                    weight=w,
                    contribution=w * (z / divisor),
                    note=_COMPONENT_NOTES[name],
                )
            )

        theme_score = scale * math.tanh(acc / weight_sum) if weight_sum > 0 else 0.0
        breakdown = ScoreBreakdown.build(
            value=theme_score,
            method="theme_weighted_tanh_v1",
            contributions=contributions,
            missing_inputs=missing,
        )

        display = {
            name: (
                None if z_parts[name] is None
                else squash(z_parts[name], scale=scale, divisor=divisor)  # type: ignore[arg-type]
            )
            for name in weights
        }
        confirm_score, confirm_band = _confirmation(
            {
                "news_sentiment": display["news_sentiment"],
                "price_momentum": display["price_momentum"],
                "flow_momentum": display["flow_momentum"],
            },
            tcfg["confirmation"],
        )

        # 구성요소가 빠진 이유를 구분한다.
        #   구조적 부재 : 그 테마에 애초에 그 종류의 자산을 매핑하지 않았다.
        #                 Defense 테마에 수급 자산이 없는 것은 결손이 아니다.
        #   실제 결손   : 매핑은 했는데 데이터를 못 가져왔다.
        structural = {"news_sentiment", "news_momentum"} if not theme_events else set()
        if not flow_map:
            structural.add("flow_momentum")
        if not price_map:
            structural.add("volatility")
        coverage = _coverage(price_cov, flow_cov, bool(flow_map))
        quality = _quality(coverage, missing, structural)

        confidence_bd = _confidence(
            confirm_score,
            coverage,
            len(theme_events),
            history.get(theme.id) if history else None,
            cfg=tcfg["confidence"],
        )

        prev = previous.get(theme.id) if previous else None
        out.append(
            ThemeState(
                theme_id=theme.id,
                name=theme.name,
                as_of=snapshot.as_of,
                theme_score=theme_score,
                breakdown=breakdown,
                news_sentiment=display["news_sentiment"],
                news_volume=(
                    squash(volume_z[theme.id], scale=scale, divisor=divisor)
                    if volume_z.get(theme.id) is not None
                    else None
                ),
                news_momentum=display["news_momentum"],
                price_momentum=display["price_momentum"],
                flow_momentum=display["flow_momentum"],
                volatility=display["volatility"],
                cross_asset_confirmation=confirm_band,
                confirmation_score=confirm_score,
                confidence=max(0.0, min(100.0, confidence_bd.value)),
                confidence_breakdown=confidence_bd,
                last_change=(theme_score - prev.theme_score) if prev else 0.0,
                last_change_window="1tick",
                supporting_events=[e.id for e in theme_events],
                supporting_instruments=[ti.instrument_id for ti in theme.instruments],
                data_quality=quality,
            )
        )

    out.sort(key=lambda t: t.theme_score, reverse=True)
    return out


_COMPONENT_NOTES = {
    "price_momentum": "테마 구성 자산의 부호 가중 z. 시장이 실제로 한 일",
    "news_sentiment": "시간 감쇠 가중 감성. 내러티브의 톤",
    "flow_momentum": "수급 자산의 부호 가중 z",
    "news_momentum": "최근 구간과 직전 구간의 감성 차이",
    "volatility": "자산군 내 횡단면 변동성 z. 음수 가중이다",
}


def _quality(
    coverage: float, missing: Sequence[str], structural: set[str]
) -> DataQualityBand:
    """
    데이터 품질.

    구조적으로 부재하는 구성요소는 감점하지 않는다. Defense 테마에 수급
    자산을 매핑하지 않은 것은 데이터 결손이 아니라 모델링 선택이다. 그것을
    PARTIAL 로 표시하면 진짜 결손이 묻힌다.

    실제 결손(매핑은 했는데 데이터를 못 가져온 경우)만 등급을 낮춘다.
    """
    real_gaps = [m for m in missing if m not in structural]
    if coverage < 0.4:
        return DataQualityBand.INSUFFICIENT
    if coverage >= 0.75 and not real_gaps:
        return DataQualityBand.OK
    return DataQualityBand.PARTIAL


def _coverage(price_cov: float, flow_cov: float, has_flow: bool) -> float:
    return (price_cov + flow_cov) / 2.0 if has_flow else price_cov


def _confidence(
    confirmation: float | None,
    coverage: float,
    event_count: int,
    score_history: Sequence[float] | None,
    *,
    cfg: dict,
) -> ScoreBreakdown:
    """
    Theme Confidence (설계서 STEP 5.7).

    NewsSufficiency 가 왜 필요한가: 기사 1건으로 만든 +78 과 20건으로 만든
    +78 은 같은 확신도가 아니다. 전자는 한 기자의 의견이고 후자는 시장의
    관심이다.
    """
    weights: dict[str, float] = dict(cfg["weights"])
    saturation = int(cfg["news_sufficiency_saturation"])
    stdev_sat = float(cfg["stability_stdev_saturation"])

    stability: float | None = None
    if score_history and len(score_history) >= 2:
        stability = 1.0 - min(1.0, statistics.stdev(score_history) / stdev_sat)

    parts: dict[str, float | None] = {
        "confirmation": None if confirmation is None else (confirmation + 100.0) / 200.0,
        "coverage": coverage,
        "news_sufficiency": min(1.0, event_count / saturation),
        "stability": stability,
    }
    value, unknown = renormalized_average(parts, weights)

    contributions = [
        ScoreContribution(
            key=k,
            normalized=parts[k],  # type: ignore[arg-type]
            weight=weights[k],
            contribution=weights[k] * parts[k],  # type: ignore[operator]
            note=_CONF_NOTES[k],
        )
        for k in weights
        if parts.get(k) is not None
    ]
    return ScoreBreakdown.build(
        value=100.0 * (value or 0.0),
        method="theme_confidence_v1",
        contributions=contributions,
        missing_inputs=unknown,
    )


_CONF_NOTES = {
    "confirmation": "뉴스·가격·수급이 같은 방향을 가리키는가",
    "coverage": "테마 구성 자산 중 데이터가 확보된 비중",
    "news_sufficiency": "기사 1건과 20건은 같은 확신도가 아니다",
    "stability": "최근 틱들에서 점수가 얼마나 안정적이었는가",
}
