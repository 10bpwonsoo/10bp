"""
Price vs Fundamental Divergence (2026-09-16 신설).

기존 DivergenceEngine 의 철학(두 신호를 같은 눈금에, 지속 2틱, severity =
tanh·지속)을 종목 계층에 옮긴다. 기존 divergence.py 는 손대지 않고
severity 계산 함수만 가져다 쓴다.

패턴
  가격↓/EPS↑  가격↑/EPS↓  가격↓/TP↑  가격↑/TP↓  (컨센서스 있을 때만)
  가격↓/원자재 순풍  가격↑/산업데이터↓          (사업 노출 × 드라이버 z)
  업종↑/종목↓  업종↓/종목↑                      (상대 z)
  가격↓/외국인 매수, 가격↑/외국인 매도            → 수급 데이터가 없어 지금은 생성되지 않는다
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Mapping, Sequence

from ..config.registry import get_intelligence_config, get_stock_exposures
from ..models.intelligence import (
    AnalystSnapshot, DivergenceSide, StockDivergence, StockExposure, StockFeature, StockMeta,
)
from ..models.market import MarketFeature

ENGINE_VERSION = "0.1.0"


def _sev(gap: float, duration: int, divisor: float) -> float:
    base = 100.0 * math.tanh(gap / divisor)
    return max(0.0, min(100.0, base * min(1.5, 1.0 + 0.1 * (duration - 1))))


def detect_stock_divergences(
    stocks: Sequence[StockMeta],
    stock_features: Mapping[str, StockFeature],
    driver_features: Mapping[str, MarketFeature],
    exposures: Mapping[str, StockExposure],
    analyst: Mapping[str, AnalystSnapshot],
    labels: Mapping[str, str],
    as_of: datetime,
    *,
    previous: Sequence[StockDivergence] = (),
    config_dir=None,
) -> list[StockDivergence]:
    cfg = get_intelligence_config(config_dir)["stock_divergence"]
    p_min, eps_min, tp_min = float(cfg["price_min_abs_z"]), float(cfg["eps_min_pct"]), float(cfg["tp_min_pct"])
    rel_min, com_min, div = float(cfg["relative_min_abs_z"]), float(cfg["commodity_min_abs_z"]), float(cfg["severity_divisor"])
    min_dur = int(cfg["min_duration"])
    fundamentals = get_stock_exposures(config_dir)
    prior = {d.id: d for d in previous}

    candidates: list[tuple[str, str, StockMeta, DivergenceSide, DivergenceSide, float, str]] = []
    for meta in stocks:
        f = stock_features.get(meta.id)
        if f is None:
            continue
        pz5 = f.price.z_5d
        p1m = f.price.ret_20d
        a = analyst.get(meta.id)

        # 가격 vs EPS / TP (1개월 기준)
        if a and a.available and p1m is not None:
            if a.eps_revision_1m is not None and abs(a.eps_revision_1m) >= eps_min and abs(p1m) >= 2.0 and (p1m > 0) != (a.eps_revision_1m > 0):
                kind = "PRICE_DOWN_EPS_UP" if p1m < 0 else "PRICE_UP_EPS_DOWN"
                candidates.append((f"{kind}:{meta.id}", kind, meta,
                    DivergenceSide(name="가격 1M", value=p1m, display=f"{p1m:+.1f}%"),
                    DivergenceSide(name="EPS 리비전 1M", value=a.eps_revision_1m, display=f"{a.eps_revision_1m:+.1f}%"),
                    abs(p1m) / 5.0 + abs(a.eps_revision_1m) / 5.0,
                    f"{meta.name}: 한 달간 가격은 {p1m:+.1f}% 인데 EPS 컨센서스는 {a.eps_revision_1m:+.1f}% 로 반대 방향이다. "
                    + ("실적 기대가 올라가는데 가격이 못 따라오거나, 가격이 다른 것을 보고 있다." if p1m < 0 else "가격이 실적 기대 없이 오르고 있다 — 근거를 확인해야 한다.")))
            if a.tp_change_1m is not None and abs(a.tp_change_1m) >= tp_min and abs(p1m) >= 2.0 and (p1m > 0) != (a.tp_change_1m > 0):
                kind = "PRICE_DOWN_TP_UP" if p1m < 0 else "PRICE_UP_TP_DOWN"
                candidates.append((f"{kind}:{meta.id}", kind, meta,
                    DivergenceSide(name="가격 1M", value=p1m, display=f"{p1m:+.1f}%"),
                    DivergenceSide(name="목표가 변화 1M", value=a.tp_change_1m, display=f"{a.tp_change_1m:+.1f}%"),
                    abs(p1m) / 5.0 + abs(a.tp_change_1m) / 5.0,
                    f"{meta.name}: 가격 {p1m:+.1f}% 와 목표가 컨센서스 {a.tp_change_1m:+.1f}% 의 방향이 다르다."))

        # 가격 vs 원자재 순풍 / 산업 데이터 (5일 창)
        if pz5 is not None and abs(pz5) >= p_min:
            for did, e in fundamentals.get(meta.id, {}).items():
                dz = driver_features.get(did).z_5d if driver_features.get(did) else None
                if dz is None or abs(dz) < com_min:
                    continue
                tail = dz * e.direction  # +면 순풍
                if tail > 0 and pz5 < 0:
                    kind = "PRICE_DOWN_COMMODITY_TAILWIND"
                    text = f"{meta.name}: {labels.get(did, did)} 가 5일간 {dz:+.1f}σ 움직여 사업상 순풍({e.kind}: {e.rationale})인데 주가는 {pz5:+.1f}σ 다."
                elif tail < 0 and pz5 > 0:
                    kind = "PRICE_UP_INDUSTRY_DOWN"
                    text = f"{meta.name}: {labels.get(did, did)} 가 5일간 {dz:+.1f}σ 로 사업상 역풍({e.kind}: {e.rationale})인데 주가는 {pz5:+.1f}σ 올랐다."
                else:
                    continue
                candidates.append((f"{kind}:{meta.id}:{did}", kind, meta,
                    DivergenceSide(name="가격 5D z", value=pz5, display=f"{pz5:+.1f}σ"),
                    DivergenceSide(name=f"{labels.get(did, did)} 5D z", value=dz, display=f"{dz:+.1f}σ"),
                    abs(pz5) + abs(dz), text))

        # 업종 vs 종목 (상대 z)
        rz = f.relative_z
        sec = f.sector_return_1d
        if rz is not None and abs(rz) >= rel_min and sec is not None and abs(sec) >= 0.5 and (sec > 0) != (rz > 0):
            kind = "SECTOR_UP_STOCK_DOWN" if sec > 0 else "SECTOR_DOWN_STOCK_UP"
            candidates.append((f"{kind}:{meta.id}", kind, meta,
                DivergenceSide(name="업종 평균 1D", value=sec, display=f"{sec:+.2f}%"),
                DivergenceSide(name="상대 z", value=rz, display=f"{rz:+.1f}σ"),
                abs(rz) + abs(sec),
                f"{meta.name}: 업종은 {sec:+.2f}% 인데 이 종목은 시장 대비 {rz:+.1f}σ 로 반대다. 업종 요인이 아닌 종목 고유 요인이다."))

    out: list[StockDivergence] = []
    for key, kind, meta, left, right, gap, text in candidates:
        seen = prior.get(key)
        duration = (seen.duration_periods + 1) if seen else 1
        first = seen.first_detected_at if seen else as_of
        if duration < min_dur:
            # 기존 엔진과 달리 pending 저장소가 없으므로 1틱짜리는 severity 를 낮춰 싣는다.
            # 화면은 '관측 1회' 로 표시한다. 감추면 첫 관측을 영영 못 본다.
            pass
        out.append(StockDivergence(
            id=key, kind=kind, stock_id=meta.id, stock_name=meta.name, as_of=as_of, left=left, right=right,  # type: ignore[arg-type]
            severity=_sev(gap, duration, div) * (1.0 if duration >= min_dur else 0.6),
            duration_periods=duration, first_detected_at=first, explanation=text,
        ))
    out.sort(key=lambda d: -d.severity)
    return out
