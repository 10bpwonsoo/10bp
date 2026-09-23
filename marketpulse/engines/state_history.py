"""
Market State 히스토리 재생 (2026-09-23 신설).

기존 엔진을 한 줄도 바꾸지 않는다. 시계열을 날짜별로 잘라
normalize.build_snapshot → market_state.compute_market_state → thermometer.price_temperature
를 그대로 다시 부른다. 그래서 히스토리의 어느 날을 골라도 그날 화면이 보여줬을
판정과 같다 (previous_label 을 전날 재생값으로 넘겨 지속성 항도 같은 식이다).

비용: 하루 재생 ≈ build_snapshot(상관 없이) + 판정. 22일이면 몇 초라
스냅샷에 넣지 않고 별도 엔드포인트에서 캐시한다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

from ..models.common import DataMode
from ..models.market import Instrument, MarketSeries
from ..models.state import StateLabel
from ..models.state_history import MarketStateHistory, StateHistoryPoint, StateSegment
from .calendar import event_window
from .market_state import compute_market_state
from .normalize import build_snapshot
from .thermometer import compute_thermometer
from ..models.news import NewsEvent

logger = logging.getLogger(__name__)

ENGINE_VERSION = "0.1.0"

LABEL_KO = {
    "RISK_ON": "Risk-On", "RISK_OFF": "Risk-Off", "GROWTH_SHOCK": "Growth Shock",
    "INFLATION_SHOCK": "Inflation Shock", "LIQUIDITY_STRESS": "Liquidity Stress",
    "POLICY_DRIVEN": "Policy Driven", "GEOPOLITICAL_RISK": "Geopolitical Risk", "NEUTRAL": "판정 없음",
}


def slice_series(series: MarketSeries, cutoff: datetime) -> MarketSeries | None:
    """cutoff 이하의 봉만 남긴 새 시계열. 봉이 없으면 None (0 으로 채우지 않는다)."""
    n = sum(1 for t in series.timestamps if t <= cutoff)
    if n == 0:
        return None
    if n == len(series.timestamps):
        return series
    vols = series.volumes[:n] if series.volumes is not None else None
    return series.model_copy(update={
        "timestamps": series.timestamps[:n], "values": series.values[:n], "volumes": vols,
        "meta": series.meta.model_copy(update={"as_of": series.timestamps[n - 1]}),
    })


def trading_dates(series_by_id: Mapping[str, MarketSeries], as_of: datetime, days: int, *, min_share: float = 0.3) -> list[date]:
    """
    재생할 날짜. 확보 계열의 min_share 이상이 봉을 가진 날만 '거래일' 로 본다 —
    한 시장만 열린 날(한국 휴일에 미국만 연 날)을 하루로 세지 않기 위해서다.
    """
    counts: dict[date, int] = {}
    total = 0
    for s in series_by_id.values():
        if not s.timestamps:
            continue
        total += 1
        for d in {t.date() for t in s.timestamps if t <= as_of}:
            counts[d] = counts.get(d, 0) + 1
    if total == 0:
        return []
    ok = sorted(d for d, c in counts.items() if c >= min_share * total)
    return ok[-days:]


def _end_of(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def replay_market_state(
    instruments: Sequence[Instrument],
    series_by_id: Mapping[str, MarketSeries],
    *,
    as_of: datetime,
    days: int,
    mode: DataMode,
    events: Sequence[NewsEvent] = (),
    zscore_window: int = 60,
    config_dir: Path | None = None,
) -> MarketStateHistory:
    dates = trading_dates(series_by_id, as_of, days)
    # 마지막 점은 언제나 '지금'(as_of) 이다 — 화면의 판정과 같은 절단이어야 띠의 끝 칸이
    # 판정과 일치한다. 일부 시장만 봉을 준 날(한쪽 시장 휴일·공급자 누락)도 이렇게 들어온다.
    if not dates or dates[-1] < as_of.date():
        dates = (dates + [as_of.date()])[-days:] if days > 0 else dates + [as_of.date()]
    points: list[StateHistoryPoint] = []
    prev_label: StateLabel | None = None
    component_labels: dict[str, str] = {}
    for d in dates:
        cutoff = min(_end_of(d), as_of)
        sliced = {}
        for iid, s in series_by_id.items():
            cut = slice_series(s, cutoff)
            if cut is not None:
                sliced[iid] = cut
        try:
            snap = build_snapshot(instruments, sliced, mode=mode, as_of=cutoff, zscore_window=zscore_window, correlations=False)
            cal = event_window(cutoff, config_dir=config_dir)
            state = compute_market_state(snap, {i.id: i for i in instruments}, previous_label=prev_label,
                                         persistence_scale=cal.persistence_scale, config_dir=config_dir)
            # 온도계도 같은 식으로. 뉴스는 그 시점(cutoff)까지 나온 기사만 — 이번 캡처에 없는
            # 과거 기사는 재현할 수 없으므로 앞쪽 날들의 뉴스 온도는 None 으로 남는다.
            past_events = [e for e in events if e.timestamp <= cutoff]
            thermo = compute_thermometer(state, past_events, cutoff, config_dir=config_dir)
        except Exception:
            logger.exception("%s 재생 실패 — 그날은 비운다", d)
            continue
        points.append(StateHistoryPoint(
            date=d, as_of=snap.as_of, label=state.primary_label, secondary_label=state.secondary_label,
            confidence=state.confidence, price_temperature=thermo.price, news_temperature=thermo.news,
            composite=thermo.composite, news_events=thermo.news_events, thermo_confidence=thermo.confidence,
            components={c.key: c.value for c in thermo.components}, coverage=snap.coverage,
            factors={k: round(v.score, 3) for k, v in state.factors.items()},
            hypotheses={h.label.value: round(h.score, 3) for h in state.hypotheses if h.score > 0},
            drivers=[f"{dr.label} {dr.z:+.1f}σ" for dr in state.main_drivers[:3]],
        ))
        prev_label = state.primary_label
        component_labels = {c.key: c.label for c in thermo.components}

    segments: list[StateSegment] = []
    for p in points:
        if segments and segments[-1].label == p.label:
            seg = segments[-1]
            n = seg.days + 1
            segments[-1] = seg.model_copy(update={"end": p.date, "days": n, "mean_confidence": (seg.mean_confidence * seg.days + p.confidence) / n})
        else:
            segments.append(StateSegment(label=p.label, start=p.date, end=p.date, days=1, mean_confidence=p.confidence))
    days_by_label: dict[str, int] = {}
    for p in points:
        days_by_label[p.label.value] = days_by_label.get(p.label.value, 0) + 1

    def _half(vals: list[float | None]) -> tuple[float | None, float | None]:
        xs = [v for v in vals if v is not None]
        if len(xs) < 4:
            return None, None
        h = len(xs) // 2
        return sum(xs[:h]) / h, sum(xs[h:]) / (len(xs) - h)

    c1, c2 = _half([p.confidence for p in points])
    t1, t2 = _half([p.composite if p.composite is not None else p.price_temperature for p in points])

    summary = ""
    if points:
        cur = segments[-1]
        parts = [f"{LABEL_KO[k]} {v}일" for k, v in sorted(days_by_label.items(), key=lambda kv: -kv[1])]
        summary = f"최근 {len(points)}거래일: " + " · ".join(parts) + f" — 상태 전환 {len(segments) - 1}회, 현재 {LABEL_KO[cur.label.value]} {cur.days}일째"
        if len(segments) >= 2:
            prv = segments[-2]
            summary += f" (직전 {LABEL_KO[prv.label.value]} {prv.days}일)"
        if t1 is not None and t2 is not None:
            summary += f". 온도 전반 {t1:+.0f} → 후반 {t2:+.0f}"
    return MarketStateHistory(
        as_of=as_of, days_requested=days, points=points, segments=segments, changes=max(0, len(segments) - 1),
        days_by_label=days_by_label, current_streak=segments[-1].days if segments else 0,
        previous_label=segments[-2].label if len(segments) >= 2 else None,
        confidence_first_half=c1, confidence_second_half=c2, temperature_first_half=t1, temperature_second_half=t2,
        component_labels=component_labels, summary=summary,
        note=("같은 시계열을 날짜별로 잘라 같은 엔진(판정 → 온도계)으로 다시 계산한 값이다 — 오늘 화면과 같은 잣대. "
              "뉴스 온도는 그 시점까지 이번 캡처에 남아 있는 기사로만 재므로 앞쪽 날들은 결측이고, 상관·지배 축은 계산하지 않았다. "
              "그날 확보되지 않은 계열은 그날 판정에서도 빠진다. 확신의 지속성 항은 전날 재생값을 직전 판정으로 넣어 계산하므로 "
              "화면 판정(저장 이력 기준)과 몇 점 다를 수 있다. 마지막 점은 화면과 같은 절단(as_of)이다."),
    )
