"""
Alternative Data Pulse (2026-09-16 신설).

대체데이터 하나를 '시세' 가 아니라 '왜 중요한가 + 누가 영향받나' 와 함께
한 줄로 만든다. feature 는 기존 FeatureEngine 그대로다. 데이터가 없는
항목도 줄을 남긴다 — quality=MISSING 으로. 없는 것을 감추면 화면이
"이 정도면 다 본 것" 이라는 거짓 안도감을 준다.

품질 검사
  stale            마지막 봉이 stale_days 보다 오래됨
  rollover_suspect 선물 연속 계열에서 하루 |z| ≥ 임계. 실제 충격일 수도 있어
                   버리지 않고 표시만 한다. 다음 봉이 되돌리면 롤오버였던 것이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from ..config.registry import get_intelligence_config
from ..models.intelligence import AltDataPoint, AltInstrument, StockMeta
from ..models.market import MarketFeature, MarketSeries

ENGINE_VERSION = "0.1.0"


def build_alt_points(
    alternative: Sequence[AltInstrument],
    features: Mapping[str, MarketFeature],
    series_by_id: Mapping[str, MarketSeries],
    stocks_by_id: Mapping[str, StockMeta],
    as_of: datetime,
    *,
    previous: Mapping[str, AltDataPoint] | None = None,
    config_dir=None,
) -> list[AltDataPoint]:
    cfg = get_intelligence_config(config_dir)["alternative"]
    stale_after = timedelta(days=int(cfg["stale_days"]))
    roll_z = float(cfg["rollover_suspect_z"])
    order = {g: i for i, g in enumerate(cfg["groups"])}
    revert_ratio = float(cfg.get("rollover_revert_ratio", 0.5))
    prev = previous or {}

    out: list[AltDataPoint] = []
    for a in alternative:
        names = [stocks_by_id[s].name for s in a.affected if s in stocks_by_id]
        f = features.get(a.id)
        s = series_by_id.get(a.id)
        if f is None or s is None:
            reason = "CSV 로만 받는 지표 — 파일이 없다" if all(src.provider == "csv" for src in a.sources) else "공급자 실패"
            out.append(AltDataPoint(
                id=a.id, label=a.name, group=a.group, unit=a.unit, quality="MISSING", source_type=a.source_type,
                proxy_for=a.proxy_for, why=a.why, affected=list(a.affected), affected_names=names,
                note=f"데이터 없음 — {reason}. 억지로 채우지 않았다.",
            ))
            continue
        stale = (as_of - s.as_of) > stale_after if as_of.tzinfo and s.as_of.tzinfo else False
        quality = "STALE" if (stale or s.meta.quality.value == "STALE") else ("PARTIAL" if f.z_1d is None else "OK")
        rollover = bool(a.futures and f.z_1d is not None and abs(f.z_1d) >= roll_z)
        note = ""
        if rollover:
            note = f"하루 |z| {abs(f.z_1d):.1f} — 선물 롤오버 가능성. 실제 충격인지 다음 봉으로 확인."
        # 직전 실행이 롤오버를 의심했고 그 뒤 새 봉이 왔으면, 되돌렸는지 이어졌는지 말한다
        followup = None
        pv = prev.get(a.id)
        if pv is not None and pv.rollover_suspect and pv.z is not None and pv.as_of is not None and s.as_of.date() > pv.as_of.date() and f.z_1d is not None:
            if (f.z_1d * pv.z) < 0 and abs(f.z_1d) >= revert_ratio * abs(pv.z):
                followup = "reverted"
                note = (note + " " if note else "") + f"전일 급변({pv.z:+.1f}σ)이 다음 봉에서 되돌려졌다 — 일회성 급변(오류·일시 충격)이었다. 롤오버 단차라면 되돌리지 않는다."
            else:
                followup = "persisted"
                note = (note + " " if note else "") + f"전일 급변({pv.z:+.1f}σ)이 다음 봉에서 되돌려지지 않았다 — 일회성 오류는 아니다. 실제 수요 충격과 월물 교체(롤오버) 단차 둘 다 이렇게 남으므로 어느 쪽인지는 이 데이터만으로 가리지 못한다."
        if a.proxy_for:
            note = (note + " " if note else "") + f"대리 지표: {a.proxy_for}."
        out.append(AltDataPoint(
            id=a.id, label=a.name, group=a.group, value=s.last, unit=a.unit,
            change_1d=f.ret_1d, change_1w=f.ret_5d, change_1m=f.ret_20d, change_3m=f.ret_3m,
            z=f.z_1d, percentile=f.percentile_1y, percentile_observations=f.percentile_observations,
            quality=quality, stale=stale, rollover_suspect=rollover, rollover_followup=followup, source=s.meta.source,  # type: ignore[arg-type]
            source_type=a.source_type, proxy_for=a.proxy_for, why=a.why, affected=list(a.affected),
            affected_names=names, as_of=s.as_of, note=note,
        ))
    # 그룹 순서, 그 안에서 |z| 큰 순 (결측은 뒤로)
    out.sort(key=lambda p: (order.get(p.group, 99), -(abs(p.z) if p.z is not None else -1.0)))
    return out
