"""
ThermometerEngine — 센티멘트 온도계 (P5).

새 데이터를 쓰지 않는다. 가격 온도는 MarketStateEngine 이 이미 계산한
매크로 factor(z) 를, 뉴스 온도는 SentimentEngine 의 가중 감성을 그대로
쓴다. 이 엔진이 하는 일은 그 둘을 **같은 눈금에 올리고 거리를 재는 것**이다.

    가격 온도 = squash( Σ(sign · w · factor_z) / Σw )      확보된 factor 만
    뉴스 온도 = Σ(w_k · S_k) / Σw_k                         w = 감쇠·영향도·출처
    종합 온도 = 0.6·가격 + 0.4·뉴스                         한쪽 없으면 재정규화

결측은 0 으로 채우지 않는다. 뉴스가 없으면 뉴스 온도는 None 이고 종합은
가격만으로 재며, 그 사실이 note 와 confidence 에 남는다.

모든 숫자는 scoring.yaml 의 thermometer 절에서 온다 (요구 15-9).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

from ..models.common import ScoreBreakdown, ScoreContribution
from ..models.news import NewsEvent
from ..models.state import MarketState
from ..models.thermometer import SentimentThermometer, ThermoComponent
from .factors import QUALITY_CREDIT
from .scoring import Component, load_scoring, renormalized_average, squash, weighted_z
from .sentiment import decay_weight

ENGINE_VERSION = "0.2.0"

#: 매크로 factor 의 한국어 라벨. relationship.MACRO_LABELS 와 같은 표다 —
#: 순환 import 를 피하려고 여기 다시 적는다.
FACTOR_LABELS: dict[str, str] = {
    "Growth": "성장",
    "Inflation": "인플레이션",
    "Rates": "금리",
    "USD": "달러",
    "Liquidity": "유동성",
    "RiskAppetite": "위험선호",
    "Credit": "신용",
    "Volatility": "변동성",
    "China": "중국",
    "KoreaFlow": "한국 수급",
    "KoreaBreadth": "한국 시장폭",
}

#: 뉴스 온도 계산 근거에 남길 기사 수. 전부 남기면 응답이 커진다.
NEWS_BREAKDOWN_LIMIT = 8

_ARROW = {"up": "↑", "down": "↓", "flat": "→"}


def _cfg(config_dir: Path | None) -> dict:
    return load_scoring(config_dir)["thermometer"]


def price_temperature(
    state: MarketState, *, week_ago: bool = False, config_dir: Path | None = None
) -> tuple[float | None, ScoreBreakdown, float]:
    """
    가격 온도. Returns: (온도 또는 None, 근거, 품질 가중 확보율 0~1)

    week_ago 가 참이면 factor 의 1주 전 값(FactorScore.week_ago)으로 같은
    식을 돌린다. 가중치도 부호도 같다 — 잣대가 같아야 옆에 놓을 수 있다.

    확보율은 단순 개수가 아니라 factor 품질을 곱한다. 종목 하나로 만든
    factor(INSUFFICIENT) 는 있어도 없는 것처럼 센다 — 그것이 "RiskAppetite
    가 사실상 VIX 하나" 인 상황을 confidence 에 반영하는 방법이다.
    """
    cfg = _cfg(config_dir)
    components = [
        Component(
            key=str(c["factor"]),
            weight=float(c["weight"]),
            sign=int(c.get("sign", 1)),
            note=f"factor z · sign {int(c.get('sign', 1)):+d}",
        )
        for c in cfg["price_components"]
    ]

    def resolve(name: str) -> float | None:
        fs = state.factors.get(name)
        if fs is None:
            return None
        return fs.week_ago if week_ago else fs.score

    z, breakdown, _ = weighted_z(
        components, resolve, method="thermometer_price_week_ago_v1" if week_ago else "thermometer_price_v1"
    )

    total_w = sum(c.weight for c in components)
    credit = sum(
        c.weight * QUALITY_CREDIT.get(state.factors[c.key].data_quality, 0.0)
        for c in components
        if c.key in state.factors
    )
    coverage = (credit / total_w) if total_w > 0 else 0.0

    if z is None:
        return None, breakdown, coverage
    std = load_scoring(config_dir)["standardize"]
    value = squash(z, scale=float(std["squash_scale"]), divisor=float(std["squash_divisor"]))
    return value, breakdown.model_copy(update={"value": value}), coverage


def news_temperature(
    events: Sequence[NewsEvent], as_of: datetime, *, config_dir: Path | None = None
) -> tuple[float | None, ScoreBreakdown, int]:
    """
    뉴스 온도. Returns: (온도 또는 None, 근거, 쓴 기사 수)

    SentimentEngine.aggregate_sentiment 와 같은 가중이다. 여기서 다시 쓰는
    이유는 기사별 기여도를 근거에 남기기 위해서다 — "뉴스가 +40" 이라는
    숫자 뒤에 어느 기사가 얼마나 밀었는지가 보여야 한다.
    """
    weighted: list[tuple[float, NewsEvent]] = []
    for e in events:
        w = decay_weight(e, as_of, config_dir=config_dir)
        if w > 0:
            weighted.append((w, e))
    if not weighted:
        return None, ScoreBreakdown.build(
            value=0.0, method="thermometer_news_v1", contributions=[], missing_inputs=["news"]
        ), 0

    total = sum(w for w, _ in weighted)
    value = sum(w * e.sentiment for w, e in weighted) / total

    weighted.sort(key=lambda x: -x[0])
    contributions = [
        ScoreContribution(
            key=e.id,
            raw_value=float(e.sentiment),
            normalized=float(e.sentiment),
            weight=w / total,
            contribution=(w / total) * e.sentiment,
            note=e.event[:80],
        )
        for w, e in weighted[:NEWS_BREAKDOWN_LIMIT]
    ]
    breakdown = ScoreBreakdown.build(
        value=value, method="thermometer_news_v1", contributions=contributions
    )
    return value, breakdown, len(weighted)


def _band(value: float | None, cfg: dict) -> tuple[str, str]:
    if value is None:
        return "unknown", "측정 불가"
    for b in cfg["bands"]:
        if value >= float(b["min"]):
            return str(b["id"]), str(b["label"])
    last = cfg["bands"][-1]
    return str(last["id"]), str(last["label"])


def _note(
    composite: float | None,
    price: float | None,
    news: float | None,
    band_label: str,
    gap_flag: str,
    gap_threshold: float,
    n_events: int,
    delta: float | None,
) -> str:
    if composite is None:
        return "가격도 뉴스도 측정되지 않아 온도를 잴 수 없다."
    parts = [f"시장 온도 {composite:+.0f} ({band_label})."]
    if price is not None and news is not None:
        parts.append(f"가격이 말하는 온도 {price:+.0f}, 뉴스가 말하는 온도 {news:+.0f}.")
        if gap_flag == "narrative_hot":
            parts.append(
                f"뉴스가 가격보다 {news - price:.0f} 뜨겁다 — 내러티브가 가격을 앞서 달린다."
            )
        elif gap_flag == "narrative_cold":
            parts.append(
                f"뉴스가 가격보다 {price - news:.0f} 차갑다 — 가격이 내러티브 없이 움직이고 있다."
            )
        else:
            parts.append(f"두 온도의 차이는 {abs(news - price):.0f} 로 임계({gap_threshold:.0f}) 안이다.")
    elif price is not None:
        parts.append(
            f"가격만으로 잰 값이다. 뉴스 온도는 기사가 없어 측정하지 못했다."
        )
    else:
        parts.append(
            f"뉴스 {n_events}건만으로 잰 값이다. 가격 온도는 factor 가 없어 측정하지 못했다."
        )
    if delta is not None:
        parts.append(f"직전 틱 대비 {delta:+.0f}.")
    return " ".join(parts)


def build_components(
    state: MarketState,
    news: float | None,
    news_week_ago: float | None,
    *,
    config_dir: Path | None = None,
) -> list[ThermoComponent]:
    """
    스트립 한 줄씩. factor 는 sign 을 곱해 "뜨거운 쪽이 +" 로 맞춘 뒤 squash.

    결측 factor 도 줄은 남긴다 — 값이 None 인 채로. 화면이 "이 재료는
    없었다" 를 보여야 온도가 무엇으로 만들어졌는지 정직해진다.
    """
    cfg = _cfg(config_dir)
    std = load_scoring(config_dir)["standardize"]
    scale, divisor = float(std["squash_scale"]), float(std["squash_divisor"])

    def sq(z: float | None, sign: int) -> float | None:
        return None if z is None else squash(sign * z, scale=scale, divisor=divisor)

    out: list[ThermoComponent] = []
    for c in cfg["price_components"]:
        key = str(c["factor"])
        sign = int(c.get("sign", 1))
        fs = state.factors.get(key)
        out.append(
            ThermoComponent(
                key=key,
                label=FACTOR_LABELS.get(key, key),
                kind="factor",
                value=sq(fs.score, sign) if fs else None,
                week_ago=sq(fs.week_ago, sign) if fs else None,
                weight=float(c["weight"]),
                sign=sign,
                quality=fs.data_quality.value if fs else None,
                note=(
                    f"factor z × 부호({sign:+d}) 를 squash. 가격 온도 가중 {float(c['weight']):.2f}"
                    if fs
                    else "이 factor 는 계산되지 않았다 — 구성 자산이 없다"
                ),
            )
        )
    blend = cfg["blend"]
    out.append(
        ThermoComponent(
            key="news",
            label="뉴스 감성",
            kind="news",
            value=news,
            week_ago=news_week_ago,
            weight=float(blend["news"]),
            sign=1,
            quality=None,
            note="감쇠·영향도·출처 가중 기사 감성. 1주 전 값은 저장된 스냅샷에서만 온다",
        )
    )
    return out


def compute_thermometer(
    state: MarketState,
    events: Sequence[NewsEvent],
    as_of: datetime,
    *,
    previous: SentimentThermometer | None = None,
    week_ago: SentimentThermometer | None = None,
    config_dir: Path | None = None,
) -> SentimentThermometer:
    """
    previous 는 직전 틱(추세 화살표용), week_ago 는 약 1주 전 저장 스냅샷의
    온도계(뉴스·종합의 1주 전 표식용)다. 가격의 1주 전은 저장 없이 시계열에서
    잰다 — factor 가 이미 5봉 전 값을 들고 있다.
    """
    cfg = _cfg(config_dir)

    price, price_bd, price_cov = price_temperature(state, config_dir=config_dir)
    news, news_bd, n_events = news_temperature(events, as_of, config_dir=config_dir)
    price_week_ago, _, _ = price_temperature(state, week_ago=True, config_dir=config_dir)
    news_week_ago = week_ago.news if week_ago is not None else None
    composite_week_ago = week_ago.composite if week_ago is not None else None
    if week_ago is not None:
        source = "snapshot"
    elif price_week_ago is not None:
        source = "series"
    else:
        source = "none"

    blend = {k: float(v) for k, v in cfg["blend"].items()}
    composite, unknown = renormalized_average({"price": price, "news": news}, blend)
    composite_contribs = [
        ScoreContribution(
            key=k,
            raw_value=v,
            normalized=v,
            weight=blend[k],
            contribution=blend[k] * v,
            note="가격 온도" if k == "price" else "뉴스 온도",
        )
        for k, v in (("price", price), ("news", news))
        if v is not None
    ]
    composite_bd = ScoreBreakdown.build(
        value=composite if composite is not None else 0.0,
        method="thermometer_blend_v1",
        contributions=composite_contribs,
        missing_inputs=unknown,
    )

    gap = (news - price) if (news is not None and price is not None) else None
    threshold = float(cfg["gap_threshold"])
    if gap is None or abs(gap) < threshold:
        gap_flag = "none"
    else:
        gap_flag = "narrative_hot" if gap > 0 else "narrative_cold"

    band_id, band_label = _band(composite, cfg)

    delta: float | None = None
    trend = "flat"
    if previous is not None and previous.composite is not None and composite is not None:
        delta = composite - previous.composite
        min_delta = float(cfg["trend_min_delta"])
        trend = "up" if delta >= min_delta else "down" if delta <= -min_delta else "flat"

    # 신뢰도. 모르는 항목은 빼고 나머지로 재정규화한다.
    saturation = max(1, int(cfg["news_saturation"]))
    agreement = (1.0 - min(1.0, abs(gap) / 200.0)) if gap is not None else None
    conf_parts = {
        "price_coverage": price_cov if price is not None else None,
        "news_sufficiency": min(1.0, n_events / saturation) if news is not None else None,
        "agreement": agreement,
    }
    conf_weights = {k: float(v) for k, v in cfg["confidence"]["weights"].items()}
    conf_value, conf_unknown = renormalized_average(conf_parts, conf_weights)
    conf_bd = ScoreBreakdown.build(
        value=(conf_value or 0.0) * 100.0,
        method="thermometer_confidence_v1",
        contributions=[
            ScoreContribution(
                key=k,
                raw_value=v,
                normalized=v,
                weight=conf_weights[k],
                contribution=conf_weights[k] * v,
                note={
                    "price_coverage": "factor 품질 가중 확보율",
                    "news_sufficiency": f"기사 수 / 포화점 {saturation}",
                    "agreement": "두 온도가 가까울수록 높다",
                }[k],
            )
            for k, v in conf_parts.items()
            if v is not None
        ],
        missing_inputs=conf_unknown,
    )

    return SentimentThermometer(
        as_of=as_of,
        composite=composite,
        price=price,
        news=news,
        gap=gap,
        gap_flag=gap_flag,
        band=band_id,  # type: ignore[arg-type]
        band_label=band_label,
        trend=trend,  # type: ignore[arg-type]
        trend_arrow=_ARROW[trend],
        delta=delta,
        confidence=(conf_value or 0.0) * 100.0 if composite is not None else 0.0,
        composite_breakdown=composite_bd if composite is not None else None,
        price_breakdown=price_bd if price is not None else None,
        news_breakdown=news_bd if news is not None else None,
        confidence_breakdown=conf_bd if composite is not None else None,
        price_week_ago=price_week_ago,
        news_week_ago=news_week_ago,
        composite_week_ago=composite_week_ago,
        week_ago_source=source,  # type: ignore[arg-type]
        week_ago_as_of=week_ago.as_of if week_ago is not None else None,
        components=build_components(state, news, news_week_ago, config_dir=config_dir),
        news_events=n_events,
        llm_events=sum(1 for e in events if e.extractor == "llm"),
        note=_note(composite, price, news, band_label, gap_flag, threshold, n_events, delta),
    )
