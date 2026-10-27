"""
Cross-Asset Confirmation (설계서 STEP 5.5).

이 상태라면 각 자산이 어느 방향으로 움직여야 하는가를 사전 정의 기대표와
대조한다. 이 구조가 요구 6 의 문장을 자동으로 만든다.

    confirmed_i   ⟺ sign(z_i) == expected_i  and  |z_i| >= 0.5
    conflicting_i ⟺ sign(z_i) != expected_i  and  |z_i| >= 1.0
    unconfirmed_i ⟺ |z_i| < 0.5

conflict 임계를 confirm 보다 높게 둔 것은 의도적 비대칭이다. "기대와
반대로 강하게 움직였다" 는 "기대대로 조금 움직였다" 보다 강한 주장이므로
더 높은 증거를 요구한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..models.market import Instrument, MarketSnapshot
from ..models.state import ConfirmationResult
from .scoring import load_scoring


def evaluate_confirmation(
    expected: Mapping[str, int],
    snapshot: MarketSnapshot,
    instruments_by_id: Mapping[str, Instrument],
    *,
    horizon: str = "1d",
    config_dir: Path | None = None,
) -> ConfirmationResult:
    """
    기대 반응표와 실제 z 를 대조한다.

    기대표가 비어 있으면(방향이 본질적으로 모호한 상태) 확인을 시도하지
    않는다. 틀린 기대표를 쓰느니 확인을 포기하고 confidence 계산에서
    빼는 편이 정직하다.
    """
    cfg = load_scoring(config_dir)["confirmation"]
    if not expected:
        return ConfirmationResult(
            expected={},
            score=0.0,
            verdict="LOW",
            note="이 상태는 기대 반응 방향이 모호해 cross-asset 확인을 적용하지 않는다.",
        )

    confirmed: list[str] = []
    unconfirmed: list[str] = []
    conflicting: list[str] = []
    missing: list[str] = []

    for iid, want in expected.items():
        z = snapshot.z(iid, horizon)
        if z is None:
            missing.append(iid)
            continue
        if abs(z) < cfg["confirm_min_abs_z"]:
            unconfirmed.append(iid)
        elif (z > 0) == (want > 0):
            confirmed.append(iid)
        elif abs(z) >= cfg["conflict_min_abs_z"]:
            conflicting.append(iid)
        else:
            # 반대 방향이지만 상충이라 부를 만큼 크지 않다
            unconfirmed.append(iid)

    evaluated = len(confirmed) + len(unconfirmed) + len(conflicting)
    score = ((len(confirmed) - len(conflicting)) / evaluated) if evaluated else 0.0

    if score >= cfg["verdict_high"]:
        verdict = "HIGH"
    elif score >= cfg["verdict_medium"]:
        verdict = "MEDIUM"
    else:
        verdict = "LOW"

    return ConfirmationResult(
        expected=dict(expected),
        confirmed=confirmed,
        unconfirmed=unconfirmed,
        conflicting=conflicting,
        score=score,
        verdict=verdict,
        note=_describe(confirmed, unconfirmed, conflicting, missing, instruments_by_id),
    )


def _name(iid: str, by_id: Mapping[str, Instrument]) -> str:
    ins = by_id.get(iid)
    return ins.name if ins else iid


def _describe(
    confirmed: list[str],
    unconfirmed: list[str],
    conflicting: list[str],
    missing: list[str],
    by_id: Mapping[str, Instrument],
) -> str:
    """
    템플릿 문장. LLM 없이 생성된다 (요구 15-7).

    요구 6 의 "유가는 강하게 상승했으나 USD 반응은 제한적이므로 글로벌
    Risk-Off 전이는 아직 제한적" 이 이 함수에서 나온다.
    """
    parts: list[str] = []
    if confirmed:
        names = ", ".join(_name(i, by_id) for i in confirmed[:4])
        parts.append(f"{names}가 기대 방향으로 움직여 판정을 뒷받침한다")
    if unconfirmed:
        names = ", ".join(_name(i, by_id) for i in unconfirmed[:4])
        parts.append(f"{names}의 반응은 제한적이라 아직 확인되지 않았다")
    if conflicting:
        names = ", ".join(_name(i, by_id) for i in conflicting[:4])
        parts.append(f"{names}는 기대와 반대로 움직여 판정과 상충한다")
    if missing:
        parts.append(f"{len(missing)}개 자산은 데이터가 없어 확인에서 제외했다")
    return ". ".join(parts) + ("." if parts else "")
