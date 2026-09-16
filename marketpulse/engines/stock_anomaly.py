"""
Unusual Move Detector (2026-09-16 신설).

수익률 z · 거래량 z · 상대수익률 z · 뉴스 유무를 조합한다. 수급·일중 범위는
데이터가 없어 missing 에 적힌다. 그래서 이 엔진은 '매집' 같은 주체를
절대 말하지 않는다 — 누가 샀는지 모르는 채로 "설명되지 않는 활동" 까지만
말한다.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Mapping, Sequence

from ..config.registry import get_intelligence_config
from ..models.intelligence import StockAnomaly, StockFeature, StockMeta

ENGINE_VERSION = "0.1.0"


def detect_anomalies(
    stocks: Sequence[StockMeta],
    features: Mapping[str, StockFeature],
    news_counts: Mapping[str, int],
    as_of: datetime,
    *,
    config_dir=None,
) -> list[StockAnomaly]:
    cfg = get_intelligence_config(config_dir)["anomaly"]
    r_min, v_min, rel_min = float(cfg["return_z"]), float(cfg["volume_z"]), float(cfg["relative_z"])
    vol_only_floor = float(cfg["min_return_z_for_volume_only"])
    news_min = int(cfg["news_min_events"])

    out: list[StockAnomaly] = []
    for meta in stocks:
        f = features.get(meta.id)
        if f is None:
            continue
        rz, vz, relz = f.price.z_1d, f.volume_z, f.relative_z
        n_news = int(news_counts.get(meta.id, 0))
        flags: list[str] = []
        if rz is not None and abs(rz) >= r_min:
            flags.append(f"수익률 {rz:+.1f}σ")
        if vz is not None and vz >= v_min and (rz is None or abs(rz) >= vol_only_floor):
            flags.append(f"거래량 {vz:+.1f}σ")
        if relz is not None and abs(relz) >= rel_min:
            flags.append(f"시장 대비 {relz:+.1f}σ")
        missing = ["외국인 수급", "기관 수급", "일중 범위"]
        if f.volume_z is None:
            missing.append("거래량")

        if not flags:
            continue
        has_news = n_news >= news_min
        if vz is not None and vz >= v_min and not has_news:
            label = "UNEXPLAINED_ACTIVITY"
        elif has_news:
            label = "NEWS_DRIVEN_MOVE"
        elif vz is not None and vz >= v_min:
            label = "VOLUME_SPIKE"
        elif relz is not None and abs(relz) >= rel_min:
            label = "RELATIVE_MOVE"
        else:
            label = "RETURN_SPIKE"

        mag = max(abs(rz or 0.0), abs(vz or 0.0), abs(relz or 0.0))
        severity = 100.0 * math.tanh(mag / 3.0)
        if label == "UNEXPLAINED_ACTIVITY":
            note = (
                f"{meta.name}: {' · '.join(flags)}. 테마 기사가 없다. 거래 주체는 알 수 없다 — "
                "수급 데이터가 없어 매수 주체를 말할 수 없고, '매집' 같은 단정은 하지 않는다."
            )
        elif label == "NEWS_DRIVEN_MOVE":
            note = f"{meta.name}: {' · '.join(flags)}. 관련 테마 기사 {n_news}건이 있다 — 기사와 같은 방향인지는 Why 패널에서 확인."
        else:
            note = f"{meta.name}: {' · '.join(flags)}."
        out.append(StockAnomaly(
            stock_id=meta.id, stock_name=meta.name, as_of=as_of, return_z=rz, volume_z=vz, relative_z=relz,
            news_events=n_news, flags=flags, label=label, severity=severity, note=note, missing=missing,  # type: ignore[arg-type]
        ))
    out.sort(key=lambda a: -a.severity)
    return out[: int(cfg["limit"])]
