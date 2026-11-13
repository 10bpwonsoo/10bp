"""
Analyst Intelligence (2026-09-16 신설).

공개 API 가 없다 — Yahoo 컨센서스 엔드포인트는 401, FnGuide·네이버는 이
환경에서 차단이다. 그래서 두 경로만 둔다.
  CSV   data/replay/analyst/<STOCK_ID>.csv
        date,broker,rating,target_price,eps_fy1
  MOCK  scenario.analyst[<STOCK_ID>] 의 리비전 값

둘 다 없으면 available=False 이고 화면은 "데이터 없음" 을 그대로 보인다.
출처가 불확실한 값을 억지로 채우지 않는다 (요구 22).
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

from ..adapters.market.scenario import AnalystSpec
from ..models.intelligence import AnalystSnapshot, StockFeature, StockMeta

ENGINE_VERSION = "0.1.0"


def _quadrant(price_1m: float | None, eps_1m: float | None, min_pct: float) -> str:
    if price_1m is None or eps_1m is None or abs(eps_1m) < min_pct * 0.5:
        return "UNKNOWN"
    p = "UP" if price_1m >= 0 else "DOWN"
    e = "UP" if eps_1m >= 0 else "DOWN"
    return f"PRICE_{p}_EPS_{e}"


def _pct(now: float | None, then: float | None) -> float | None:
    if now is None or then is None or then == 0:
        return None
    return (now / then - 1.0) * 100.0


def from_csv(path: Path, meta: StockMeta, as_of: datetime, price_1m: float | None, min_pct: float) -> AnalystSnapshot:
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                d = datetime.fromisoformat(r["date"]).replace(tzinfo=timezone.utc)
            except Exception:
                continue
            rows.append({
                "date": d, "broker": r.get("broker", ""), "rating": r.get("rating") or None,
                "tp": float(r["target_price"]) if r.get("target_price") else None,
                "eps": float(r["eps_fy1"]) if r.get("eps_fy1") else None,
            })
    rows = [r for r in rows if r["date"] <= as_of]
    rows.sort(key=lambda r: r["date"])
    if not rows:
        return AnalystSnapshot(stock_id=meta.id, stock_name=meta.name, available=False, note=f"{path.name} 에 as_of 이전 행이 없다")

    def consensus_at(when: datetime) -> tuple[float | None, float | None]:
        latest: dict[str, dict] = {}
        for r in rows:
            if r["date"] <= when:
                latest[r["broker"]] = r
        tps = [r["tp"] for r in latest.values() if r["tp"] is not None]
        epss = [r["eps"] for r in latest.values() if r["eps"] is not None]
        return (sum(tps) / len(tps) if tps else None, sum(epss) / len(epss) if epss else None)

    tp_now, eps_now = consensus_at(as_of)
    tp_1w, eps_1w = consensus_at(as_of - timedelta(days=7))
    tp_1m, eps_1m = consensus_at(as_of - timedelta(days=30))
    tp_3m, eps_3m = consensus_at(as_of - timedelta(days=91))
    last = rows[-1]
    brokers = len({r["broker"] for r in rows})
    eps_rev_1m = _pct(eps_now, eps_1m)
    return AnalystSnapshot(
        stock_id=meta.id, stock_name=meta.name, as_of=last["date"], rating=last["rating"],
        target_price=tp_now, tp_change_1w=_pct(tp_now, tp_1w), tp_change_1m=_pct(tp_now, tp_1m), tp_change_3m=_pct(tp_now, tp_3m),
        eps_fy1=eps_now, eps_revision_1w=_pct(eps_now, eps_1w), eps_revision_1m=eps_rev_1m, eps_revision_3m=_pct(eps_now, eps_3m),
        brokers=brokers, price_change_1m=price_1m, quadrant=_quadrant(price_1m, eps_rev_1m, min_pct),  # type: ignore[arg-type]
        source=f"csv:{path.name}", source_type="RESEARCH", available=True,
        note=f"CSV 적재 {brokers}개 증권사 · 마지막 {last['date'].date().isoformat()}",
    )


def from_scenario(spec: AnalystSpec, meta: StockMeta, as_of: datetime, price_1m: float | None, min_pct: float) -> AnalystSnapshot:
    return AnalystSnapshot(
        stock_id=meta.id, stock_name=meta.name, as_of=as_of, rating=spec.rating, rating_change=spec.rating_change,
        target_price=None, tp_change_1w=spec.tp_change_1w, tp_change_1m=spec.tp_change_1m, tp_change_3m=spec.tp_change_3m,
        eps_fy1=None, eps_revision_1w=spec.eps_revision_1w, eps_revision_1m=spec.eps_revision_1m, eps_revision_3m=spec.eps_revision_3m,
        brokers=spec.brokers, price_change_1m=price_1m, quadrant=_quadrant(price_1m, spec.eps_revision_1m, min_pct),  # type: ignore[arg-type]
        source="mock:scenario", source_type="RESEARCH", available=True, note="MOCK 시나리오의 컨센서스 상태",
    )


def build_analyst(
    stocks: Sequence[StockMeta],
    stock_features: Mapping[str, StockFeature],
    as_of: datetime,
    *,
    replay_dir: Path | None = None,
    scenario_specs: Mapping[str, AnalystSpec] | None = None,
    min_pct: float = 2.0,
) -> list[AnalystSnapshot]:
    out: list[AnalystSnapshot] = []
    for meta in stocks:
        f = stock_features.get(meta.id)
        price_1m = f.price.ret_20d if f else None
        if scenario_specs is not None and meta.id in scenario_specs:
            out.append(from_scenario(scenario_specs[meta.id], meta, as_of, price_1m, min_pct))
            continue
        path = (replay_dir / "analyst" / f"{meta.id}.csv") if replay_dir else None
        if path is not None and path.exists():
            out.append(from_csv(path, meta, as_of, price_1m, min_pct))
            continue
        out.append(AnalystSnapshot(
            stock_id=meta.id, stock_name=meta.name, price_change_1m=price_1m, available=False,
            note="컨센서스 데이터 없음 — 공개 API 가 없다. data/replay/analyst/<ID>.csv 를 넣으면 읽는다.",
        ))
    return out
