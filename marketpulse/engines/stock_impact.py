"""
Market → Stock Impact Score (2026-09-16 신설).

    impact = 100·tanh(|shock_z|/div) × |exposure| × stat_conf × fund_relevance × current_relevance

각 항의 의미
  shock_z          드라이버의 오늘 z (기존 FeatureEngine)
  exposure         primary 창 상관. 없으면 사업 노출 방향만으로 0.5 로 본다
  stat_conf        |corr| / full_corr (상한 1). 통계가 없으면 0.3 — '모른다' 는 낮은 확신이다
  fund_relevance   사업 노출 중요도. 정의가 없으면 none(0.2)
  current_relevance 드라이버가 역사적 극단이면 1.0, 아니면 0.7

통계 부호와 사업 부호가 다르면 점수를 깎고 sign_conflict 를 남긴다. 어느
쪽이 맞다고 단정하지 않는다. 숫자는 전부 intelligence.yaml 에서 온다.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from ..config.registry import get_intelligence_config
from ..models.common import ScoreBreakdown, ScoreContribution, direction_for
from ..models.intelligence import StockExposure, StockImpact, StockMeta

ENGINE_VERSION = "0.1.0"


def impact_for(
    meta: StockMeta,
    exposure: StockExposure,
    driver_id: str,
    driver_label: str,
    shock_z: float,
    percentile: float | None,
    *,
    config_dir=None,
) -> StockImpact | None:
    cfg = get_intelligence_config(config_dir)["impact"]
    row = next((r for r in exposure.rows if r.driver_id == driver_id), None)
    if row is None:
        return None
    if row.corr is None and row.fundamental is None:
        return None

    shock = 100.0 * math.tanh(abs(shock_z) / float(cfg["shock_divisor"]))
    full = float(cfg["stat_conf_full_corr"])
    if row.corr is not None:
        exposure_val = abs(row.corr)
        stat_conf = min(1.0, abs(row.corr) / full)
        stat_sign = 1 if row.corr > 0 else -1
    else:
        exposure_val = float(cfg["no_stat_exposure"])
        stat_conf = float(cfg["no_stat_confidence"])
        stat_sign = row.fundamental.direction if row.fundamental else 1

    rel_map = cfg["fund_relevance"]
    fund_rel = float(rel_map[row.fundamental.importance]) if row.fundamental else float(rel_map["none"])
    extreme = percentile is not None and (percentile >= float(cfg["extreme_percentile"]) or percentile <= 100 - float(cfg["extreme_percentile"]))
    cur_rel = float(cfg["current_relevance"]["extreme" if extreme else "normal"])

    sign = row.fundamental.direction if row.fundamental else stat_sign
    min_corr = float(cfg["min_abs_corr_for_sign"])
    conflict = row.fundamental is not None and row.corr is not None and abs(row.corr) >= min_corr and stat_sign != row.fundamental.direction
    penalty = float(cfg["sign_conflict_penalty"]) if conflict else 1.0

    score = shock * exposure_val * stat_conf * fund_rel * cur_rel * penalty
    score = max(0.0, min(100.0, score))
    if score < float(cfg["min_score"]):
        return None

    contribs = [
        ScoreContribution(key="shock", normalized=shock / 100.0, weight=1.0, contribution=shock / 100.0, note=f"드라이버 z {shock_z:+.2f} → tanh"),
        ScoreContribution(key="exposure", normalized=exposure_val, weight=1.0, contribution=exposure_val, note=f"{exposure.primary_window}일 상관 {row.corr:+.2f}" if row.corr is not None else "통계 없음 — 사업 노출만"),
        ScoreContribution(key="stat_confidence", normalized=stat_conf, weight=1.0, contribution=stat_conf, note="|상관| / 기준 상관"),
        ScoreContribution(key="fund_relevance", normalized=fund_rel, weight=1.0, contribution=fund_rel, note=(f"사업 노출 {row.fundamental.kind} {row.fundamental.importance}" if row.fundamental else "사업 노출 정의 없음")),
        ScoreContribution(key="current_relevance", normalized=cur_rel, weight=1.0, contribution=cur_rel, note=("드라이버가 역사적 극단" if extreme else "드라이버 백분위 보통")),
    ]
    if conflict:
        contribs.append(ScoreContribution(key="sign_conflict", normalized=penalty, weight=1.0, contribution=penalty, note="통계 부호 ≠ 사업 부호"))

    direction = direction_for(shock_z * sign, deadband=float(cfg["direction_deadband"]))
    rationale = row.fundamental.rationale if row.fundamental else "통계 관계만 있다 — 사업 구조상 근거는 정의되지 않았다"
    return StockImpact(
        stock_id=meta.id, stock_name=meta.name, driver_id=driver_id, driver_label=driver_label,
        shock_z=shock_z, exposure=exposure_val * sign, stat_confidence=stat_conf, fund_relevance=fund_rel,
        current_relevance=cur_rel, score=score, direction=direction, sign_conflict=conflict,
        breakdown=ScoreBreakdown.build(value=score, method="stock_impact_v1", contributions=contribs),
        rationale=rationale,
    )


def compute_impacts(
    stocks: Sequence[StockMeta],
    exposures: Mapping[str, StockExposure],
    drivers: Sequence[tuple[str, str, float, float | None]],
    *,
    config_dir=None,
) -> list[StockImpact]:
    """drivers: (id, label, z, percentile). 점수 내림차순."""
    out: list[StockImpact] = []
    for meta in stocks:
        exp = exposures.get(meta.id)
        if exp is None:
            continue
        for driver_id, label, z, pct in drivers:
            imp = impact_for(meta, exp, driver_id, label, z, pct, config_dir=config_dir)
            if imp is not None:
                out.append(imp)
    out.sort(key=lambda i: -i.score)
    return out
