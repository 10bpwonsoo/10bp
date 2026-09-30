"""
AI SENTIMENT · GREED & FEAR (2026-09-30) — AI 투자 테마 내부의 투자심리와 실제 시장 확인 강도를 0~100 하나로 잰다.

일반 시장 Fear & Greed 가 아니다. 상승 확률·매수 확률·수익률 전망도 아니다.
  NARRATIVE(AI 뉴스 톤·driver 톤) + PRICE(바스켓 z·상대 z·1M) + BREADTH(5/20일선·상승 비율)
  + FUNDAMENTALS(HBM·범용 메모리·EPS·반도체 확인) + MACRO(금리·실질금리·달러·VIX·신용·지수)
를 config/ai_regime.yaml `sentiment` 의 가중으로 합친 '현재 상태' 지표다.

원칙: 모든 입력은 이미 계산된 AI Trade Intelligence 값(AiRegime)에서 가져온다 — 새 판정을 만들지 않는다.
각 입력은 clip(값/ref) 를 0~100 으로 옮기고(50 = 중립), 결측은 0 이 아니라 분모에서 뺀다.
1M 이력은 같은 공식을 시계열(바스켓·벤치마크 종가, 시장 계열, 기사 시각)로 하루씩 되돌려 만든다. 이력이 없는
구성요소(메모리 데이터·EPS 처럼 날짜별 계열이 없는 것)는 이력의 basis 에서 빼고 그렇게 적는다 — 채워 넣지 않는다.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Mapping, Sequence

from ..models.ai_regime import AiRegime, AiSentiment, SentimentComponent, SentimentFactor, SentimentHistory, SentimentInput, SentimentPoint
from ..models.common import DataMeta, DataMode, utcnow
from ..models.market import Instrument, MarketSeries
from ..models.news import NewsEvent
from .ai_regime import _clip, _equal_weight_index, _feature, _member_stats, _pct, _r, _ratio, _zmax
from .features import compute_feature
from .korean import fix_particles
from .sentiment import decay_weight

Values = Mapping[str, tuple[float | None, str, str]]  # input id → (값, 표시, 결측/비고)


# ── 점수 도구 ─────────────────────────────────────────────
def _score(v: float | None, ref: float) -> float | None:
    return None if v is None else round(50.0 + 50.0 * _clip(v / ref), 1)


def _band(cfg: Mapping, score: float | None) -> Mapping:
    if score is None:
        return {"key": "UNKNOWN", "label": "–", "ko": "측정 불가"}
    for b in cfg.get("bands", []):
        if score >= float(b.get("min", 0)):
            return b
    bands = list(cfg.get("bands", []))
    return bands[-1] if bands else {"key": "UNKNOWN", "label": "–", "ko": ""}


def _tier(cfg: Mapping, score: float | None) -> str:
    key = str(_band(cfg, score).get("key", "UNKNOWN"))
    return "high" if key in ("GREED", "EXTREME_GREED") else "low" if key in ("FEAR", "EXTREME_FEAR") else "mid"


def _wmean(pairs: Sequence[tuple[float | None, float]]) -> tuple[float | None, float]:
    """(값, 가중치) 의 가중 평균과 확보율. 결측은 분모에서 뺀다."""
    tot = sum(w for _, w in pairs)
    avail = [(v, w) for v, w in pairs if v is not None]
    if not avail or tot <= 0:
        return None, 0.0
    den = sum(w for _, w in avail)
    return round(sum(v * w for v, w in avail) / den, 1), round(den / tot, 3)


def _fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "–"
    if unit == "σ":
        return f"{v:+.1f}σ"
    if unit == "%":
        return f"{v:.0f}%"
    if unit == "%p":
        return f"{v:+.1f}%"
    return f"{v:+.0f}"


# ── 뉴스 톤 (오늘과 이력이 같은 함수를 쓴다) ────────────────
def ai_tone(events: Sequence[NewsEvent], as_of: datetime, *, config_dir=None) -> tuple[float | None, int]:
    """AI 태그 기사의 감쇠 가중 AI 톤(theme_sentiment['ai'], 없으면 기사 감성). (톤, 기사 수)."""
    acc = tot = 0.0; n = 0
    for e in events:
        if as_of is not None and e.timestamp > as_of:
            continue
        w = decay_weight(e, as_of, config_dir=config_dir)
        if w <= 0:
            continue
        acc += w * float(e.theme_sentiment.get("ai", e.sentiment)); tot += w; n += 1
    return ((acc / tot) if tot > 0 else None), n


def _driver_tone(events: Sequence[NewsEvent], keywords: Sequence[str], as_of: datetime, *, config_dir=None) -> tuple[float | None, int]:
    kws = [str(k).lower() for k in keywords]
    hits = [e for e in events if any(k in e.event.lower() for k in kws)]
    return ai_tone(hits, as_of, config_dir=config_dir)


# ── 입력값 → 구성요소 (순수 함수) ──────────────────────────
def score_components(cfg: Mapping, values: Values) -> list[SentimentComponent]:
    comps: list[SentimentComponent] = []
    for c in cfg.get("components", []):
        inputs: list[SentimentInput] = []
        for spec in c.get("inputs", []):
            iid = str(spec["id"]); w = float(spec.get("weight", 1.0))
            v, disp, note = values.get(iid, (None, "–", "결측"))
            src = str(spec.get("source", ""))
            if v is None:
                sc = None
            elif src == "breadth_pct":
                sc = round(max(0.0, min(100.0, float(v))), 1)
            elif src == "fundamental_confirmation":
                sc = round(float(v), 1)
            else:
                sc = _score(float(v), float(spec.get("ref", 1.0)))
            inputs.append(SentimentInput(id=iid, label=str(spec["label"]), label_ko=str(spec.get("label_ko", "")), component=str(c["key"]), value=_r(v), display=disp,
                                         score=sc, weight=w, available=sc is not None, note=note if sc is None else ""))
        score, cov = _wmean([(i.score, i.weight) for i in inputs])
        band = _band(cfg, score)
        reads = c.get("read", {}) or {}
        comps.append(SentimentComponent(key=str(c["key"]), label=str(c["label"]), label_ko=str(c.get("label_ko", c["label"])), score=score, state=str(band.get("key", "UNKNOWN")),
                                        state_label=str(band.get("label", "–")), read=str(reads.get(_tier(cfg, score), "")) if score is not None else "입력이 없어 잴 수 없다",
                                        weight=float(c.get("weight", 1.0)), coverage=cov, inputs=inputs))
    return comps


def index_of(cfg: Mapping, comps: Sequence[SentimentComponent], keys: Sequence[str] | None = None) -> tuple[float | None, float]:
    use = [c for c in comps if keys is None or c.key in keys]
    if keys is not None and any(c.score is None for c in use):
        return None, 0.0  # basis 를 정한 이력에서는 한 구성요소라도 비면 그 날은 비운다
    return _wmean([(c.score, c.weight) for c in use])


# ── 오늘의 입력값 (AiRegime 에서 그대로) ────────────────────
def live_values(cfg: Mapping, r: AiRegime, ai_events: Sequence[NewsEvent], as_of: datetime, *, config_dir=None) -> Values:
    out: dict[str, tuple[float | None, str, str]] = {}
    avm, br, fc = r.ai_vs_market, r.breadth, r.fundamental_confirmation
    narr = {d.key: d for d in r.narrative.drivers}
    stage = {s.key: s for s in r.transmission.stages}
    macro = {m.key: m for m in r.macro.rows}
    min_events = int(cfg.get("min_events", 3))
    tone, n = ai_tone(ai_events, as_of, config_dir=config_dir)
    has_basket = avm.members_used > 0 and avm.basket_z is not None  # 바스켓 지수가 없으면 가격 입력은 전부 결측 — 빈 바스켓의 평탄한 지수를 값으로 읽지 않는다
    for c in cfg.get("components", []):
        for spec in c.get("inputs", []):
            iid = str(spec["id"]); src = str(spec.get("source", ""))
            if src == "news_tone":
                out[iid] = (tone if n >= min_events else None, f"{_fmt(tone, '')} · {n}건" if tone is not None else "–", f"AI 기사 {n}건 < {min_events}" if n < min_events else "")
            elif src == "narrative":
                d = narr.get(str(spec.get("key")))
                out[iid] = (d.tone if d else None, f"{_fmt(d.tone, '')} · {d.count}건" if d and d.tone is not None else "–", "해당 driver 기사 없음" if not d or d.tone is None else "")
            elif src == "basket_z":
                out[iid] = (avm.basket_z, _fmt(avm.basket_z, "σ") + (" (5일)" if avm.basket_window == 5 else ""), "바스켓 계열 없음" if avm.basket_z is None else "")
            elif src == "rel_z":
                z = (avm.rel_ndx_z_5d if avm.rel_ndx_z_5d is not None else avm.rel_ndx_z) if has_basket else None
                out[iid] = (z, _fmt(z, "σ") + " vs NDX", "상대 계열 없음" if z is None else "")
            elif src == "basket_ret_21d":
                v = avm.basket_ret_21d if has_basket else None
                out[iid] = (v, _fmt(v, "%p"), "1개월 이력 없음" if v is None else "")
            elif src == "breadth_pct":
                v = getattr(br, str(spec.get("field", "above_ma20_pct")), None)
                out[iid] = (v, _fmt(v, "%"), "구성원 부족" if v is None else "")
            elif src == "stage":
                s = stage.get(str(spec.get("key")))
                out[iid] = (s.score if s else None, f"{_fmt(s.score, '')} · {s.status}" if s and s.score is not None else (f"{s.status}" if s else "–"), (s.evidence if s else "전파 단계 없음") if not s or s.score is None else "")
            elif src == "fundamental_confirmation":
                lv = (spec.get("levels") or {}).get(fc.level)
                out[iid] = (float(lv) if lv is not None else None, fc.level, "반도체 확인 UNCONFIRMED — 잴 데이터 없음" if lv is None else "")
            elif src == "macro_row":
                m = macro.get(str(spec.get("key")))
                v = None if m is None or m.z is None else m.z * m.expected_sign
                out[iid] = (v, (_fmt(m.z, "σ") + (" (5일)" if m.window == 5 else "")) if m and m.z is not None else "–", "결측" if v is None else "")
            else:
                out[iid] = (None, "–", f"알 수 없는 source {src}")
    return out


# ── 보조 상태 · 구조 · 문장 ─────────────────────────────────
def secondary_state(cfg: Mapping, index: float | None, comps: Sequence[SentimentComponent]) -> tuple[str, str, str]:
    sec = cfg.get("secondary", {}) or {}; gap = float(sec.get("gap", 15)); by = {c.key: c.score for c in comps}
    best: tuple[float, Mapping] | None = None
    for rule in sec.get("rules", []):
        kind = str(rule.get("kind", "gap")); tension: float | None = None
        if kind == "gap":
            a, b = by.get(str(rule.get("a"))), by.get(str(rule.get("b")))
            if a is not None and b is not None and a - b >= gap:
                tension = a - b
        elif kind == "fragile":
            bdt = by.get("breadth")
            if index is not None and bdt is not None and index >= float(rule.get("index_min", 60)) and bdt <= float(rule.get("breadth_max", 50)):
                tension = index - bdt
        elif kind == "cap":
            mac = by.get("macro")
            if index is not None and mac is not None and index >= float(rule.get("index_min", 45)) and mac <= float(rule.get("macro_max", 40)):
                tension = index - mac
        elif kind == "floor":
            mac = by.get("macro")
            if index is not None and mac is not None and index <= float(rule.get("index_max", 55)) and mac >= float(rule.get("macro_min", 60)):
                tension = mac - index
        if tension is not None and (best is None or tension > best[0]):
            best = (tension, rule)
    if best is None:
        none = sec.get("none", {}) or {}
        return "none", str(none.get("label", "BALANCED")), str(none.get("ko", ""))
    return str(best[1]["key"]), str(best[1].get("label", best[1]["key"])), str(best[1].get("ko", ""))


def structure(cfg: Mapping, comps: Sequence[SentimentComponent]) -> tuple[list[SentimentFactor], list[SentimentFactor]]:
    st = cfg.get("structure", {}) or {}; smin = float(st.get("support_min", 60)); pmax = float(st.get("pressure_max", 40)); n = int(st.get("max", 3))
    items = [SentimentFactor(id=i.id, label=i.label, label_ko=i.label_ko, component=c.key, score=float(i.score), display=i.display) for c in comps for i in c.inputs if i.score is not None]
    support = sorted([i for i in items if i.score >= smin], key=lambda i: -i.score)[:n]
    pressure = sorted([i for i in items if i.score <= pmax], key=lambda i: i.score)[:n]
    return support, pressure


def _join(names: Sequence[str]) -> str:
    return " · ".join(names)


def read_sentence(cfg: Mapping, index: float | None, comps: Sequence[SentimentComponent], support: Sequence[SentimentFactor], pressure: Sequence[SentimentFactor], secondary_ko: str, secondary_key: str) -> str:
    t = cfg.get("read", {}) or {}
    if index is None:
        return "입력이 부족해 AI SENTIMENT INDEX 를 내지 못한다."
    strong = [c.label_ko for c in comps if c.score is not None and _tier(cfg, c.score) == "high"]
    weak = [c.label_ko for c in comps if c.score is not None and _tier(cfg, c.score) == "low"]
    if strong and weak:
        s1 = str(t.get("support_and_pressure", "")).format(strong=_join(strong), weak=_join(weak))
    elif strong:
        s1 = str(t.get("support_only", "")).format(strong=_join(strong))
    elif weak:
        s1 = str(t.get("pressure_only", "")).format(weak=_join(weak))
    else:
        s1 = str(t.get("neither", ""))
    parts = [s1]
    if pressure:
        key = "pressure_factors_greed" if index >= 40 else "pressure_factors_fear"
        parts.append(str(t.get(key, "")).format(factors=_join([f.label for f in pressure[:2]])))
    elif support:
        parts.append(str(t.get("support_factors", "")).format(factors=_join([f.label for f in support[:2]])))
    if secondary_key != "none" and secondary_ko:
        parts.append(secondary_ko + ".")
    return fix_particles(" ".join(p for p in parts if p))


# ── 1M 이력 (같은 공식을 하루씩 되돌린다) ────────────────────
def _series_feature(ins: Instrument, rows: Sequence[tuple[date, float]], as_of: datetime, window: int):
    if len(rows) < 25:
        return None
    meta = DataMeta(source="derived:ai_sentiment_replay", mode=DataMode.DELAYED, retrieved_at=utcnow(), as_of=as_of)
    ser = MarketSeries(instrument_id=ins.id, timestamps=[datetime(d.year, d.month, d.day, tzinfo=as_of.tzinfo) for d, _ in rows], values=[v for _, v in rows], meta=meta)
    try:
        return compute_feature(ins, ser, window=window)
    except Exception:
        return None


def replay_history(cfg: Mapping, r: AiRegime, *, closes: Mapping[str, list[tuple[date, float]]], basket_ids: Sequence[str], bench: Sequence[tuple[date, float]],
                   market_series: Mapping[str, MarketSeries], instruments_by_id: Mapping[str, Instrument], ai_events: Sequence[NewsEvent], as_of: datetime, zwin: int,
                   ma_s: int, ma_l: int, config_dir=None) -> SentimentHistory:
    h_cfg = cfg.get("history", {}) or {}; days = int(h_cfg.get("days", 21)); min_days = int(h_cfg.get("min_days", 10)); min_events = int(cfg.get("min_events", 3))
    hist = SentimentHistory(days=days)
    cal = [d for d, _ in bench]
    if len(cal) < days + 1 or not basket_ids:
        hist.note = "벤치마크 달력이 짧거나 바스켓이 없어 1M 이력을 만들지 못한다."
        return hist
    b_dates, b_vals, _u = _equal_weight_index({m: closes.get(m, []) for m in basket_ids}, cal)
    if _u == 0:
        hist.note = "바스켓 구성원 계열이 없어 1M 이력을 만들지 못한다."
        return hist
    r_dates, r_vals = _ratio(b_dates, b_vals, cal, [v for _, v in bench])
    macro_specs = {str(m.key): m for m in r.macro.rows}
    narr_specs = {str(d.key): d for d in r.narrative.drivers}
    narr_kw = {str(s["key"]): [str(k) for k in s.get("keywords", [])] for s in (cfg.get("_narrative_drivers") or [])}
    from .ai_regime import _closes as _series_closes
    macro_closes = {}
    for c in cfg.get("components", []):
        for spec in c.get("inputs", []):
            if spec.get("source") == "macro_row":
                m = macro_specs.get(str(spec.get("key")))
                if m and m.instrument in market_series:
                    macro_closes[str(spec["id"])] = (m, _series_closes(market_series[m.instrument]))
    window_days = cal[-days:]
    points: list[SentimentPoint] = []; per_comp: dict[str, list[float | None]] = {}
    for d in window_days:
        as_of_d = datetime.combine(d, time(23, 59), tzinfo=as_of.tzinfo)
        if d >= as_of.date():
            as_of_d = as_of
        vals: dict[str, tuple[float | None, str, str]] = {}
        # PRICE
        i = next((k for k, dd in enumerate(b_dates) if dd == d), None)
        if i is not None:
            bf = _feature("AI_BASKET", b_dates[: i + 1], b_vals[: i + 1], as_of_d, zwin); z, _w = _zmax(bf)
            vals["basket_price"] = (z, _fmt(z, "σ"), "" if z is not None else "이력 부족")
            vals["basket_1m"] = (_pct(b_vals[: i + 1], 21), "", "")
        j = next((k for k, dd in enumerate(r_dates) if dd == d), None)
        if j is not None:
            rf = _feature("AI_REL_NDX", r_dates[: j + 1], r_vals[: j + 1], as_of_d, zwin)
            rz = (rf.z_5d if rf and rf.z_5d is not None else (rf.z_1d if rf else None))
            vals["relative_strength"] = (rz, _fmt(rz, "σ"), "" if rz is not None else "이력 부족")
        # BREADTH
        flags: dict[str, list[bool]] = {"above_ma20": [], "above_ma5": [], "advancing": []}
        for mid in basket_ids:
            rows = [(dd, v) for dd, v in closes.get(mid, []) if dd <= d]
            if len(rows) < 2:
                continue
            st = _member_stats(rows, ma_s, ma_l)
            for k in flags:
                if st.get(k) is not None:
                    flags[k].append(bool(st[k]))
        for k in flags:
            f = flags[k]; vals[k] = ((100.0 * sum(f) / len(f)) if f else None, "", "" if f else "구성원 없음")
        # MACRO
        for iid, (m, rows) in macro_closes.items():
            sub = [(dd, v) for dd, v in rows if dd <= d]; ins = instruments_by_id.get(m.instrument)
            f = _series_feature(ins, sub, as_of_d, zwin) if ins is not None else None
            z, _w = _zmax(f)
            vals[iid] = (None if z is None else z * m.expected_sign, _fmt(z, "σ"), "" if z is not None else "이력 부족")
        # NARRATIVE (그 날 끝 기준 감쇠 가중 — 오늘과 같은 함수)
        tone, n = ai_tone(ai_events, as_of_d, config_dir=config_dir)
        vals["ai_news_tone"] = (tone if n >= min_events else None, "", "" if n >= min_events else "기사 부족")
        for key, kws in narr_kw.items():
            t, _n = _driver_tone(ai_events, kws, as_of_d, config_dir=config_dir)
            vals[key] = (t, "", "" if t is not None else "기사 없음")
        comps = score_components(cfg, vals)
        for c in comps:
            per_comp.setdefault(c.key, []).append(c.score)
        points.append(SentimentPoint(date=d.isoformat(), components={c.key: c.score for c in comps}))
    basis = [k for k, xs in per_comp.items() if sum(1 for x in xs if x is not None) >= min_days]
    comp_specs = list(cfg.get("components", []))
    for c in comp_specs:
        if c["key"] not in basis:
            n_ok = sum(1 for x in per_comp.get(str(c["key"]), []) if x is not None)
            hist.excluded[str(c["key"])] = "날짜별 계열이 없어 이력을 만들 수 없다" if n_ok == 0 else f"창 안에서 {n_ok}일만 잴 수 있다(기준 {min_days}일)"
    for p in points:
        use = [(p.components.get(k), float(next(c.get("weight", 1.0) for c in comp_specs if c["key"] == k))) for k in basis]
        p.index = None if not basis or any(v is None for v, _ in use) else _wmean(use)[0]
    hist.points = points; hist.basis = basis
    idx = [p.index for p in points if p.index is not None]
    if idx:
        hist.range_min, hist.range_max = min(idx), max(idx)
    if len(points) >= 2 and points[-1].index is not None and points[-2].index is not None:
        hist.change_1d = round(points[-1].index - points[-2].index, 1)
    if len(points) >= 6 and points[-1].index is not None and points[-6].index is not None:
        hist.change_1w = round(points[-1].index - points[-6].index, 1)
    labels = {str(c["key"]): str(c.get("label", c["key"])) for c in comp_specs}
    hist.note = ("1M 이력과 1D/1W 변화는 " + " · ".join(labels.get(k, k) for k in basis) + " 로만 만든 값이다(같은 공식을 하루씩 되돌림)"
                 + (" — " + ", ".join(f"{labels.get(k, k)}: {v}" for k, v in hist.excluded.items()) if hist.excluded else "") + ".") if basis else "이력을 만들 구성요소가 없다."
    return hist


# ── 본체 ─────────────────────────────────────────────────
def build_ai_sentiment(r: AiRegime, cfg_all: Mapping, *, ai_events: Sequence[NewsEvent], as_of: datetime, closes: Mapping[str, list[tuple[date, float]]], basket_ids: Sequence[str],
                       bench: Sequence[tuple[date, float]], market_series: Mapping[str, MarketSeries], instruments_by_id: Mapping[str, Instrument], zwin: int, ma_s: int, ma_l: int,
                       config_dir=None) -> AiSentiment:
    cfg = dict(cfg_all.get("sentiment") or {})
    cfg["_narrative_drivers"] = [s for s in cfg_all.get("narrative_drivers", []) if any(i.get("source") == "narrative" and i.get("key") == s.get("key") for c in cfg.get("components", []) for i in c.get("inputs", []))]
    comps = score_components(cfg, live_values(cfg, r, ai_events, as_of, config_dir=config_dir))
    index, cov = index_of(cfg, comps)
    if index is not None and cov < float(cfg.get("min_coverage", 0.5)):
        index = None
    band = _band(cfg, index)
    sk, sl, sko = secondary_state(cfg, index, comps)
    support, pressure = structure(cfg, comps)
    out = AiSentiment(index=index, state=str(band.get("key", "UNKNOWN")), state_label=str(band.get("label", "–")), state_ko=str(band.get("ko", "")), coverage=cov, components=comps,
                      secondary_key=sk, secondary_label=sl, secondary_ko=sko, support=support, pressure=pressure,
                      bands=[{"key": str(b["key"]), "label": str(b["label"]), "min": float(b["min"])} for b in cfg.get("bands", [])],
                      note="AI 테마 내부의 투자심리와 시장 확인 강도를 합친 현재 상태 지표(0~100)다. 상승 확률·매수 확률·수익률 전망이 아니다. 각 입력은 AI Trade Intelligence 의 값을 clip(값/ref)로 0~100 에 옮긴 것이고 결측은 분모에서 뺀다.")
    out.read = read_sentence(cfg, index, comps, support, pressure, sko, sk)
    r.sentiment = out
    try:
        out.history = replay_history(cfg, r, closes=closes, basket_ids=basket_ids, bench=bench, market_series=market_series, instruments_by_id=instruments_by_id, ai_events=ai_events,
                                     as_of=as_of, zwin=zwin, ma_s=ma_s, ma_l=ma_l, config_dir=config_dir)
    except Exception as exc:  # 이력은 보조 층 — 실패해도 지수는 뜬다
        out.history = SentimentHistory(days=int((cfg.get("history") or {}).get("days", 21)), note=f"1M 이력 계산 실패: {exc}")
    return out
