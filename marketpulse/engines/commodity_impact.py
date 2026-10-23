"""
Commodity → Industry → Stock (2026-09-16 신설).

원자재가 움직였을 때 어느 산업의 어느 종목이 **어느 경로로** 영향받는지.
"구리 상승 = 전력기기 수혜" 로 뭉개지 않는다. 종목마다 매출/원가/수요 노출
(stock_exposures.yaml)이 다르고, 그 노출 × 원자재 방향이 기대 효과다.
기대 효과 옆에 실제 반응(오늘 z)을 놓아 확인/무반응/불일치를 판정한다.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..config.registry import get_intelligence_config, get_stock_exposures
from ..models.common import direction_for
from ..models.intelligence import CommodityImpactRow, CommodityStockLink, StockExposure, StockFeature, StockMeta
from ..models.market import MarketFeature

ENGINE_VERSION = "0.1.0"

_INDUSTRY_LABEL = {
    "refining": "정유", "petrochemical": "석유화학", "airline": "항공", "steel": "철강", "nonferrous": "비철",
    "power_equipment": "전력기기", "battery": "2차전지", "auto": "자동차", "shipbuilding": "조선",
    "dry_bulk": "벌크 해운", "container_shipping": "컨테이너 해운", "utility": "유틸리티", "food": "식품",
    "nuclear_power": "원전", "memory": "메모리", "equipment": "반도체 장비", "synthetic_rubber": "합성고무",
}


def build_commodity_impact(
    stocks: Sequence[StockMeta],
    features: Mapping[str, MarketFeature],
    stock_features: Mapping[str, StockFeature],
    exposures: Mapping[str, StockExposure],
    labels: Mapping[str, str],
    displays: Mapping[str, str],
    rollover: Mapping[str, bool],
    *,
    config_dir=None,
) -> list[CommodityImpactRow]:
    cfg = get_intelligence_config(config_dir)["commodity_impact"]
    fundamentals = get_stock_exposures(config_dir)
    min_z = float(cfg["min_abs_z"])
    by_id = {s.id: s for s in stocks}

    rows: list[CommodityImpactRow] = []
    for cid in cfg["commodities"]:
        f = features.get(cid)
        if f is None or f.z_1d is None or abs(f.z_1d) < min_z:
            continue
        z = f.z_1d
        links: list[CommodityStockLink] = []
        industries: list[str] = []
        for sid, fund in fundamentals.items():
            e = fund.get(cid)
            meta = by_id.get(sid)
            if e is None or meta is None:
                continue
            exp = exposures.get(sid)
            corr = next((r.corr for r in exp.rows if r.driver_id == cid), None) if exp else None
            sf = stock_features.get(sid)
            react = sf.price.z_1d if sf else None
            expected = direction_for(z * e.direction, deadband=0.3)
            if react is None:
                agreement = "unknown"
            elif abs(react) < 0.5:
                agreement = "muted"
            elif (react > 0) == (expected == "up"):
                agreement = "confirmed"
            else:
                agreement = "mismatch"
            links.append(CommodityStockLink(
                stock_id=sid, stock_name=meta.name, kind=e.kind, direction=e.direction, importance=e.importance,
                rationale=e.rationale, stat_corr=corr, price_reaction_z=react, expected_effect=expected, agreement=agreement,  # type: ignore[arg-type]
            ))
            lab = _INDUSTRY_LABEL.get(meta.industry, meta.industry)
            if lab not in industries:
                industries.append(lab)
        if not links:
            continue
        imp_rank = {"high": 0, "medium": 1, "low": 2}
        links.sort(key=lambda l: (imp_rank[l.importance], l.stock_name))
        rows.append(CommodityImpactRow(
            commodity_id=cid, label=labels.get(cid, cid), z=z, change_1d_display=displays.get(cid, ""),
            change_1w=f.ret_5d, industries=industries, links=links, rollover_suspect=bool(rollover.get(cid)),
            note=("선물 롤오버 가능성 — 확인 전까지 충격으로 단정하지 않는다." if rollover.get(cid) else ""),
        ))
    rows.sort(key=lambda r: -abs(r.z))
    return rows[: int(cfg["limit"])]
