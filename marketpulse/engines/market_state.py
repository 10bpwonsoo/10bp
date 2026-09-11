"""
MarketStateEngine (설계서 STEP 5.3 / 5.4).

require + support 2단 룰로 시장 상태를 판정한다. 판정은 전부 deterministic
하고, LLM 은 이 결과를 자연어로 다듬는 역할만 한다 (요구 2, 6).

요구 6 이 "하나의 Label 만 보여주기보다" 라고 했으므로 hypotheses 전체
순위와 factors 11개를 항상 함께 돌려준다. primary_label 은 편의 필드다.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.common import ScoreBreakdown, ScoreContribution, arrow_for, direction_for
from ..models.market import Instrument, MarketSnapshot
from ..models.state import (
    ConfirmationResult,
    DriverItem,
    FactorScore,
    MarketState,
    RuleMatch,
    StateHypothesis,
    StateLabel,
)
from .confirmation import evaluate_confirmation
from .factors import compute_factors, factor_coverage
from .scoring import Expression, load_scoring, parse_expression, renormalized_average

ENGINE_VERSION = "0.1.0"


@lru_cache(maxsize=4)
def load_state_rules(config_dir: Path | None = None) -> dict[str, dict]:
    d = config_dir or CONFIG_DIR
    with (d / "state_rules.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["states"]


@lru_cache(maxsize=4)
def _parsed_rules(config_dir: Path | None = None) -> dict[str, dict]:
    """표현식을 한 번만 파싱해 둔다. 잘못된 문법은 여기서 즉시 터진다."""
    out: dict[str, dict] = {}
    for label, spec in load_state_rules(config_dir).items():
        out[label] = {
            "description": spec.get("description", ""),
            "require": [
                (r["id"], parse_expression(r["expr"])) for r in spec.get("require", [])
            ],
            "support": [
                (s["id"], parse_expression(s["expr"]), float(s["weight"]))
                for s in spec.get("support", [])
            ],
            "expected_response": spec.get("expected_response", {}) or {},
        }
    return out


def reset_state_rule_cache() -> None:
    load_state_rules.cache_clear()
    _parsed_rules.cache_clear()


def _resolver(factors: Mapping[str, FactorScore], snapshot: MarketSnapshot, horizon: str):
    def resolve(kind: str, name: str) -> float | None:
        if kind == "factor":
            f = factors.get(name)
            return None if f is None else f.score
        return snapshot.z(name, horizon)

    return resolve


def evaluate_hypotheses(
    factors: Mapping[str, FactorScore],
    snapshot: MarketSnapshot,
    *,
    horizon: str = "1d",
    config_dir: Path | None = None,
) -> list[StateHypothesis]:
    """
    모든 상태 라벨을 채점한다.

        score = 0                                 require 미충족
              = base + (1-base)·Σ(w·passed)/Σw    require 충족 시

    support 중 평가할 수 없는 항목은 분모에서 뺀다. 결측을 실패로 처리하면
    데이터가 없을수록 점수가 낮아지고, 통과로 처리하면 데이터가 없을수록
    점수가 높아진다. 둘 다 틀렸다.
    """
    cfg = load_scoring(config_dir)["market_state"]
    base = float(cfg["require_pass_base"])
    resolve = _resolver(factors, snapshot, horizon)

    hypotheses: list[StateHypothesis] = []
    for label, spec in _parsed_rules(config_dir).items():
        matches: list[RuleMatch] = []
        require_ok = True

        for rule_id, expr in spec["require"]:
            passed, observed = expr.evaluate(resolve)
            matches.append(
                RuleMatch(
                    rule_id=rule_id,
                    expression=expr.raw,
                    kind="require",
                    passed=passed,
                    observed=observed,
                    evaluable=observed is not None,
                )
            )
            if not passed:
                require_ok = False

        support_weight = 0.0
        support_hit = 0.0
        for rule_id, expr, weight in spec["support"]:
            passed, observed = expr.evaluate(resolve)
            evaluable = observed is not None
            matches.append(
                RuleMatch(
                    rule_id=rule_id,
                    expression=expr.raw,
                    kind="support",
                    weight=weight,
                    passed=passed and evaluable,
                    observed=observed,
                    evaluable=evaluable,
                )
            )
            if evaluable:
                support_weight += weight
                if passed:
                    support_hit += weight

        if not require_ok:
            score = 0.0
        elif support_weight > 0:
            score = base + (1.0 - base) * (support_hit / support_weight)
        else:
            score = base

        hypotheses.append(
            StateHypothesis(label=StateLabel(label), score=score, matched_rules=matches)
        )

    hypotheses.sort(key=lambda h: (-h.score, h.label.value))
    return hypotheses


def build_drivers(
    snapshot: MarketSnapshot,
    instruments_by_id: Mapping[str, Instrument],
    focus: Sequence[str] = (),
    *,
    horizon: str = "1d",
    config_dir: Path | None = None,
) -> list[DriverItem]:
    """
    Main Drivers. 요구 10 의 'Oil ↑↑ / Rates ↑ / USD →'.

    focus 가 주어지면(판정된 상태의 기대 반응표) 그 자산들을 우선한다.
    판정과 무관한 자산이 상단을 차지하면 '왜 이 판정인가' 에 답하지 못한다.
    """
    cfg = load_scoring(config_dir)["market_state"]
    min_z = float(cfg["driver_min_z"])
    limit = int(cfg["driver_limit"])

    focus_set = set(focus)
    rows: list[tuple[int, float, DriverItem]] = []
    for iid, feat in snapshot.features.items():
        z = feat.z_1d if horizon == "1d" else getattr(feat, f"z_{horizon}", None)
        if z is None or abs(z) < min_z:
            continue
        ins = instruments_by_id.get(iid)
        if ins is None:
            continue
        rows.append(
            (
                0 if iid in focus_set else 1,
                -abs(z),
                DriverItem(
                    instrument_id=iid,
                    label=ins.name,
                    z=z,
                    direction=direction_for(z),
                    arrow=arrow_for(z),
                ),
            )
        )
    rows.sort(key=lambda r: (r[0], r[1]))
    return [r[2] for r in rows[:limit]]


def compute_confidence(
    hypotheses: Sequence[StateHypothesis],
    confirmation: ConfirmationResult,
    coverage: float,
    persistence: float | None,
    *,
    config_dir: Path | None = None,
) -> ScoreBreakdown:
    """
    Confidence (설계서 STEP 5.4).

        Conf = 100·(0.40·Separation + 0.25·Confirmation
                  + 0.20·Coverage   + 0.15·Persistence)

    신뢰도는 "얼마나 강한가" 가 아니라 "얼마나 확실한가" 다. 강도는 factor z
    가 이미 표현하므로 여기 다시 넣으면 같은 정보를 두 번 센다. 대신 서로
    독립적인 불확실성의 원천 네 가지를 넣는다.

    persistence 가 None 이면(직전 스냅샷이 없으면) 0 으로 채우지 않고
    가중치를 재정규화한다.
    """
    cfg = load_scoring(config_dir)["confidence"]
    weights: dict[str, float] = dict(cfg["weights"])
    full_gap = float(cfg["separation_full_gap"])

    top = hypotheses[0].score if hypotheses else 0.0
    second = hypotheses[1].score if len(hypotheses) > 1 else 0.0
    separation = max(0.0, min(1.0, (top - second) / full_gap)) if top > 0 else 0.0

    # confirmation.score 는 -1~+1 이다. 0~1 로 옮긴다.
    confirm = None if not confirmation.expected else (confirmation.score + 1.0) / 2.0

    parts: dict[str, float | None] = {
        "separation": separation,
        "confirmation": confirm,
        "coverage": coverage,
        "persistence": persistence,
    }
    value, unknown = renormalized_average(parts, weights)

    contributions = [
        ScoreContribution(
            key=key,
            normalized=parts[key],  # type: ignore[arg-type]
            weight=weights[key],
            contribution=weights[key] * parts[key],  # type: ignore[operator]
            note=_CONF_NOTES[key],
        )
        for key in weights
        if parts.get(key) is not None
    ]
    return ScoreBreakdown.build(
        value=100.0 * (value or 0.0),
        method="confidence_weighted_v1",
        contributions=contributions,
        missing_inputs=unknown,
    )


_CONF_NOTES = {
    "separation": "1등과 2등 판정의 격차. 붙어 있으면 어느 쪽인지 확신할 수 없다",
    "confirmation": "cross-asset 이 서로를 확인하는 정도",
    "coverage": "factor 계산에 쓸 데이터가 얼마나 확보되었는가",
    "persistence": "직전 틱에도 같은 판정이었는가",
}


def compute_market_state(
    snapshot: MarketSnapshot,
    instruments_by_id: Mapping[str, Instrument],
    *,
    previous_label: StateLabel | None = None,
    horizon: str = "1d",
    config_dir: Path | None = None,
) -> MarketState:
    """순수 함수. 스냅샷을 받아 시장 상태를 판정한다."""
    cfg = load_scoring(config_dir)["market_state"]
    factors = compute_factors(snapshot, config_dir=config_dir, horizon=horizon)
    hypotheses = evaluate_hypotheses(
        factors, snapshot, horizon=horizon, config_dir=config_dir
    )

    top = hypotheses[0] if hypotheses else None
    if top is None or top.score <= 0.0:
        primary, secondary = StateLabel.NEUTRAL, None
        expected: Mapping[str, int] = {}
    else:
        primary = top.label
        expected = _parsed_rules(config_dir)[primary.value]["expected_response"]
        runner = hypotheses[1] if len(hypotheses) > 1 else None
        secondary = (
            runner.label
            if runner and runner.score >= float(cfg["secondary_min_score"])
            else None
        )

    confirmation = evaluate_confirmation(
        expected, snapshot, instruments_by_id, horizon=horizon, config_dir=config_dir
    )

    persistence = None if previous_label is None else float(previous_label == primary)
    confidence = compute_confidence(
        hypotheses,
        confirmation,
        factor_coverage(factors, config_dir=config_dir),
        persistence,
        config_dir=config_dir,
    )

    drivers = build_drivers(
        snapshot,
        instruments_by_id,
        focus=list(expected),
        horizon=horizon,
        config_dir=config_dir,
    )

    narrative = render_narrative(primary, secondary, drivers, confirmation, confidence.value)

    return MarketState(
        as_of=snapshot.as_of,
        primary_label=primary,
        secondary_label=secondary,
        confidence=max(0.0, min(100.0, confidence.value)),
        confidence_breakdown=confidence,
        factors=dict(factors),
        hypotheses=hypotheses,
        main_drivers=drivers,
        cross_asset_confirmation=confirmation,
        narrative=narrative,
        narrative_source="template",
    )


LABEL_KO: dict[StateLabel, str] = {
    StateLabel.RISK_ON: "위험선호",
    StateLabel.RISK_OFF: "위험회피",
    StateLabel.GROWTH_SHOCK: "성장 충격",
    StateLabel.INFLATION_SHOCK: "물가 충격",
    StateLabel.LIQUIDITY_STRESS: "유동성 경색",
    StateLabel.POLICY_DRIVEN: "정책 주도",
    StateLabel.GEOPOLITICAL_RISK: "지정학 리스크",
    StateLabel.NEUTRAL: "뚜렷한 판정 없음",
}


def render_narrative(
    primary: StateLabel,
    secondary: StateLabel | None,
    drivers: Sequence[DriverItem],
    confirmation: ConfirmationResult,
    confidence: float,
) -> str:
    """
    템플릿 설명. LLM 없이 생성된다.

    P3 에서 LLM 요약이 붙어도 이 문장은 남는다. LLM 이 실패하면 여기로
    돌아온다 (요구 15-7).
    """
    if primary is StateLabel.NEUTRAL:
        if drivers:
            top = ", ".join(f"{d.label} {d.z:+.1f}σ" for d in drivers[:3])
            return (
                f"어느 상태 룰도 발동 조건을 충족하지 않았다. 개별 변수로는 {top} 가 "
                "움직였으나 전체 시장 상태를 규정할 정도는 아니다."
            )
        return "어느 상태 룰도 발동 조건을 충족하지 않았고, 임계 이상으로 움직인 변수도 없다."

    head = LABEL_KO[primary]
    if secondary:
        head += f" 성격이 우세하며 {LABEL_KO[secondary]} 요소가 함께 나타난다"
    else:
        head += " 성격이 우세하다"

    lead = ""
    if drivers:
        top = ", ".join(f"{d.label} {d.z:+.1f}σ" for d in drivers[:3])
        lead = f" 주도 변수는 {top} 다."

    tail = f" {confirmation.note}" if confirmation.note else ""
    conf = f" 판정 신뢰도는 {confidence:.0f}% 다."
    return head + "." + lead + tail + conf
