"""
Semiconductor Intelligence (2026-09-16 신설).

국내 시장 특성상 별도 모듈이다. 메모리 가격(있으면) · 글로벌 peer · 국내
종목 · EPS 방향을 한 상자에 놓고 **같은 방향인가** 만 묻는다. 방향 합의는
-1~+1 이고, 메모리 현물이 없으면 그 칸은 None 이며 문장이 그것을 말한다.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..config.registry import get_intelligence_config
from .alternative_data import FREQ_KO
from ..models.intelligence import AltDataPoint, AnalystSnapshot, SemiconductorIntelligence, StockRow

ENGINE_VERSION = "0.1.0"


def _direction(zs: Sequence[float | None], min_abs: float) -> float | None:
    vals = [z for z in zs if z is not None and abs(z) >= min_abs]
    if not vals:
        return None
    return sum(1.0 if z > 0 else -1.0 for z in vals) / len(vals)


def _word(d: float | None) -> str:
    if d is None:
        return "판단 불가"
    if d >= 0.5:
        return "상승 합의"
    if d <= -0.5:
        return "하락 합의"
    return "혼조"


def build_semiconductor(
    alt_points: Mapping[str, AltDataPoint],
    stock_rows: Mapping[str, StockRow],
    analyst: Mapping[str, AnalystSnapshot],
    *,
    config_dir=None,
) -> SemiconductorIntelligence:
    cfg = get_intelligence_config(config_dir)["semiconductor"]
    min_abs = float(cfg["direction_min_abs_z"])
    memory = [alt_points[i] for i in cfg["memory"] if i in alt_points]
    peers = [alt_points[i] for i in cfg["peers"] if i in alt_points]
    korea = [stock_rows[i] for i in cfg["korea"] if i in stock_rows]

    mem_dir = _direction([p.z for p in memory if p.quality in ("OK", "PARTIAL")], min_abs)
    peer_dir = _direction([p.z for p in peers if p.quality in ("OK", "PARTIAL")], min_abs)
    kr_dir = _direction([r.z for r in korea], min_abs)
    eps = [analyst[i].eps_revision_1m for i in cfg["korea"] if i in analyst and analyst[i].available]
    eps_dir = _direction([e / 2.0 if e is not None else None for e in eps], 0.5)  # 1% 리비전 = 0.5 로 환산

    missing = [p.label for p in memory if p.quality == "MISSING"]
    # 값은 있지만 z 가 없는 것(봉 부족·분기 추정)은 '없음' 이 아니라 '방향 판단 보류' 다
    pending = [p for p in memory if p.quality != "MISSING" and p.z is None]
    parts = [f"글로벌 peer {_word(peer_dir)}", f"국내 반도체 {_word(kr_dir)}"]
    parts.append(f"메모리 현물 {_word(mem_dir)}" if mem_dir is not None else ("메모리 현물 방향 미정(봉 부족)" if pending else "메모리 현물 데이터 없음"))
    parts.append(f"EPS 리비전 {_word(eps_dir)}" if eps_dir is not None else "컨센서스 데이터 없음")
    agree = [d for d in (peer_dir, kr_dir, mem_dir, eps_dir) if d is not None]
    if len(agree) >= 2 and all(d >= 0.5 for d in agree):
        verdict = "확보된 신호가 전부 상승 방향이다."
    elif len(agree) >= 2 and all(d <= -0.5 for d in agree):
        verdict = "확보된 신호가 전부 하락 방향이다."
    elif len(agree) >= 2:
        verdict = "신호가 엇갈린다 — 가격·peer·실적이 같은 방향이 아니다."
    else:
        verdict = "방향을 말할 만큼 신호가 없다."
    interpretation = " · ".join(parts) + ". " + verdict
    if missing:
        interpretation += f" 메모리 가격({', '.join(missing)})은 공개 API 가 없어 CSV 를 넣기 전까지 비어 있다."
    if pending:
        short = [p for p in pending if p.frequency == "daily"]
        lowf = [p for p in pending if p.frequency != "daily"]
        if short:
            n = min(p.observations for p in short)
            interpretation += f" {'·'.join(p.label.split(' (')[0] for p in short)}은 값은 있으나 봉이 {n}/20 이라 z 가 없다 — 방향 계산은 봉이 차면 들어간다."
        if lowf:
            interpretation += f" {'·'.join(p.label.split(' (')[0] for p in lowf)}은 {FREQ_KO.get(lowf[0].frequency, lowf[0].frequency)} 추정치라 방향 계산에 넣지 않는다."
    return SemiconductorIntelligence(
        memory=memory, peers=peers, korea=korea, peer_direction=peer_dir, korea_direction=kr_dir,
        memory_direction=mem_dir, eps_direction=eps_dir, interpretation=interpretation, missing=missing,
    )
