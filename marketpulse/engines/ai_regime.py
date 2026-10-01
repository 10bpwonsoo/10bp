"""
AI Trade Intelligence — AI 탭의 판정 엔진 (2026-09-29).

시장 온도(공포·탐욕)가 아니라 'AI 트레이드 자체' 를 잰다. 답해야 할 질문:
  1. AI 가 스스로 약해지는가, broad-market risk-off 에 같이 눌리는가  → AI vs MARKET (Nasdaq·S&P 대비 상대 z)
  2. Nasdaq/S&P 대비 outperform / underperform                      → 같은 곳
  3. AI 안에서 어느 segment 가 리더십을 갖는가                        → LEADERSHIP (그룹별 1D/1W/1M 상대 모멘텀)
  4. 랠리·매도의 breadth 가 넓어지는가 좁아지는가                     → BREADTH (5·20일선 상회, 상승 비율, 1주 변화)
  5. 뉴스 내러티브와 가격이 서로 확인하는가                            → NARRATIVE × PRICE 2×2 + 내러티브 driver
  6. 금리·달러·VIX 가 AI 가격을 얼마나 설명하는가                      → MACRO CONFIRMATION
  7. 무엇이 생기면 AI-specific risk-off 로 바꾸는가                    → WHAT CHANGES THE VIEW

바스켓·그룹·임계·증거표는 전부 config/ai_regime.yaml 에 있다. 확률이 아니라 증거 크기. 결측은 분모에서 뺀다.
바스켓 지수는 벤치마크(Nasdaq 100) 달력에 맞춘 구성원 동일가중 일수익의 누적이고, 상대 지수는 그 비율이다.
한국 종목은 자기 달력이라 바스켓에 넣지 않고(메모리 그룹의 두 종목만 예외, 설정 note) 리더십 비교에만 쓴다.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import yaml

from ..config.settings import CONFIG_DIR
from ..models.ai_regime import (
    AiRegime, AiStress, AiVsMarket, Breadth, DriverScore, EvidenceItem, GlobalContext, GroupMomentum, Leadership,
    MacroConfirmation, MacroRow, MemberRow, NarrativeDriver, NarrativePrice, RegimeCheck, StressComponent, TriggerItem,
)
from ..models.common import DataMeta, DataMode, utcnow
from ..models.market import Instrument, MarketFeature, MarketSeries, MarketSnapshot
from ..models.news import NewsEvent
from ..models.theme import ThemeState
from .features import compute_feature
from .sentiment import decay_weight

ExtraZ = Mapping[str, tuple[float | None, float | None, str]]
STATUS_KO = {"CONFIRMED": "확인됨", "UNCONFIRMED": "미확인", "CONTRADICTED": "반박됨"}


@lru_cache(maxsize=4)
def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_ai_regime_config(config_dir: Path | None = None) -> dict:
    return _load((config_dir or CONFIG_DIR) / "ai_regime.yaml")


def basket_instruments(config_dir: Path | None = None) -> list[dict]:
    """설정의 종목 universe(instruments). 바스켓·밸류체인·종목 영향도가 전부 이 목록을 참조하고, 서비스가 이 목록으로 계열을 받는다."""
    cfg = load_ai_regime_config(config_dir)
    seen: dict[str, dict] = {str(m["id"]): dict(m) for m in cfg.get("instruments", [])}
    for g in cfg.get("groups", []):  # 예전 형식(members 가 dict) 호환
        for m in g.get("members", []):
            if isinstance(m, dict):
                seen.setdefault(str(m["id"]), dict(m))
    return list(seen.values())


def _members(g: dict, names: Mapping[str, str]) -> list[dict]:
    """그룹 구성원을 {id, name} 로 정규화 — 설정의 members 는 id 문자열이거나 dict 다."""
    out = []
    for m in g.get("members", []):
        mid = str(m["id"]) if isinstance(m, dict) else str(m)
        out.append({"id": mid, "name": (m.get("name") if isinstance(m, dict) else None) or names.get(mid, mid)})
    return out


# ── 작은 도구 ────────────────────────────────────────────
def _clip(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _sign(v: float | None, flat: float) -> int:
    if v is None or abs(v) < flat:
        return 0
    return 1 if v > 0 else -1


def _strength(score: float, bands: Sequence[dict]) -> str:
    for b in bands:
        if abs(score) >= float(b["min"]):
            return str(b["label"])
    return str(bands[-1]["label"]) if bands else ""


def _r(v: float | None, d: int = 2) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), d)


def _closes(s: MarketSeries) -> list[tuple[date, float]]:
    out: dict[date, float] = {}
    for t, v in zip(s.timestamps, s.values):
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            out[t.date()] = float(v)
    return sorted(out.items())


def _pct(vals: Sequence[float], n: int) -> float | None:
    if len(vals) <= n or vals[-1 - n] == 0:
        return None
    return (vals[-1] / vals[-1 - n] - 1.0) * 100.0


def _feature(iid: str, dates: Sequence[date], vals: Sequence[float], as_of: datetime, window: int) -> MarketFeature | None:
    if len(vals) < 25:
        return None
    ins = Instrument(id=iid, name=iid, asset_class="equity", unit="index")  # type: ignore[arg-type]
    meta = DataMeta(source="derived:ai_basket", mode=DataMode.DELAYED, retrieved_at=utcnow(), as_of=as_of)
    ser = MarketSeries(instrument_id=iid, timestamps=[datetime(d.year, d.month, d.day, tzinfo=as_of.tzinfo) for d in dates], values=list(vals), meta=meta)
    try:
        return compute_feature(ins, ser, window=window)
    except Exception:
        return None


def _zmax(f: MarketFeature | None) -> tuple[float | None, int | None]:
    if f is None:
        return None, None
    z1, z5 = f.z_1d, f.z_5d
    if z1 is None and z5 is None:
        return None, None
    if z5 is None:
        return z1, 1
    if z1 is None:
        return z5, 5
    return (z1, 1) if abs(z1) >= abs(z5) else (z5, 5)


# ── 바스켓·그룹 지수 ───────────────────────────────────────
def _equal_weight_index(members: Mapping[str, list[tuple[date, float]]], calendar: Sequence[date]) -> tuple[list[date], list[float], int]:
    """벤치마크 달력 위의 구성원 동일가중 일수익 누적 지수. 그 날 봉이 없는 구성원은 그 날 빠진다."""
    by_id = {mid: dict(rows) for mid, rows in members.items() if rows}
    prev_close: dict[str, float] = {}
    dates: list[date] = []; vals: list[float] = []
    level = 100.0; used: set[str] = set()
    for d in calendar:
        rets = []
        for mid, m in by_id.items():
            c = m.get(d)
            if c is None:
                continue
            p = prev_close.get(mid)
            if p:
                rets.append(c / p - 1.0); used.add(mid)
            prev_close[mid] = c
        if not dates:
            dates.append(d); vals.append(level); continue
        if rets:
            level *= 1.0 + float(np.mean(rets))
        dates.append(d); vals.append(level)
    return dates, vals, len(used)


def _ratio(da: Sequence[date], va: Sequence[float], db: Sequence[date], vb: Sequence[float]) -> tuple[list[date], list[float]]:
    b = dict(zip(db, vb))
    out_d: list[date] = []; out_v: list[float] = []
    for d, v in zip(da, va):
        bv = b.get(d)
        if bv:
            out_d.append(d); out_v.append(100.0 * v / bv)
    if out_v:
        base = out_v[0]; out_v = [x / base * 100.0 for x in out_v]
    return out_d, out_v


def _member_stats(rows: list[tuple[date, float]], ma_s: int, ma_l: int) -> dict:
    vals = [v for _, v in rows]
    def above(n: int, at: int = 0) -> bool | None:
        end = len(vals) - at
        if end < n or end <= 0:
            return None
        return vals[end - 1] > float(np.mean(vals[end - n:end]))
    return {
        "ret_1d": _pct(vals, 1), "ret_5d": _pct(vals, 5), "ret_21d": _pct(vals, 21),
        "above_ma5": above(ma_s), "above_ma20": above(ma_l), "above_ma20_1w": above(ma_l, 5),
        "advancing": (vals[-1] > vals[-2]) if len(vals) >= 2 else None,
        "last": rows[-1][0].isoformat() if rows else None,
    }


# ── 증거표 ───────────────────────────────────────────────
def _z_of(iid: str, market: MarketSnapshot, extra: ExtraZ, window: str) -> tuple[float | None, int | None, str]:
    f = market.features.get(iid)
    if f is not None:
        z1, z5, layer = f.z_1d, f.z_5d, "market"
    elif iid in extra:
        z1, z5, layer = extra[iid][0], extra[iid][1], extra[iid][2]
    else:
        return None, None, "market"
    if window == "1d" or z5 is None:
        return z1, (1 if z1 is not None else None), layer
    if z1 is None:
        return z5, 5, layer
    return (z1, 1, layer) if abs(z1) >= abs(z5) else (z5, 5, layer)


def _score_table(evidence: Sequence[dict], market: MarketSnapshot, themes: Mapping[str, ThemeState], extra: ExtraZ,
                 by_id: Mapping[str, Instrument], names: Mapping[str, str], narr: Mapping[str, NarrativeDriver],
                 *, z_ref: float, news_ref: float, window: str) -> tuple[list[EvidenceItem], float | None, float]:
    items: list[EvidenceItem] = []
    num = den = tot = 0.0
    for e in evidence:
        sign = int(e.get("sign", 1)); w = float(e.get("weight", 1.0)); tot += w
        if "theme" in e:
            t = themes.get(str(e["theme"]))
            raw = None if t is None else getattr(t, str(e.get("field", "news_sentiment")), None)
            label = str(e.get("label") or f"{e['theme']} 뉴스 톤")
            if raw is None:
                items.append(EvidenceItem(id=f"theme:{e['theme']}", label=label, kind="news", layer="theme", sign=sign, weight=w, available=False, note="뉴스 없음"))
                continue
            c = _clip(sign * float(raw) / news_ref) * w
            items.append(EvidenceItem(id=f"theme:{e['theme']}", label=label, kind="news", layer="theme", value=round(float(raw), 1), sign=sign, weight=w, contribution=round(c, 3), note=str(e.get("note", ""))))
        elif "narrative" in e:
            nd = narr.get(str(e["narrative"]))
            label = f"내러티브 · {nd.label if nd else e['narrative']}"
            if nd is None or nd.tone is None:
                items.append(EvidenceItem(id=f"narr:{e['narrative']}", label=label, kind="news", layer="narrative", sign=sign, weight=w, available=False, note="해당 driver 기사 없음"))
                continue
            c = _clip(sign * nd.tone / news_ref) * w
            items.append(EvidenceItem(id=f"narr:{e['narrative']}", label=label, kind="news", layer="narrative", value=round(nd.tone, 1), sign=sign, weight=w, contribution=round(c, 3), note=f"기사 {nd.count}건"))
        else:
            iid = str(e["id"])
            z, win, layer = _z_of(iid, market, extra, window)
            label = names.get(iid) or (by_id[iid].name if iid in by_id else iid)
            if z is None:
                items.append(EvidenceItem(id=iid, label=label, layer=layer, sign=sign, weight=w, available=False, note=str(e.get("note", "")) or "결측"))  # type: ignore[arg-type]
                continue
            c = _clip(sign * z / z_ref) * w
            items.append(EvidenceItem(id=iid, label=label, layer=layer, value=round(z, 2), window=win, sign=sign, weight=w, contribution=round(c, 3), note=str(e.get("note", ""))))  # type: ignore[arg-type]
        num += c; den += w
    items.sort(key=lambda i: -abs(i.contribution))
    score = round(100.0 * num / den, 1) if den > 0 else None
    return items, score, (round(den / tot, 3) if tot > 0 else 0.0)


# ── 본체 ─────────────────────────────────────────────────
def build_ai_regime(
    market: MarketSnapshot,
    market_series: Mapping[str, MarketSeries],
    basket_series: Mapping[str, MarketSeries],
    themes: Sequence[ThemeState],
    events: Sequence[NewsEvent],
    instruments_by_id: Mapping[str, Instrument],
    *,
    market_label: str,
    market_confidence: float,
    thermometer: float | None = None,
    band: str | None = None,
    extra_z: ExtraZ | None = None,
    extra_names: Mapping[str, str] | None = None,
    investment: object | None = None,
    as_of: datetime | None = None,
    config_dir: Path | None = None,
) -> AiRegime:
    cfg = load_ai_regime_config(config_dir)
    as_of = as_of or market.as_of
    z_ref = float(cfg.get("z_ref", 2.0)); news_ref = float(cfg.get("news_ref", 40.0)); window = str(cfg.get("window", "max"))
    bands = list(cfg.get("strength_bands", [])); min_score = float(cfg.get("status", {}).get("min_score", 25))
    zwin = int(market.features[next(iter(market.features))].zscore_window) if market.features else 60
    rel_cfg = cfg.get("relative", {}); flat = float(rel_cfg.get("flat_abs", 0.5)); specific_z = float(rel_cfg.get("specific_z", -1.0))
    macro_band = float(rel_cfg.get("macro_band", -0.5)); outperf = float(rel_cfg.get("outperform_z", 0.5))
    br_cfg = cfg.get("breadth", {}); ma_s = int(br_cfg.get("ma_short", 5)); ma_l = int(br_cfg.get("ma_long", 20))
    low_pct = float(br_cfg.get("low_pct", 50)); drop_pts = float(br_cfg.get("narrowing_drop_pts", 10)); rise_pts = float(br_cfg.get("widening_rise_pts", 10))
    bench = cfg.get("benchmarks", {}); primary = str(bench.get("primary", "NDX")); secondary = str(bench.get("secondary", "SPX"))
    theme_by_id = {t.theme_id: t for t in themes}
    extra: dict[str, tuple[float | None, float | None, str]] = dict(extra_z or {}); names = dict(extra_names or {})
    missing: list[str] = []

    # ── 계열 정리 ──────────────────────────────────────────
    closes = {mid: _closes(s) for mid, s in basket_series.items()}
    bench_closes = {b: _closes(market_series[b]) for b in (primary, secondary, "KOSPI") if b in market_series}
    for b in (primary, secondary):
        if b not in bench_closes:
            missing.append(f"{b} 계열 없음 — 상대 판정 불가")
    inst_names = {str(m["id"]): str(m.get("name", m["id"])) for m in basket_instruments(config_dir)}
    groups_cfg = [{**g, "members": _members(g, inst_names)} for g in cfg.get("groups", [])]; basket_keys = set(cfg.get("basket_groups", []))
    basket_ids: list[str] = []
    for g in groups_cfg:
        if g["key"] in basket_keys:
            for m in g["members"]:
                if m["id"] not in basket_ids:
                    basket_ids.append(str(m["id"]))

    # ── 구성원 통계 ────────────────────────────────────────
    member_rows: list[MemberRow] = []; stats: dict[str, dict] = {}
    seen: set[str] = set()
    for g in groups_cfg:
        for m in g["members"]:
            mid = str(m["id"])
            rows = closes.get(mid) or []
            if mid not in stats:
                stats[mid] = _member_stats(rows, ma_s, ma_l) if len(rows) >= 2 else {}
            if mid in seen:
                continue
            seen.add(mid)
            st = stats[mid]
            if not st:
                member_rows.append(MemberRow(id=mid, name=str(m.get("name", mid)), group=str(g["key"]), available=False, note="계열 없음"))
                continue
            member_rows.append(MemberRow(id=mid, name=str(m.get("name", mid)), group=str(g["key"]), last_date=st["last"], ret_1d=_r(st["ret_1d"]), ret_5d=_r(st["ret_5d"]), ret_21d=_r(st["ret_21d"]),
                                         above_ma5=st["above_ma5"], above_ma20=st["above_ma20"], advancing=st["advancing"]))
    unavailable = [r.id for r in member_rows if not r.available]
    if unavailable:
        missing.append(f"구성원 계열 없음: {', '.join(unavailable)}")

    # ── 바스켓 vs 시장 ─────────────────────────────────────
    avm = AiVsMarket(members_total=len(basket_ids))
    pcal = [d for d, _ in bench_closes.get(primary, [])]
    b_dates: list[date] = []; b_vals: list[float] = []
    if pcal:
        b_dates, b_vals, used = _equal_weight_index({mid: closes.get(mid, []) for mid in basket_ids}, pcal)
        avm.members_used = used; avm.last_date = b_dates[-1].isoformat() if b_dates else None
        bf = _feature("AI_BASKET", b_dates, b_vals, as_of, zwin)
        avm.basket_ret_1d, avm.basket_ret_5d, avm.basket_ret_21d = _r(_pct(b_vals, 1)), _r(_pct(b_vals, 5)), _r(_pct(b_vals, 21))
        avm.basket_z_1d, avm.basket_z_5d = (_r(bf.z_1d), _r(bf.z_5d)) if bf else (None, None)
        z, w = _zmax(bf); avm.basket_z, avm.basket_window = _r(z), w
        pv = [v for _, v in bench_closes[primary]]
        avm.ndx_ret_1d, avm.ndx_ret_5d, avm.ndx_ret_21d = _r(_pct(pv, 1)), _r(_pct(pv, 5)), _r(_pct(pv, 21))
        rd, rv = _ratio(b_dates, b_vals, pcal, pv)
        rf = _feature("AI_REL_NDX", rd, rv, as_of, zwin)
        avm.rel_ndx_1d = _r(_pct(rv, 1)); avm.rel_ndx_5d = _r(_pct(rv, 5)); avm.rel_ndx_21d = _r(_pct(rv, 21))
        avm.rel_ndx_z_1d, avm.rel_ndx_z_5d = (_r(rf.z_1d), _r(rf.z_5d)) if rf else (None, None)
        z, w = _zmax(rf); avm.rel_ndx_z = _r(z)
        if rf is not None:
            extra["AI_REL_NDX"] = (rf.z_1d, rf.z_5d, "basket"); names["AI_REL_NDX"] = "AI 바스켓 / Nasdaq 100 상대"
        if secondary in bench_closes:
            sv = [v for _, v in bench_closes[secondary]]; scal = [d for d, _ in bench_closes[secondary]]
            avm.spx_ret_5d, avm.spx_ret_21d = _r(_pct(sv, 5)), _r(_pct(sv, 21))
            sd, srv = _ratio(b_dates, b_vals, scal, sv)
            sf = _feature("AI_REL_SPX", sd, srv, as_of, zwin)
            avm.rel_spx_5d = _r(_pct(srv, 5)); avm.rel_spx_z_5d = _r(sf.z_5d) if sf else None
            if sf is not None:
                extra["AI_REL_SPX"] = (sf.z_1d, sf.z_5d, "basket"); names["AI_REL_SPX"] = "AI 바스켓 / S&P 500 상대"
        if bf is not None:
            extra["AI_BASKET"] = (bf.z_1d, bf.z_5d, "basket"); names["AI_BASKET"] = "AI 바스켓"
    abs_dir = _sign(avm.basket_z, flat) if avm.basket_z is not None else None
    rel_z5 = avm.rel_ndx_z_5d if avm.rel_ndx_z_5d is not None else avm.rel_ndx_z
    avm.abs_direction = "unknown" if abs_dir is None else {1: "up", -1: "down", 0: "flat"}[abs_dir]
    if rel_z5 is None:
        avm.rel_verdict = "unknown"
    else:
        avm.rel_verdict = "outperform" if rel_z5 >= outperf else ("underperform" if rel_z5 <= -outperf else "inline")
    dir_ko = {"up": "상승", "down": "하락", "flat": "보합", "unknown": "미상"}[avm.abs_direction]
    rel_ko = {"outperform": "outperform", "inline": "시장과 같은 걸음", "underperform": "underperform", "unknown": "판정 불가"}[avm.rel_verdict]
    if avm.basket_z is None:
        avm.sentence = "바스켓 지수를 만들 계열이 부족하다."
    else:
        avm.sentence = (f"AI 바스켓 절대 {dir_ko}({avm.basket_z:+.1f}σ{'·5일' if avm.basket_window == 5 else ''}, 5일 {avm.basket_ret_5d:+.1f}%) · Nasdaq 100 대비 {rel_ko}"
                        f"(5일 {avm.rel_ndx_5d:+.1f}%p, 상대 z {rel_z5:+.1f}σ)" if rel_z5 is not None else f"AI 바스켓 절대 {dir_ko}({avm.basket_z:+.1f}σ) · 상대 판정 불가")
        if avm.abs_direction == "down" and avm.rel_verdict in ("inline", "outperform"):
            avm.sentence += " — 절대 하락이지만 Nasdaq 보다 약하지 않다. AI-specific selloff 가 아니다."
        elif avm.abs_direction == "down" and avm.rel_verdict == "underperform":
            avm.sentence += " — 시장보다 더 빠진다. AI 고유 요인을 의심한다."
        elif avm.abs_direction == "up" and avm.rel_verdict == "underperform":
            avm.sentence += " — 오르지만 시장보다 덜 오른다. 리더십이 AI 밖에 있다."

    # ── 리더십 ─────────────────────────────────────────────
    gm: list[GroupMomentum] = []
    lead_cfg = cfg.get("leadership", {}); lead_min = float(lead_cfg.get("leader_min_rel_pct", 0.5)); lag_max = float(lead_cfg.get("laggard_max_rel_pct", -0.5))
    group_breadth: dict[str, float | None] = {}
    for g in groups_cfg:
        key = str(g["key"]); bkey = str(g.get("benchmark", primary)); ids = [str(m["id"]) for m in g["members"]]
        avail = [i for i in ids if stats.get(i)]
        row = GroupMomentum(key=key, label=str(g["label"]), label_ko=str(g.get("label_ko", g["label"])), benchmark=bkey, in_basket=key in basket_keys, members=len(ids), available=len(avail), note=str(g.get("note", "")))
        bc = bench_closes.get(bkey)
        if bc and avail:
            cal = [d for d, _ in bc]; bv = [v for _, v in bc]
            gd, gv, _u = _equal_weight_index({i: closes.get(i, []) for i in avail}, cal)
            row.ret_1d, row.ret_5d, row.ret_21d = _r(_pct(gv, 1)), _r(_pct(gv, 5)), _r(_pct(gv, 21))
            b1, b5, b21 = _pct(bv, 1), _pct(bv, 5), _pct(bv, 21)
            row.rel_1d = _r(None if row.ret_1d is None or b1 is None else row.ret_1d - b1)
            row.rel_5d = _r(None if row.ret_5d is None or b5 is None else row.ret_5d - b5)
            row.rel_21d = _r(None if row.ret_21d is None or b21 is None else row.ret_21d - b21)
            rd, rv = _ratio(gd, gv, cal, bv)
            rf = _feature(f"AI_{key.upper()}_REL", rd, rv, as_of, zwin)
            if rf is not None:
                row.rel_z_1d, row.rel_z_5d = _r(rf.z_1d), _r(rf.z_5d)
                extra[f"AI_{key.upper()}_REL"] = (rf.z_1d, rf.z_5d, "basket"); names[f"AI_{key.upper()}_REL"] = f"{row.label} / {bkey} 상대"
        elif not bc:
            row.note = (row.note + " · " if row.note else "") + f"벤치마크 {bkey} 계열 없음"
        ma_flags = [stats[i]["above_ma20"] for i in avail if stats[i].get("above_ma20") is not None]
        row.above_ma20_pct = _r(100.0 * sum(1 for f in ma_flags if f) / len(ma_flags), 0) if ma_flags else None
        group_breadth[key] = row.above_ma20_pct
        row.down_1w = sum(1 for i in avail if (stats[i].get("ret_5d") or 0) < 0)
        gm.append(row)
    # 별칭 — 설정 증거표·트리거가 쓰는 파생 z
    alias = {"AI_SEMIS_REL": "AI_SEMIS_COMPUTE_REL", "AI_MEMORY_REL": "AI_MEMORY_REL", "AI_HYPER_REL": "AI_HYPERSCALERS_REL", "AI_SOFT_REL": "AI_SOFTWARE_APP_REL"}
    for a, src in alias.items():
        if src in extra and a not in extra:
            extra[a] = extra[src]; names[a] = names[src]
    ranked = sorted([r for r in gm if r.in_basket and r.rel_5d is not None], key=lambda r: -(r.rel_5d or 0))
    for i, r in enumerate(ranked):
        r.rank_1w = i + 1
    for r in gm:
        if r.rel_5d is None:
            r.role = "unknown"
        elif r.rank_1w == 1 and r.rel_5d >= lead_min:
            r.role = "leader"
        elif r.rel_5d >= lead_min:
            r.role = "strong"
        elif r.rel_5d <= lag_max:
            r.role = "laggard" if r.rank_1w == len(ranked) else "lagging"
        else:
            r.role = "neutral"
    by_1d = sorted([r for r in gm if r.in_basket and r.rel_1d is not None], key=lambda r: -(r.rel_1d or 0))
    by_1m = sorted([r for r in gm if r.in_basket and r.rel_21d is not None], key=lambda r: -(r.rel_21d or 0))
    lead = Leadership(groups=gm, leader_1d=by_1d[0].key if by_1d else None, leader_1w=ranked[0].key if ranked else None,
                      leader_1m=by_1m[0].key if by_1m else None, laggard_1w=ranked[-1].key if ranked else None)
    lab = {r.key: r.label for r in gm}
    if lead.leader_1w and lead.leader_1m:
        if lead.leader_1w == lead.leader_1m:
            lead.rotation = "none" if lead.leader_1d in (None, lead.leader_1w) else "early"
        else:
            lead.rotation = "rotating"
        l1w = next(r for r in gm if r.key == lead.leader_1w); lg = next(r for r in gm if r.key == lead.laggard_1w)
        lead.sentence = f"1주 리더 {lab[lead.leader_1w]}(Nasdaq 대비 {l1w.rel_5d:+.1f}%p) · 1개월 리더 {lab[lead.leader_1m]} · 1주 후미 {lab[lead.laggard_1w]}({lg.rel_5d:+.1f}%p). "
        if (l1w.rel_5d or 0) < lead_min:
            lead.sentence += "모든 그룹이 Nasdaq 에 뒤진다 — 상대적 리더일 뿐 진짜 리더십은 없다. "
        lead.sentence += {"none": "1개월·1주·하루 리더가 같다 — 리더십이 유지된다.", "early": f"하루 리더는 {lab[lead.leader_1d]} — 초기 회전 가능성, 하루로는 단정하지 않는다.",
                          "rotating": f"1개월 → 1주 리더가 {lab[lead.leader_1m]} → {lab[lead.leader_1w]} 로 바뀌었다 — 회전 중."}[lead.rotation]
    else:
        lead.sentence = "그룹 상대 모멘텀을 낼 계열이 부족하다."

    # ── breadth ────────────────────────────────────────────
    br = Breadth(members=len([i for i in basket_ids if stats.get(i)]), by_group=group_breadth)
    def _pct_true(key: str) -> float | None:
        flags = [stats[i][key] for i in basket_ids if stats.get(i) and stats[i].get(key) is not None]
        return _r(100.0 * sum(1 for f in flags if f) / len(flags), 0) if flags else None
    br.above_ma5_pct, br.above_ma20_pct, br.advancing_pct, br.above_ma20_pct_1w_ago = _pct_true("above_ma5"), _pct_true("above_ma20"), _pct_true("advancing"), _pct_true("above_ma20_1w")
    if br.above_ma20_pct is not None and br.above_ma20_pct_1w_ago is not None:
        br.change_1w_pts = _r(br.above_ma20_pct - br.above_ma20_pct_1w_ago, 0)
        br.trend = "narrowing" if br.change_1w_pts <= -drop_pts else ("widening" if br.change_1w_pts >= rise_pts else "stable")
    br.narrowing_with_index_up = bool(abs_dir is not None and abs_dir > 0 and (br.trend == "narrowing" or (br.above_ma20_pct is not None and br.above_ma20_pct < low_pct)))
    if br.above_ma20_pct is None:
        br.sentence = "breadth 를 낼 구성원이 부족하다."
    else:
        br.sentence = (f"바스켓 {br.members}종목 중 20일선 위 {br.above_ma20_pct:.0f}% · 5일선 위 {br.above_ma5_pct:.0f}% · 오늘 상승 {br.advancing_pct:.0f}%"
                       + (f" · 20일선 상회 비율 1주 {br.change_1w_pts:+.0f}%p ({ {'narrowing': '좁아진다', 'widening': '넓어진다', 'stable': '유지', 'unknown': ''}[br.trend]})" if br.change_1w_pts is not None else ""))
        if br.narrowing_with_index_up:
            br.sentence += " — 지수는 오르는데 참여가 줄어든다: Leadership Narrowing."
        elif abs_dir is not None and abs_dir < 0 and br.trend == "narrowing":
            br.sentence += " — 지수와 함께 참여 종목도 줄어든다: 광범위한 매도."
        elif abs_dir is not None and abs_dir < 0 and br.trend == "widening":
            br.sentence += " — 지수는 빠지는데 20일선 위 종목은 늘어난다: 매도가 소수 종목에 집중된다."

    # ── 내러티브 ───────────────────────────────────────────
    ai_events = [e for e in events if "ai" in e.themes]
    narr: dict[str, NarrativeDriver] = {}
    for spec in cfg.get("narrative_drivers", []):
        kws = [str(k).lower() for k in spec.get("keywords", [])]
        hits = [e for e in ai_events if any(k in e.event.lower() for k in kws)]
        tone = None; acc = tot = 0.0
        for e in hits:
            w = decay_weight(e, as_of, config_dir=config_dir); acc += w * float(e.theme_sentiment.get("ai", e.sentiment)); tot += w
        if tot > 0:
            tone = acc / tot
        hits.sort(key=lambda e: -decay_weight(e, as_of, config_dir=config_dir))
        narr[str(spec["key"])] = NarrativeDriver(key=str(spec["key"]), label=str(spec["label"]), label_ko=str(spec.get("label_ko", spec["label"])), tone=_r(tone, 1), count=len(hits), samples=[e.event[:90] for e in hits[:2]])
    ai_theme = theme_by_id.get("ai")
    np_cfg = cfg.get("narrative_price", {}); news_on = float(np_cfg.get("news_on", 10)); price_on = float(np_cfg.get("price_on", 0.5))
    tone_all = None if ai_theme is None else ai_theme.news_sentiment
    nar = NarrativePrice(news_tone=_r(tone_all, 1), news_count=len(ai_events), news_momentum=None if ai_theme is None else _r(ai_theme.news_momentum, 1),
                         price_z=avm.basket_z, price_window=avm.basket_window, drivers=list(narr.values()))
    ns, ps = _sign(tone_all, news_on), _sign(avm.basket_z, price_on)
    if tone_all is None or avm.basket_z is None or ns == 0 or ps == 0:
        nar.quadrant, nar.label = "unclear", "UNCLEAR"
        nar.sentence = ("AI 기사가 없다." if tone_all is None else "바스켓 가격이 없다." if avm.basket_z is None else
                        f"뉴스 톤 {tone_all:+.0f} / 가격 {avm.basket_z:+.1f}σ — 한쪽이 방향을 안 찍어 2×2 에 놓지 못한다.")
    elif ns > 0 and ps > 0:
        nar.quadrant, nar.label, nar.sentence = "confirmed", "CONFIRMED", f"뉴스 {tone_all:+.0f} ↑ · 가격 {avm.basket_z:+.1f}σ ↑ — 내러티브와 가격이 서로 확인한다."
    elif ns > 0 and ps < 0:
        nar.quadrant, nar.label, nar.sentence = "narrative_ahead", "NARRATIVE AHEAD / DISTRIBUTION RISK", f"뉴스 {tone_all:+.0f} ↑ · 가격 {avm.basket_z:+.1f}σ ↓ — 뉴스는 뜨거운데 가격이 따라오지 않는다. 좋은 뉴스에 파는 분배 위험."
    elif ns < 0 and ps > 0:
        nar.quadrant, nar.label, nar.sentence = "price_resilience", "PRICE RESILIENCE", f"뉴스 {tone_all:+.0f} ↓ · 가격 {avm.basket_z:+.1f}σ ↑ — 악재에도 가격이 버틴다."
    else:
        nar.quadrant, nar.label, nar.sentence = "confirmed_risk_off", "CONFIRMED RISK-OFF", f"뉴스 {tone_all:+.0f} ↓ · 가격 {avm.basket_z:+.1f}σ ↓ — 내러티브와 가격이 같이 식는다."

    # ── driver ─────────────────────────────────────────────
    drivers: list[DriverScore] = []
    for did, spec in (cfg.get("drivers") or {}).items():
        items, score, cov = _score_table(spec.get("evidence", []), market, theme_by_id, extra, instruments_by_id, names, narr, z_ref=z_ref, news_ref=news_ref, window=window)
        score = score if score is not None else 0.0
        s_drv = _sign(score, min_score)
        if s_drv == 0:
            status, reason = "UNCONFIRMED", f"증거가 약하다(|{score:+.0f}| < {min_score:.0f})."
        elif abs_dir is None or abs_dir == 0:
            status, reason = "UNCONFIRMED", f"AI 바스켓이 평탄하다({'–' if avm.basket_z is None else f'{avm.basket_z:+.1f}σ'}) — 방향이 아직 가격에 안 찍혔다."
        elif abs_dir == s_drv:
            status, reason = "CONFIRMED", f"driver 방향({'상승' if s_drv > 0 else '하락'})과 AI 바스켓({avm.basket_z:+.1f}σ)이 같다."
        else:
            status, reason = "CONTRADICTED", f"driver 는 AI {'상승' if s_drv > 0 else '하락'} 압력인데 바스켓은 반대({avm.basket_z:+.1f}σ)다."
        drivers.append(DriverScore(id=did, label=str(spec.get("label", did)), label_ko=str(spec.get("label_ko", did)), headline=str(spec.get("headline", did)), score=score, strength=_strength(score, bands),
                                   status=status, status_reason=reason, coverage=cov, evidence=items, implication=str(spec.get("implication", ""))))  # type: ignore[arg-type]
    ranked_d = sorted(drivers, key=lambda d: (0 if d.status == "CONFIRMED" else 1, -abs(d.score)))
    dom = ranked_d[0] if ranked_d else None; run = ranked_d[1] if len(ranked_d) > 1 else None
    margin = round(abs(dom.score) - (abs(run.score) if run else 0.0), 1) if dom else 0.0

    # ── 매크로 확인 ────────────────────────────────────────
    mc_cfg = cfg.get("macro_confirmation", {}); mrows: list[MacroRow] = []
    for r in mc_cfg.get("rows", []):
        z, win, _l = _z_of(str(r["id"]), market, extra, window); exp = int(r.get("sign", -1))
        if z is None:
            mrows.append(MacroRow(key=str(r["key"]), label=str(r["label"]), instrument=str(r["id"]), expected_sign=exp, status="MISSING", note="결측")); continue
        if abs_dir is None or abs_dir == 0:
            st, note = "NEUTRAL", "AI 바스켓이 평탄해 설명할 움직임이 없다"
        elif abs(z) < flat:
            st, note = "DOES_NOT_EXPLAIN", f"이 요인은 움직이지 않았다(|z| < {flat})"
        elif (1 if z > 0 else -1) * exp == abs_dir:
            st, note = "EXPLAINS", f"{'상승' if z > 0 else '하락'}이 AI {'하락' if abs_dir < 0 else '상승'}과 같은 방향으로 작용한다"
        else:
            st, note = "DOES_NOT_EXPLAIN", f"{'상승' if z > 0 else '하락'}은 AI 를 {'올리는' if exp * (1 if z > 0 else -1) > 0 else '내리는'} 쪽인데 바스켓은 반대다"
        mrows.append(MacroRow(key=str(r["key"]), label=str(r["label"]), instrument=str(r["id"]), z=_r(z), window=win, expected_sign=exp, status=st, note=note))  # type: ignore[arg-type]
    mac = MacroConfirmation(rows=mrows, explains=sum(1 for r in mrows if r.status == "EXPLAINS"), evaluated=sum(1 for r in mrows if r.status in ("EXPLAINS", "DOES_NOT_EXPLAIN")))
    min_expl = int(mc_cfg.get("min_explains", 2))
    if abs_dir is None or rel_z5 is None:
        mac.verdict, mac.sentence = "unknown", "바스켓 또는 상대 계열이 없어 판정하지 못한다."
    elif abs_dir >= 0:
        mac.verdict = "not_weak"
        mac.sentence = f"AI 가 약세가 아니다({dir_ko}) — 설명할 약세가 없다. 매크로 {mac.explains}/{mac.evaluated} 요인이 같은 방향."
    elif rel_z5 <= specific_z:
        mac.verdict = "ai_specific"
        mac.sentence = f"AI 가 Nasdaq 보다 현저히 약하다(상대 z {rel_z5:+.1f}σ ≤ {specific_z:+.1f}) — 매크로 {mac.explains}/{mac.evaluated} 요인이 맞아도 AI-specific weakness 다."
    elif mac.explains >= min_expl:
        mac.verdict = "macro_driven"
        mac.sentence = (f"AI 약세가 매크로 {mac.explains}/{mac.evaluated} 요인과 동시에 나온다 — Macro-driven weakness. Nasdaq 대비 {rel_z5:+.1f}σ 로 "
                        + ("같이 눌린다." if rel_z5 >= macro_band else f"시장보다 조금 더 빠지지만 AI-specific 문턱({specific_z:+.1f}σ)은 아니다."))
    else:
        mac.verdict = "mixed"
        mac.sentence = f"매크로가 {mac.explains}/{mac.evaluated} 만 설명하고 상대 z 는 {rel_z5:+.1f}σ — 매크로만으로도, AI 고유만으로도 설명이 안 된다."

    # ── 스트레스 ───────────────────────────────────────────
    hyper = next((r for r in gm if r.key == "hyperscalers"), None); semis = next((r for r in gm if r.key == "semis_compute"), None)
    metrics: dict[str, tuple[float | None, str]] = {
        "AI_REL_NDX_Z5": (rel_z5, "σ"), "AI_SEMIS_REL_Z5": (semis.rel_z_5d if semis else None, "σ"),
        "HYPER_ABOVE_MA20": (hyper.above_ma20_pct if hyper else None, "%"), "SEMI_ABOVE_MA20": (semis.above_ma20_pct if semis else None, "%"),
        "HYPER_DOWN_1W": (float(hyper.down_1w) if hyper and hyper.available else None, f"/{hyper.available if hyper else 0}"), "AI_NEWS_TONE": (tone_all, ""),
    }
    def _disp(key: str) -> str:
        v, u = metrics.get(key, (None, ""))
        return "–" if v is None else (f"{v:+.1f}{u}" if u == "σ" else f"{v:.0f}{u}" if u.startswith(("%", "/")) else f"{v:+.0f}")
    st_cfg = cfg.get("stress", {}); comps: list[StressComponent] = []
    for c in st_cfg.get("components", []):
        v, _u = metrics.get(str(c["metric"]), (None, "")); th = [float(x) for x in c.get("thresholds", [])]
        if v is None:
            comps.append(StressComponent(key=str(c["key"]), label=str(c["label"]), display="–", points=0, note="결측 — 점수에서 뺀다")); continue
        pts = (2 if v <= th[0] else 1 if v <= th[1] else 0) if str(c.get("direction", "below")) == "below" else (2 if v >= th[0] else 1 if v >= th[1] else 0)
        comps.append(StressComponent(key=str(c["key"]), label=str(c["label"]), value=_r(v), display=_disp(str(c["metric"])), points=pts, note=f"임계 {th[0]:g} / {th[1]:g}"))
    avail_c = [c for c in comps if c.value is not None]
    stress = AiStress(components=comps, score=sum(c.points for c in avail_c), max_score=2 * len(avail_c))
    if not avail_c:
        stress.level, stress.sentence = "UNKNOWN", "스트레스 항목을 잴 계열이 없다."
    else:
        # 결측 항목이 있으면 만점 기준으로 비례 환산해 레벨 임계에 댄다
        scaled = stress.score * (2 * len(comps)) / stress.max_score if stress.max_score else 0
        stress.level = next((str(l["label"]) for l in st_cfg.get("levels", []) if scaled >= float(l["min"])), "LOW")  # type: ignore[assignment]
        stress.sentence = f"{stress.score}/{stress.max_score}점 — " + " · ".join(f"{c.label} {c.display}({c.points})" for c in avail_c)

    # ── 판정 ───────────────────────────────────────────────
    reg_cfg = cfg.get("regimes", {}); checks: list[RegimeCheck] = []
    news_val = tone_all
    def _chk(key: str, passed: bool, detail: str) -> None:
        checks.append(RegimeCheck(key=key, label=str(reg_cfg.get(key, {}).get("label", key)), passed=passed, detail=detail))  # type: ignore[arg-type]
    rz = "–" if rel_z5 is None else f"{rel_z5:+.1f}σ"; bz = "–" if avm.basket_z is None else f"{avm.basket_z:+.1f}σ"
    bpct = "–" if br.above_ma20_pct is None else f"{br.above_ma20_pct:.0f}%"; nt = "–" if news_val is None else f"{news_val:+.0f}"
    c1 = rel_z5 is not None and abs_dir is not None and rel_z5 <= specific_z and abs_dir <= 0
    _chk("ai_specific_derisking", c1, f"상대 z {rz} ≤ {specific_z:+.1f} 이고 절대 {dir_ko}(비상승)")
    c4 = nar.quadrant == "narrative_ahead" or (news_val is not None and abs_dir == 0 and news_val >= news_on)
    _chk("narrative_ahead", c4, f"뉴스 톤 {nt} ≥ +{news_on:.0f} 인데 가격 {bz} 은 비상승")
    c2 = abs_dir is not None and abs_dir < 0 and rel_z5 is not None and rel_z5 > specific_z and mac.verdict == "macro_driven"
    _chk("macro_dragged", c2, f"절대 하락({bz}) · 상대 z {rz} > {specific_z:+.1f} · 매크로 설명 {mac.explains}/{mac.evaluated} ≥ {min_expl}")
    c3 = br.narrowing_with_index_up
    _chk("leadership_narrowing", c3, f"절대 상승({bz}) · 20일선 상회 {bpct}(1주 {'–' if br.change_1w_pts is None else f'{br.change_1w_pts:+.0f}%p'}) — 문턱 {low_pct:.0f}% / −{drop_pts:.0f}%p")
    c5 = abs_dir is not None and abs_dir > 0 and (rel_z5 is None or rel_z5 >= -flat) and (br.above_ma20_pct is None or br.above_ma20_pct >= low_pct) and (news_val is None or news_val >= -news_on)
    _chk("confirmed_risk_on", c5, f"절대 상승({bz}) · 상대 {rz} ≥ {-flat:+.1f} · breadth {bpct} ≥ {low_pct:.0f}% · 뉴스 {nt} ≥ −{news_on:.0f}")
    c6 = nar.quadrant == "confirmed_risk_off"
    _chk("confirmed_risk_off", c6, f"뉴스 {nt} ↓ 이고 가격 {bz} ↓")
    c7 = nar.quadrant == "price_resilience"
    _chk("price_resilience", c7, f"뉴스 {nt} ↓ 인데 가격 {bz} ↑")
    regime = next((c.key for c in checks if c.passed), "mixed" if avm.basket_z is not None else "unknown")
    rspec = reg_cfg.get(regime, {"label": "UNKNOWN", "label_ko": "판정 불가", "implication": "바스켓 계열이 없다."})
    regime_label, regime_ko, implication = str(rspec.get("label", regime)), str(rspec.get("label_ko", regime)), str(rspec.get("implication", ""))

    # ── 전환 조건 ──────────────────────────────────────────
    tc = cfg.get("triggers", {}); triggers: list[TriggerItem] = []; release: list[TriggerItem] = []
    def _trig(t: dict) -> TriggerItem:
        v, _u = metrics.get(str(t["metric"]), (None, "")); thr = float(t["value"]); op = str(t["op"])
        met = v is not None and (v <= thr if op == "<=" else v >= thr)
        return TriggerItem(text=str(t["text"]), metric=str(t["metric"]), current=_disp(str(t["metric"])), condition=f"{op} {thr:g}", met=bool(met), measurable=v is not None)
    triggers = [_trig(t) for t in tc.get("to_ai_specific_risk_off", [])]
    release = [_trig(t) for t in tc.get("release", [])]

    # ── 머리글 ─────────────────────────────────────────────
    ctx = GlobalContext(market_label=market_label, market_confidence=round(float(market_confidence), 1), thermometer=_r(thermometer, 0), band=band)
    strength = abs(dom.score) if dom else 0.0
    headline = (f"{regime_ko}. {avm.sentence} "
                + (f"가장 큰 driver 는 {dom.label_ko}({dom.score:+.0f}, {dom.status_reason})" if dom else "")
                + (f" breadth {bpct}({br.trend}). 뉴스×가격 {nar.label}. AI 고유 스트레스 {stress.level}." if avm.basket_z is not None else ""))
    note = ("AI 바스켓은 설정(ai_regime.yaml)의 6개 그룹 구성원 동일가중 일수익 누적 지수(Nasdaq 100 달력)이고, 상대 지수는 바스켓/벤치마크 비율이다. "
            "z 는 시장 계열과 같은 60일 창. driver 점수는 증거표의 가중 clip 평균이며 확률이 아니다. 내러티브 driver 는 제목 키워드 룰 분류다. "
            "시장 판정·온도계는 맥락 입력으로만 붙인다 — AI 판정은 절대 z·상대 z·breadth·뉴스 톤·매크로 설명 여부로만 정한다.")
    result = AiRegime(as_of=as_of, regime=regime, regime_label=regime_label, regime_label_ko=regime_ko, headline=headline, implication=implication, checks=checks,  # type: ignore[arg-type]
                      ai_vs_market=avm, drivers=drivers, dominant=dom.id if dom else None, runner_up=run.id if run else None, margin=margin,
                      signal_strength=round(min(100.0, strength), 1), signal_strength_label=_strength(strength, bands), leadership=lead, breadth=br, narrative=nar,
                      macro=mac, stress=stress, triggers=triggers, release=release, context=ctx, members=member_rows, missing=missing, note=note)
    # ── 밸류체인 · 펀더멘털 확인 · 종목 영향도 (같은 입력 위의 확장 층) ──
    from .ai_value_chain import extend_with_value_chain

    extend_with_value_chain(result, cfg, market=market, extra=extra, names=names, closes=closes, stats=stats, bench_closes=bench_closes, ai_events=ai_events,
                            narr=narr, themes=theme_by_id, investment=investment, inst_names=inst_names, instruments_by_id=instruments_by_id, as_of=as_of, zwin=zwin, config_dir=config_dir)
    # ── AI SENTIMENT · GREED & FEAR (2026-09-30) — 위 값들을 0~100 하나로 합친 현재 상태 지표. 새 판정을 만들지 않는다 ──
    from .ai_sentiment import build_ai_sentiment

    build_ai_sentiment(result, cfg, ai_events=ai_events, as_of=as_of, closes=closes, basket_ids=basket_ids, bench=bench_closes.get(primary, []), market_series=market_series,
                       instruments_by_id=instruments_by_id, zwin=zwin, ma_s=ma_s, ma_l=ma_l, config_dir=config_dir)
    # ── AI VS MARKET → WHAT IS DRIVING AI 표시 층 (2026-09-30): 4개 핵심 판단 · driver 카드 라벨 · DRIVER VERDICT. 점수는 그대로 ──
    from .ai_driver_view import annotate_driver_view

    annotate_driver_view(result, cfg)
    # ── AI CHAIN VIEW (2026-10-01): 전파 · 리더십 · 반도체 확인을 한 흐름으로 — 재표현만 ──
    from .ai_chain_view import build_chain_view

    result.chain_view = build_chain_view(result, cfg)
    return result
