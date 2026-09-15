"""
DivergenceEngine (설계서 STEP 5.8 / 요구 7).

요구 7 이 "이 프로젝트의 핵심 차별화 기능 중 하나" 로 지목한 부분이다.
뉴스 내러티브와 실제 가격·수급이 어긋나는 지점을 찾는다.

    gap      = |n_A - n_B|                        두 신호 모두 -100~+100
    severity = 100·tanh(gap/80) · persistence · materiality

materiality 가 없으면 A=+3, B=-3 같은 무의미한 괴리가 잡힌다. 통계적으로는
divergence 지만 둘 다 사실상 0 이라 실무적 의미가 없다.

persistence 가 없으면 한 틱짜리 노이즈와 며칠 지속되는 구조적 괴리를
구분하지 못한다. 요구 7 이 duration 을 필드로 요구한 이유가 이것이다.

순수 함수다. 직전 스냅샷의 divergence 목록을 받아 지속 기간을 잇는다.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.common import Direction, direction_for
from ..models.divergence import (
    Divergence,
    DivergenceLeg,
    DivergenceType,
    SeverityBand,
)
from ..models.market import Instrument, MarketSnapshot
from ..models.state import MarketState, StateLabel
from ..models.theme import Theme, ThemeState
from .korean import fix_particles
from .scoring import load_scoring, squash, unsquash

ENGINE_VERSION = "0.1.0"


@lru_cache(maxsize=4)
def load_divergence_rules(config_dir: Path | None = None) -> dict:
    d = config_dir or CONFIG_DIR
    with (d / "divergence_rules.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def reset_divergence_cache() -> None:
    load_divergence_rules.cache_clear()


def _band(severity: float, cfg: dict) -> SeverityBand:
    if severity >= cfg["critical"]:
        return SeverityBand.CRITICAL
    if severity >= cfg["high"]:
        return SeverityBand.HIGH
    if severity >= cfg["medium"]:
        return SeverityBand.MEDIUM
    return SeverityBand.LOW


def severity_of(gap: float, magnitude: float, duration: int, cfg: dict) -> float:
    """설계서 STEP 5.8 의 식 그대로."""
    base = 100.0 * math.tanh(gap / float(cfg["severity_divisor"]))
    persistence = min(
        float(cfg["persistence_max"]),
        1.0 + float(cfg["persistence_step"]) * (duration - 1),
    )
    materiality = max(0.0, min(1.0, magnitude / float(cfg["materiality_divisor"])))
    return base * persistence * materiality


def qualifies(left: float, right: float, trigger: dict) -> str | None:
    """
    이 격차가 '괴리' 라 부를 만한가.

    같은 방향으로 크기만 다른 것은 괴리가 아니다. 요구 7 이 든 예시는 전부
    방향이 엇갈리거나 한쪽이 무반응인 경우다. 뉴스 톤 +6 과 가격 +66 은
    격차가 60 이지만 둘 다 같은 방향이므로 "내러티브가 가격으로 확인되지
    않는다" 고 말하면 틀린 말이 된다.

    Returns: "opposing" | "unresponsive" | None
    """
    opposing_min = float(trigger["opposing_min_abs"])
    unresponsive_max = float(trigger["unresponsive_max_abs"])

    if (left > 0) != (right > 0):
        if abs(left) >= opposing_min and abs(right) >= opposing_min:
            return "opposing"

    big, small = (left, right) if abs(left) >= abs(right) else (right, left)
    if abs(small) < unresponsive_max <= abs(big):
        return "unresponsive"
    return None


def _fmt(value: float) -> str:
    return f"{value:+.0f}"


def _render(template: str, c: "_Candidate") -> str:
    """
    설명 문장 생성.

    active / quiet 치환자는 **크기 기준**이다. 무반응 문장이 "가격은 -8로
    움직였으나 수급은 +39에 그쳤다" 처럼 큰 쪽과 작은 쪽을 뒤바꿔 말하는
    것을 막는다. left/right 는 규칙에 적힌 순서 그대로다.
    """
    a, b = c.legs[0], c.legs[1]
    active, quiet = (a, b) if abs(a.value) >= abs(b.value) else (b, a)
    text = template.format(
        subject=c.subject,
        left=a.name,
        right=b.name,
        left_value=_fmt(a.value),
        right_value=_fmt(b.value),
        active=active.name,
        active_value=_fmt(active.value),
        quiet=quiet.name,
        quiet_value=_fmt(quiet.value),
        gap=f"{c.gap:.0f}",
    )
    return fix_particles(" ".join(text.split()))


class _Candidate:
    """트리거 판정 전의 후보. 지속 기간을 붙이기 전 단계다."""

    __slots__ = (
        "key", "type", "rule_id", "subject", "legs", "gap", "magnitude",
        "templates", "related_theme", "related_assets",
    )

    def __init__(
        self,
        *,
        key: str,
        type: DivergenceType,
        rule_id: str,
        subject: str,
        legs: list[DivergenceLeg],
        gap: float,
        magnitude: float,
        templates: Mapping[str, str],
        related_theme: str | None = None,
        related_assets: Sequence[str] = (),
    ) -> None:
        self.key = key
        self.type = type
        self.rule_id = rule_id
        self.subject = subject
        self.legs = legs
        self.gap = gap
        self.magnitude = magnitude
        self.templates = dict(templates)
        self.related_theme = related_theme
        self.related_assets = list(related_assets)


def _leg(name: str, value: float, z: float | None = None) -> DivergenceLeg:
    return DivergenceLeg(
        name=name, value=value, z=z, direction=_direction_from_display(value)
    )


def _direction_from_display(value: float) -> Direction:
    # 표시값(-100~100) 기준의 사표시. ±10 미만은 방향 없음으로 본다.
    return direction_for(value, deadband=10.0)


def _theme_candidates(
    themes: Sequence[ThemeState], rules: dict, *, use_flow: bool = True
) -> list[_Candidate]:
    out: list[_Candidate] = []
    for spec in rules.get("theme_pairs", []):
        # 수급 신호를 끈 설정(scoring.yaml theme.use_flow=false)에서는 수급이 한쪽인
        # 짝을 평가하지 않는다. 규칙은 파일에 남겨 두어 수급이 붙는 날 그대로 산다.
        if not use_flow and "flow_momentum" in (spec.get("left"), spec.get("right")):
            continue
        min_events = int(spec.get("min_events", 0))
        for t in themes:
            left = getattr(t, spec["left"])
            right = getattr(t, spec["right"])
            # 측정되지 않은 신호로 괴리를 주장하지 않는다.
            if left is None or right is None:
                continue
            # 기사 1건으로 "내러티브가 가격과 어긋난다" 고 말하지 않는다.
            # 그건 한 기자의 문장과 시장을 비교하는 것이다.
            if min_events and len(t.supporting_events) < min_events:
                continue
            out.append(
                _Candidate(
                    key=f"{spec['id']}:{t.theme_id}",
                    type=DivergenceType(spec["type"]),
                    rule_id=spec["id"],
                    subject=t.name,
                    legs=[
                        _leg(spec["left_label"], left),
                        _leg(spec["right_label"], right),
                    ],
                    gap=abs(left - right),
                    magnitude=max(abs(left), abs(right)),
                    templates=spec["explanation"],
                    related_theme=t.theme_id,
                    related_assets=t.supporting_instruments,
                )
            )
    return out


def _instrument_candidates(
    snapshot: MarketSnapshot, rules: dict, divisor: float, scale: float
) -> list[_Candidate]:
    out: list[_Candidate] = []
    for spec in rules.get("instrument_pairs", []):
        lz = snapshot.z(spec["left"])
        rz = snapshot.z(spec["right"])
        if lz is None or rz is None:
            continue
        if abs(lz) < float(spec.get("require_left_abs", 0.0)):
            continue
        left = squash(lz, scale=scale, divisor=divisor)
        right = squash(rz, scale=scale, divisor=divisor)
        out.append(
            _Candidate(
                key=spec["id"],
                type=DivergenceType(spec["type"]),
                rule_id=spec["id"],
                subject=spec["left_label"],
                legs=[
                    _leg(spec["left_label"], left, lz),
                    _leg(spec["right_label"], right, rz),
                ],
                gap=abs(left - right),
                magnitude=max(abs(left), abs(right)),
                templates=spec["explanation"],
                related_assets=[spec["left"], spec["right"]],
            )
        )
    return out


def _state_vol_candidates(
    state: MarketState,
    snapshot: MarketSnapshot,
    rules: dict,
    divisor: float,
    scale: float,
) -> list[_Candidate]:
    """
    리스크 판정은 섰는데 변동성이 반응하지 않은 경우.

    요구 7 의 "Risk Event ↑ / VIX 반응 없음" 이다. 이것은 두 신호의 단순
    격차가 아니라 '기대했던 반응의 부재' 라 별도 규칙으로 둔다.
    """
    out: list[_Candidate] = []
    for spec in rules.get("state_vs_volatility", []):
        if state.primary_label.value not in spec["states"]:
            continue
        vz = snapshot.z(spec["instrument"])
        if vz is None or abs(vz) > float(spec["max_vol_z"]):
            continue

        # 판정의 강도를 왼쪽 신호로 삼는다. confidence 가 높을수록 강한 주장이다.
        left = state.confidence
        right = squash(vz, scale=scale, divisor=divisor)
        out.append(
            _Candidate(
                key=f"{spec['id']}:{state.primary_label.value}",
                type=DivergenceType(spec["type"]),
                rule_id=spec["id"],
                subject=state.primary_label.value,
                legs=[
                    _leg("상태 판정 신뢰도", left),
                    _leg(spec["instrument_label"], right, vz),
                ],
                gap=abs(left - right),
                magnitude=max(abs(left), abs(right)),
                templates=spec["explanation"],
                related_assets=[spec["instrument"]],
            )
        )
    return out


def _theme_asset_candidates(
    themes: Sequence[ThemeState],
    theme_registry: Mapping[str, Theme],
    snapshot: MarketSnapshot,
    instruments_by_id: Mapping[str, Instrument],
    rules: dict,
    divisor: float,
    scale: float,
) -> list[_Candidate]:
    """테마는 강한데 구성 자산 하나가 반대로 가는 경우 (요구 7 의 Theme↑/Asset↓)."""
    spec = rules.get("theme_vs_asset")
    if not spec:
        return []

    out: list[_Candidate] = []
    for t in themes:
        if abs(t.theme_score) < float(spec["min_theme_abs"]):
            continue
        theme = theme_registry.get(t.theme_id)
        if theme is None:
            continue
        for ti in theme.instruments:
            z = snapshot.z(ti.instrument_id)
            if z is None:
                continue
            aligned = z * ti.direction
            asset_value = squash(aligned, scale=scale, divisor=divisor)
            # 테마와 같은 부호면 괴리가 아니다
            if (asset_value > 0) == (t.theme_score > 0):
                continue
            # 자산이 사실상 제자리인데 "반대 방향" 이라 말하지 않는다.
            if abs(asset_value) < float(spec.get("min_asset_abs", 0.0)):
                continue
            ins = instruments_by_id.get(ti.instrument_id)
            out.append(
                _Candidate(
                    key=f"{spec['id']}:{t.theme_id}:{ti.instrument_id}",
                    type=DivergenceType(spec["type"]),
                    rule_id=spec["id"],
                    subject=t.name,
                    legs=[
                        _leg("테마 점수", t.theme_score),
                        _leg(ins.name if ins else ti.instrument_id, asset_value, z),
                    ],
                    gap=abs(t.theme_score - asset_value),
                    magnitude=max(abs(t.theme_score), abs(asset_value)),
                    templates=spec["explanation"],
                    related_theme=t.theme_id,
                    related_assets=[ti.instrument_id],
                )
            )
    return out


def _passes_trigger(c: "_Candidate", trigger: dict) -> bool:
    if c.gap < float(trigger["min_gap"]):
        return False
    if c.magnitude < float(trigger["min_magnitude"]):
        return False
    return qualifies(c.legs[0].value, c.legs[1].value, trigger) is not None


def detect_divergences(
    themes: Sequence[ThemeState],
    theme_registry: Mapping[str, Theme],
    state: MarketState,
    snapshot: MarketSnapshot,
    instruments_by_id: Mapping[str, Instrument],
    *,
    previous: Sequence[Divergence] = (),
    config_dir: Path | None = None,
) -> list[Divergence]:
    """
    현재 스냅샷의 괴리를 찾는다.

    previous 는 직전 틱의 divergence 목록이다. 같은 key 가 이어지면 duration
    을 늘리고 first_detected_at 을 유지한다. 트리거 조건에 min_duration 이
    있으므로, 한 틱만 나타난 괴리는 기록만 되고 밖으로 나가지 않는다.
    """
    scoring = load_scoring(config_dir)
    dcfg = scoring["divergence"]
    sq = scoring["standardize"]
    scale, divisor = float(sq["squash_scale"]), float(sq["squash_divisor"])
    rules = load_divergence_rules(config_dir)
    trigger = dcfg["trigger"]

    candidates: list[_Candidate] = []
    candidates += _theme_candidates(themes, rules, use_flow=bool(scoring["theme"].get("use_flow", True)))
    candidates += _instrument_candidates(snapshot, rules, divisor, scale)
    candidates += _state_vol_candidates(state, snapshot, rules, divisor, scale)
    candidates += _theme_asset_candidates(
        themes, theme_registry, snapshot, instruments_by_id, rules, divisor, scale
    )

    prior = {d.id: d for d in previous}
    out: list[Divergence] = []

    for c in candidates:
        if not _passes_trigger(c, trigger):
            continue

        kind = qualifies(c.legs[0].value, c.legs[1].value, trigger)
        assert kind is not None  # _passes_trigger 가 이미 확인했다

        seen = prior.get(c.key)
        duration = (seen.duration_periods + 1) if seen else 1
        first_seen = seen.first_detected_at if seen else snapshot.as_of

        if duration < int(trigger["min_duration"]):
            # 아직 노이즈와 구분되지 않는다. 기록은 하되 내보내지 않는다.
            continue

        severity = severity_of(c.gap, c.magnitude, duration, dcfg)
        out.append(
            Divergence(
                id=c.key,
                type=c.type,
                as_of=snapshot.as_of,
                severity=max(0.0, min(100.0, severity)),
                severity_band=_band(severity, dcfg["bands"]),
                duration_periods=duration,
                first_detected_at=first_seen,
                related_theme=c.related_theme,
                related_assets=c.related_assets,
                legs=c.legs,
                gap=c.gap,
                rule_id=c.rule_id,
                explanation=_render(c.templates[kind], c),
                llm_commentary=None,
            )
        )

    out.sort(key=lambda d: d.severity, reverse=True)
    return out


def pending_candidates(
    themes: Sequence[ThemeState],
    theme_registry: Mapping[str, Theme],
    state: MarketState,
    snapshot: MarketSnapshot,
    instruments_by_id: Mapping[str, Instrument],
    *,
    previous: Sequence[Divergence] = (),
    config_dir: Path | None = None,
) -> list[Divergence]:
    """
    아직 min_duration 을 채우지 못한 후보.

    다음 틱에서 duration 을 이으려면 이번 틱의 관측을 어딘가 남겨야 한다.
    스냅샷에 싣지 않고 저장소에만 두기 위해 분리했다.
    """
    scoring = load_scoring(config_dir)
    dcfg = scoring["divergence"]
    sq = scoring["standardize"]
    scale, divisor = float(sq["squash_scale"]), float(sq["squash_divisor"])
    rules = load_divergence_rules(config_dir)
    trigger = dcfg["trigger"]

    candidates = (
        _theme_candidates(themes, rules, use_flow=bool(scoring["theme"].get("use_flow", True)))
        + _instrument_candidates(snapshot, rules, divisor, scale)
        + _state_vol_candidates(state, snapshot, rules, divisor, scale)
        + _theme_asset_candidates(
            themes, theme_registry, snapshot, instruments_by_id, rules, divisor, scale
        )
    )
    prior = {d.id: d for d in previous}
    out: list[Divergence] = []
    for c in candidates:
        if not _passes_trigger(c, trigger):
            continue
        seen = prior.get(c.key)
        duration = (seen.duration_periods + 1) if seen else 1
        if duration >= int(trigger["min_duration"]):
            continue
        out.append(
            Divergence(
                id=c.key,
                type=c.type,
                as_of=snapshot.as_of,
                severity=0.0,
                severity_band=SeverityBand.LOW,
                duration_periods=duration,
                first_detected_at=seen.first_detected_at if seen else snapshot.as_of,
                related_theme=c.related_theme,
                related_assets=c.related_assets,
                legs=c.legs,
                gap=c.gap,
                rule_id=c.rule_id,
                explanation="관측 1회. 지속 여부 확인 중이다.",
            )
        )
    return out
