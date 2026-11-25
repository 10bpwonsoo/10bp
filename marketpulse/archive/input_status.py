"""
입력 상태 판정 — 계열마다 OK · STALE · MISSING, 그리고 그날 스냅샷을 FULL 로 만들 수 있는지(gate) (2026-11-25).

왜 필요한가. 공급처가 막힌 날 두 가지가 섞인다 — ① 아예 못 받은 계열(MISSING) ② 받았지만 마지막 봉이 빠진 계열(STALE:
공급처가 최신 일봉 없이 응답했거나, 원래 며칠 늦는 대체 경로에서 받은 것). ②를 그대로 쓰면 **전날 종가가 오늘 종가처럼**
계산에 들어간다. 그래서 기준 시각(cutoff)에 '나와 있어야 할 마지막 봉' 을 계열마다 따져 본다.

    behind = 그 계열의 (cutoff 로 자른) 마지막 봉 뒤로, 같은 규칙(archive.pit)으로 이미 공개됐어야 할 평일 봉이 몇 개인가
             (config/collection.yaml market_holidays 의 휴장일은 세지 않는다)
    OK      behind == 0
    STALE   behind >= 1  → 계산에서 뺀다(결측). 값을 당겨 쓰지 않는다
    MISSING 받지 못함

한 시장의 계열이 전부 같은 날에 멈춰 있으면(5개 이상) 휴장으로 본다(CLOSED_SUSPECT — OK 로 두되 보고서에 따로 적는다).
달력에 없는 휴장일을 STALE 로 잘못 빼지 않기 위해서다. 일부만 멈춰 있으면 그 일부가 STALE 이다.

핵심 계열(gate.must · gate.core)이 모자라면 PARTIAL — 그날은 별도 저장하고 공식 regime 판정을 보류한다(backfill.build_partial).
이 모듈은 값을 고치지 않는다. 판정만 한다.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..models.market import MarketSeries
from .pit import availability_lag, bar_available, cut_series

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "collection.yaml"
GROUPS = ("base", "universe", "basket")
#: 일봉 시장 데이터가 아닌 출처 — 메모리 현물 · 계약가처럼 주 · 월 단위로 손으로 넣는 파일. 날짜 간격으로 STALE 을 가리지 않는다
NOT_JUDGED = frozenset({"csv", "csv_base", "store"})


def load_collection_config(path: Path | None = None) -> dict[str, Any]:
    return yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8")) or {}


def market_of(source: str) -> str:
    """출처 문자열(공급자:심볼) → 휴장일 달력을 고를 시장. 모르면 'US'(미국 상장이 대부분이다)."""
    s = (source or "").strip()
    low = s.lower()
    if low.startswith("derived:"):
        return "DERIVED"
    if low.startswith("fred:"):
        return "FRED"
    prov, _, sym = low.partition(":")
    if prov == "yahoo":
        if sym.endswith("=x"):
            return "FX"
        if sym.endswith((".ks", ".kq")) or sym.startswith(("^ks", "^kq")):
            return "KR"
        if sym.endswith(".hk") or sym in ("^hsi", "^hsce"):
            return "HK"
        if sym.endswith((".ss", ".sz")):
            return "CN"
        if sym.endswith(".t") or sym == "^n225":
            return "JP"
        if sym in ("^stoxx50e",) or sym.endswith((".as", ".de", ".pa", ".l", ".mi", ".sw")):
            return "EU"
        if sym.endswith(".tw") or sym.endswith(".two"):
            return "TW"
        return "US"  # 미국 주식 · ETF · 지수 · 선물(=F) · DX-Y
    if prov == "stooq":
        if sym == "^kospi":
            return "KR"
        if sym == "^nkx":
            return "JP"
        if sym.endswith(".us") or sym in ("^spx", "^ndq", "^dji"):
            return "US"
        return "FX"
    if prov == "twelvedata":
        return "US"
    return "OTHER"


def _holidays(cfg: Mapping[str, Any], market: str) -> set[date]:
    hol = (cfg.get("market_holidays") or {})
    key = {"FRED": "US", "DERIVED": "US", "OTHER": "US", "FX": "__none__"}.get(market, market)
    out: set[date] = set()
    for x in hol.get(key) or []:
        try:
            out.add(date.fromisoformat(str(x)))
        except ValueError:
            continue
    return out


def behind_bars(last: datetime, source: str, cutoff: datetime, *, lags_by_id: Mapping[str, timedelta] | None = None, holidays: set[date] | None = None) -> int:
    """마지막 봉 뒤로, cutoff 에 이미 공개됐어야 할 평일 봉의 수(휴장일 제외). 0 이면 최신이다."""
    lag = availability_lag(source, lags_by_id, cutoff=cutoff)
    n = 0
    d = last.date() + timedelta(days=1)
    end = cutoff.astimezone(last.tzinfo).date() + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5 and d not in (holidays or set()):
            cand = last.replace(year=d.year, month=d.month, day=d.day)
            if bar_available(cand, lag, cutoff):
                n += 1
        d += timedelta(days=1)
    return n


def _load(path: Path) -> dict[str, MarketSeries]:
    if not path.is_file():
        return {}
    return {k: MarketSeries.model_validate(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def assess(inputs: Path, cutoff: datetime, *, expected: Mapping[str, list[str]] | None = None, cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """
    수집 폴더(series_base · series_universe · series_basket)의 계열 상태와 gate 판정.

    expected  묶음별로 있어야 할 계열 id 목록. 없으면 수집기가 남긴 collect_status.json 의 expected 를, 그것도 없으면 받은 것만 본다.
    """
    cfg = dict(cfg or load_collection_config())
    if expected is None:
        try:
            expected = json.loads((inputs / "collect_status.json").read_text(encoding="utf-8")).get("expected")
        except (OSError, ValueError):
            expected = None
    series: dict[str, dict[str, Any]] = {}
    rows: list[tuple[str, str, str, int]] = []  # (group, id, market, behind) — 받은 계열
    for g in GROUPS:
        raw = _load(inputs / f"series_{g}.json")
        cut = cut_series(raw, cutoff)
        lags = {iid: availability_lag(str(s.meta.source or ""), cutoff=cutoff) for iid, s in raw.items() if not str(s.meta.source or "").lower().startswith("derived:")}
        out: dict[str, Any] = {}
        for iid, s in raw.items():
            src = str(s.meta.source or "")
            mk = market_of(src)
            c = cut.get(iid)
            if c is None or not c.timestamps:
                out[iid] = {"status": "MISSING", "reason": "기준 시각에 공개된 봉이 없다", "source": src, "market": mk, "raw_last_bar": s.timestamps[-1].isoformat() if s.timestamps else None}
                continue
            if src.lower().split(":", 1)[0] in NOT_JUDGED:
                out[iid] = {"status": "OK", "last_bar": c.timestamps[-1].isoformat(), "behind": None, "source": src, "market": mk,
                            "note": "수기 · 자체 주기 계열 — 최신 여부를 여기서 판정하지 않는다(엔진이 자기 규칙으로 본다)"}
                continue
            b = behind_bars(c.timestamps[-1], src, cutoff, lags_by_id=lags, holidays=_holidays(cfg, mk))
            out[iid] = {"status": "OK" if b == 0 else "STALE", "last_bar": c.timestamps[-1].isoformat(), "behind": b, "source": src, "market": mk}
            rows.append((g, iid, mk, b))
        for iid in (expected or {}).get(g) or []:
            out.setdefault(iid, {"status": "MISSING", "reason": "받지 못했다"})
        series[g] = out

    # 한 시장이 통째로 같은 날에 멈춰 있으면 휴장으로 본다(달력에 없는 휴장일을 STALE 로 빼지 않는다)
    closed: dict[str, int] = {}
    by_market: dict[str, list[int]] = {}
    for _, _, mk, b in rows:
        by_market.setdefault(mk, []).append(b)
    for mk, bs in by_market.items():
        if mk in ("DERIVED", "OTHER"):
            continue
        if len(bs) >= 5 and min(bs) >= 1:
            closed[mk] = min(bs)
    for g, iid, mk, b in rows:
        if mk in closed and b == closed[mk]:
            series[g][iid].update(status="OK", note="CLOSED_SUSPECT — 이 시장의 계열이 모두 같은 날에 멈춰 있다(휴장으로 봄 · 확인 필요)")
    # 파생 계열은 재료가 OK 가 아니면 같이 내려간다
    for g in GROUPS:
        for iid, r in series[g].items():
            if r.get("market") == "DERIVED" and r["status"] == "STALE":
                import re
                parts = re.findall(r"[A-Z][A-Z0-9_]+", str(r.get("source", "")).split(":", 1)[-1])
                if parts and all(series[g].get(p, {}).get("status") == "OK" for p in parts):
                    r.update(status="OK", note="재료 계열이 모두 최신")

    counts = {g: {k: sum(1 for r in series[g].values() if r["status"] == k) for k in ("OK", "STALE", "MISSING")} for g in GROUPS}
    gate_cfg = cfg.get("gate") or {}
    base = series["base"]
    st = lambda i: (base.get(i) or {}).get("status", "MISSING")
    must_bad = {i: st(i) for i in gate_cfg.get("must") or [] if st(i) != "OK"}
    core = list(gate_cfg.get("core") or [])
    core_bad = {i: st(i) for i in core if st(i) != "OK"}
    ratio = 1.0 if not core else (len(core) - len(core_bad)) / len(core)
    reasons = []
    if must_bad:
        reasons.append("필수 핵심 계열이 최신이 아니다: " + ", ".join(f"{k}({v})" for k, v in must_bad.items()))
    if ratio < float(gate_cfg.get("min_core_ok", 0.8)):
        reasons.append(f"핵심 계열 {len(core) - len(core_bad)}/{len(core)} 만 최신 — 기준 {gate_cfg.get('min_core_ok', 0.8):.0%} 미만")
    drop = {g: sorted(i for i, r in series[g].items() if r["status"] == "STALE") for g in GROUPS}
    return {
        "cutoff": cutoff.isoformat(),
        "counts": counts,
        "gate": {"verdict": "PARTIAL" if reasons else "FULL", "reasons": reasons, "must_not_ok": must_bad, "core_not_ok": core_bad, "core_ok_ratio": round(ratio, 3)},
        "closed_suspect": closed,
        "stale": drop,
        "missing": {g: sorted(i for i, r in series[g].items() if r["status"] == "MISSING") for g in GROUPS},
        "series": series,
    }


def summary_of(status: Mapping[str, Any]) -> dict[str, Any]:
    """저장본 meta 에 넣는 요약(계열별 전체 표는 캡처 폴더 input_status.json 에 남긴다)."""
    return {k: status.get(k) for k in ("cutoff", "counts", "gate", "closed_suspect", "stale", "missing")}
