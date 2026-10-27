"""
AlertEngine (설계서 STEP 5.9 / 요구 9).

요구 9 가 "단순 수준보다 변화를 중요하게 본다" 고 했다. 그래서 이 엔진은
현재 값이 아니라 **직전 틱 대비 변화**를 본다. 스키마의 AlertTrigger 가
baseline 과 delta 를 필수로 요구하므로, 기준선 없는 알림은 애초에 만들 수 없다.

    severity = 100·tanh(|delta_z| / 2.5) · type_weight

중복 억제
---------
dedupe_key = (type, subject, severity_band). 같은 키가 cooldown 안에 다시
뜨면 새 알림을 만들지 않고 fire_count 만 올린다. 기존 코드에는 이 장치가
전혀 없어 같은 알림이 매 주기 반복됐다.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Collection, Mapping, Sequence

from ..models.alert import Alert, AlertState, AlertTrigger, AlertType
from ..models.divergence import Divergence, DivergenceType, SeverityBand
from ..models.market import AssetClass, Instrument, MarketSnapshot
from ..models.snapshot import DataHealth
from ..models.state import MarketState
from ..models.theme import ThemeState
from .scoring import load_scoring

ENGINE_VERSION = "0.1.0"


def _band(severity: float, cfg: dict) -> SeverityBand:
    if severity >= cfg["critical"]:
        return SeverityBand.CRITICAL
    if severity >= cfg["high"]:
        return SeverityBand.HIGH
    if severity >= cfg["medium"]:
        return SeverityBand.MEDIUM
    return SeverityBand.LOW


def severity_of(delta_z: float, alert_type: AlertType, cfg: dict) -> float:
    weight = float(cfg["type_weights"].get(alert_type.value, 0.8))
    return 100.0 * math.tanh(abs(delta_z) / float(cfg["severity_divisor"])) * weight


class _Draft:
    __slots__ = ("type", "subject", "title", "message", "trigger", "theme", "assets", "events")

    def __init__(
        self,
        *,
        type: AlertType,
        subject: str,
        title: str,
        message: str,
        trigger: AlertTrigger,
        theme: str | None = None,
        assets: Sequence[str] = (),
        events: Sequence[str] = (),
    ) -> None:
        self.type = type
        self.subject = subject
        self.title = title
        self.message = message
        self.trigger = trigger
        self.theme = theme
        self.assets = list(assets)
        self.events = list(events)


def _state_change(
    state: MarketState, previous: MarketState | None, thresholds: dict
) -> list[_Draft]:
    if previous is None or previous.primary_label == state.primary_label:
        return []
    return [
        _Draft(
            type=AlertType.STATE_CHANGE,
            subject=state.primary_label.value,
            title=f"시장 상태 전환 · {previous.primary_label.value} → {state.primary_label.value}",
            message=state.narrative or "",
            trigger=AlertTrigger(
                rule_id="state_change",
                metric="market_state.confidence",
                current=state.confidence,
                baseline=previous.confidence,
                delta=state.confidence - previous.confidence,
                threshold=0.0,
                window="1tick",
            ),
        )
    ]


def _new_divergences(
    divergences: Sequence[Divergence],
    previous: Sequence[Divergence],
    min_gap: float,
    theme_names: Mapping[str, str],
    asset_names: Mapping[str, str] | None = None,
) -> list[_Draft]:
    known = {d.id for d in previous}
    names = asset_names or {}
    out: list[_Draft] = []
    for d in divergences:
        if d.id in known:
            continue
        left, right = (d.legs + d.legs)[:2]
        # 무엇에 대한 괴리인지 제목에서 바로 읽혀야 한다. 타입만 적으면
        # 같은 제목이 여러 줄 늘어서고 화면에서 구분이 안 된다.
        if d.related_theme:
            subject_label = theme_names.get(d.related_theme, d.related_theme)
        elif d.type is DivergenceType.CORRELATION_REGIME and len(d.related_assets) >= 2:
            # 상관 괴리는 두 자산의 관계에 대한 것이다. 한쪽만 적으면 반쪽이다.
            subject_label = " ↔ ".join(names.get(a, a) for a in d.related_assets[:2])
        else:
            subject_label = d.related_assets[0] if d.related_assets else d.type.value
        out.append(
            _Draft(
                type=AlertType.DIVERGENCE_OPENED,
                subject=d.id,
                title=f"{subject_label} · {left.name} ↔ {right.name} 괴리",
                message=d.explanation,
                trigger=AlertTrigger(
                    rule_id=d.rule_id,
                    metric=f"{left.name} vs {right.name}",
                    current=left.value,
                    baseline=right.value,
                    delta=d.gap,
                    # 괴리가 성립하려면 넘어야 했던 격차를 임계로 적는다.
                    threshold=min_gap,
                    window=f"{d.duration_periods}tick",
                ),
                theme=d.related_theme,
                assets=d.related_assets,
            )
        )
    return out


def _price_and_vol_spikes(
    snapshot: MarketSnapshot,
    instruments_by_id: Mapping[str, Instrument],
    thresholds: dict,
) -> list[_Draft]:
    """
    가격·변동성 급변.

    이것만은 '변화' 가 아니라 '수준' 을 본다. z-score 자체가 이미 과거 대비
    변화량이기 때문이다. baseline 은 z 임계값이다.
    """
    out: list[_Draft] = []
    price_threshold = float(thresholds["price_zscore"])
    vol_threshold = float(thresholds["vol_spike_z"])

    for iid, feat in snapshot.features.items():
        z = feat.z_1d
        ins = instruments_by_id.get(iid)
        if z is None or ins is None:
            continue

        is_vol = ins.asset_class is AssetClass.VOLATILITY
        threshold = vol_threshold if is_vol else price_threshold
        if abs(z) < threshold:
            continue

        atype = AlertType.VOL_SPIKE if is_vol else AlertType.PRICE_ZSCORE_SPIKE
        arrow = "급등" if z > 0 else "급락"
        out.append(
            _Draft(
                type=atype,
                subject=iid,
                title=f"{ins.name} {arrow} · {z:+.1f}σ",
                message=(
                    f"{ins.name}이(가) 60일 평균 대비 {abs(z):.1f}표준편차 "
                    f"{'상승' if z > 0 else '하락'}했다."
                ),
                trigger=AlertTrigger(
                    rule_id=f"{atype.value.lower()}",
                    metric=f"z_1d({iid})",
                    current=z,
                    baseline=0.0,
                    delta=z,
                    threshold=threshold,
                    window="1d",
                ),
                assets=[iid],
            )
        )
    return out


def _theme_moves(
    themes: Sequence[ThemeState],
    previous: Mapping[str, ThemeState],
    thresholds: dict,
) -> list[_Draft]:
    out: list[_Draft] = []
    change_threshold = float(thresholds["theme_change"])
    flow_threshold = float(thresholds["flow_reversal_z"])

    for t in themes:
        prev = previous.get(t.theme_id)
        if prev is None:
            continue

        if abs(t.last_change) >= change_threshold:
            out.append(
                _Draft(
                    type=AlertType.THEME_SENTIMENT_SPIKE,
                    subject=t.theme_id,
                    title=f"{t.name} 테마 점수 급변 · {t.last_change:+.0f}p",
                    message=(
                        f"{t.name} 테마 점수가 {prev.theme_score:+.0f}에서 "
                        f"{t.theme_score:+.0f}로 움직였다."
                    ),
                    trigger=AlertTrigger(
                        rule_id="theme_change",
                        metric=f"theme_score({t.theme_id})",
                        current=t.theme_score,
                        baseline=prev.theme_score,
                        delta=t.last_change,
                        delta_pct=(
                            100.0 * t.last_change / abs(prev.theme_score)
                            if prev.theme_score
                            else None
                        ),
                        threshold=change_threshold,
                        window=t.last_change_window,
                    ),
                    theme=t.theme_id,
                    events=t.supporting_events,
                )
            )

        # 수급 방향 전환. 부호가 뒤집히고 새 값이 충분히 커야 한다.
        now, before = t.flow_momentum, prev.flow_momentum
        if (
            now is not None
            and before is not None
            and (now > 0) != (before > 0)
            and abs(now) >= flow_threshold * 25.0
        ):
            out.append(
                _Draft(
                    type=AlertType.FLOW_REVERSAL,
                    subject=t.theme_id,
                    title=f"{t.name} 수급 방향 전환 · {before:+.0f} → {now:+.0f}",
                    message=(
                        f"{t.name} 테마의 수급이 "
                        f"{'매도에서 매수로' if now > 0 else '매수에서 매도로'} 돌아섰다."
                    ),
                    trigger=AlertTrigger(
                        rule_id="flow_reversal",
                        metric=f"flow_momentum({t.theme_id})",
                        current=now,
                        baseline=before,
                        delta=now - before,
                        threshold=flow_threshold * 25.0,
                        window=t.last_change_window,
                    ),
                    theme=t.theme_id,
                )
            )

        # 뉴스량 급증
        current_count = len(t.supporting_events)
        base_count = len(prev.supporting_events)
        if current_count >= 3 and current_count >= base_count * 2 and base_count > 0:
            out.append(
                _Draft(
                    type=AlertType.NEWS_VOLUME_SPIKE,
                    subject=t.theme_id,
                    title=f"{t.name} 뉴스량 급증 · {base_count}건 → {current_count}건",
                    message=f"{t.name} 관련 기사가 직전 대비 {current_count - base_count}건 늘었다.",
                    trigger=AlertTrigger(
                        rule_id="news_volume",
                        metric=f"news_count({t.theme_id})",
                        current=float(current_count),
                        baseline=float(base_count),
                        delta=float(current_count - base_count),
                        delta_pct=100.0 * (current_count - base_count) / base_count,
                        threshold=100.0,
                        window="1tick",
                    ),
                    theme=t.theme_id,
                    events=t.supporting_events,
                )
            )
    return out


def _data_quality(health: DataHealth, thresholds: dict) -> list[_Draft]:
    floor = float(thresholds["coverage_floor"])
    if health.coverage >= floor and not health.stale:
        return []
    return [
        _Draft(
            type=AlertType.DATA_QUALITY,
            subject="coverage",
            title=f"데이터 품질 저하 · 커버리지 {health.coverage:.0%}",
            message=(
                f"{health.expected_instruments}개 중 {health.available_instruments}개만 "
                f"확보했다. 오래된 데이터 {len(health.stale)}건."
            ),
            trigger=AlertTrigger(
                rule_id="coverage_floor",
                metric="data_health.coverage",
                current=health.coverage,
                baseline=floor,
                delta=health.coverage - floor,
                threshold=floor,
                window="1tick",
            ),
        )
    ]


def _delta_z(draft: _Draft) -> float:
    """
    severity 계산용 표준화 변화량.

    지표마다 단위가 달라 그대로 쓸 수 없다. threshold 를 1σ 로 보는 비율로
    환산한다. threshold 가 0 인 경우(상태 전환 등)는 변화량 자체를 쓴다.
    """
    t = draft.trigger
    if t.threshold:
        return t.delta / abs(t.threshold)
    if draft.type is AlertType.STATE_CHANGE:
        # 상태 전환은 그 자체로 중대하다. 신뢰도 변화폭을 얹는다.
        return 2.0 + abs(t.delta) / 50.0
    return abs(t.delta) / 50.0


def build_alerts(
    state: MarketState,
    themes: Sequence[ThemeState],
    divergences: Sequence[Divergence],
    snapshot: MarketSnapshot,
    health: DataHealth,
    instruments_by_id: Mapping[str, Instrument],
    *,
    previous_state: MarketState | None = None,
    previous_themes: Mapping[str, ThemeState] | None = None,
    previous_divergences: Sequence[Divergence] = (),
    previous_alerts: Sequence[Alert] = (),
    threshold_scale: float = 1.0,
    config_dir: Path | None = None,
) -> list[Alert]:
    """
    순수 함수. 직전 틱과 비교해 '변화' 를 알린다.

    threshold_scale 은 이벤트 창(중앙은행 회의 직전)에서 급변 임계를 올리는
    배율이다. 가격·변동성·테마 급변에만 걸린다 — 상태 전환·괴리 발생·데이터
    품질은 임계가 아니라 사건이라 그대로 둔다.
    """
    scoring = load_scoring(config_dir)
    cfg = scoring["alert"]
    thresholds = dict(cfg["thresholds"])
    if threshold_scale != 1.0:
        for key in ("price_zscore", "vol_spike_z", "theme_change"):
            thresholds[key] = float(thresholds[key]) * threshold_scale
    min_gap = float(scoring["divergence"]["trigger"]["min_gap"])
    theme_names = {t.theme_id: t.name for t in themes}
    now = snapshot.as_of
    cooldown = timedelta(minutes=float(cfg["cooldown_minutes"]))

    drafts: list[_Draft] = []
    drafts += _state_change(state, previous_state, thresholds)
    drafts += _new_divergences(
        divergences, previous_divergences, min_gap, theme_names,
        asset_names={k: v.name for k, v in instruments_by_id.items()},
    )
    drafts += _price_and_vol_spikes(snapshot, instruments_by_id, thresholds)
    drafts += _theme_moves(themes, previous_themes or {}, thresholds)
    drafts += _data_quality(health, thresholds)

    prior = {a.dedupe_key: a for a in previous_alerts}
    out: list[Alert] = []

    for d in drafts:
        severity = max(0.0, min(100.0, severity_of(_delta_z(d), d.type, cfg)))
        band = _band(severity, cfg["bands"])
        key = f"{d.type.value}|{d.subject}|{band.value}"

        seen = prior.get(key)
        if seen is not None and (now - seen.last_fired_at) < cooldown:
            # 같은 알림을 반복 발화하지 않는다. 횟수만 센다.
            out.append(
                seen.model_copy(
                    update={
                        "as_of": now,
                        "last_fired_at": now,
                        "fire_count": seen.fire_count + 1,
                        "state": AlertState.ONGOING,
                    }
                )
            )
            continue

        out.append(
            Alert(
                id=f"{key}@{now.isoformat()}",
                as_of=now,
                type=d.type,
                subject=d.subject,
                severity=severity,
                severity_band=band,
                title=d.title,
                message=d.message,
                trigger=d.trigger,
                related_theme=d.theme,
                related_assets=d.assets,
                related_events=d.events,
                dedupe_key=key,
                first_fired_at=seen.first_fired_at if seen else now,
                last_fired_at=now,
                fire_count=(seen.fire_count + 1) if seen else 1,
                state=AlertState.ONGOING if seen else AlertState.NEW,
            )
        )

    out.sort(key=lambda a: a.severity, reverse=True)
    return out


def carry_forward(
    current: Sequence[Alert],
    previous: Sequence[Alert],
    as_of: datetime,
    *,
    live_subjects: Collection[str] = (),
    config_dir: Path | None = None,
) -> list[Alert]:
    """
    이번 틱에 재생성되지 않은 알림을 보존 창 동안 타임라인에 남긴다.

    알림은 '지금 참인 것' 의 목록이 아니라 '최근에 일어난 일' 의 기록이다.
    괴리 발생 같은 사건은 한 번 일어나면 다음 틱에 조건이 재생성되지 않는데,
    그때마다 화면에서 사라지면 타임라인이 성립하지 않는다.

    다만 재생성되지 않았다고 해서 해소된 것은 아니다. 괴리가 4틱째
    이어지고 있는데 알림이 "해소" 로 찍히면 화면이 거짓말을 한다.
    live_subjects 에 남아 있는 대상은 ONGOING 으로 둔다.

    보존 창을 넘긴 것은 버린다. 화면이 무한히 길어지면 아무도 보지 않는다.
    """
    cfg = load_scoring(config_dir)["alert"]
    retention = timedelta(minutes=float(cfg["retention_minutes"]))

    live_keys = {a.dedupe_key for a in current}
    still_true = set(live_subjects)
    out: list[Alert] = []
    for a in previous:
        if a.dedupe_key in live_keys:
            continue
        if (as_of - a.last_fired_at) > retention:
            continue
        state = (
            AlertState.ONGOING if a.subject in still_true else AlertState.RESOLVED
        )
        out.append(a.model_copy(update={"as_of": as_of, "state": state}))
    return out
