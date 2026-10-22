"""
MARKET TONE SNAPSHOT (2026-10-07) — 실시간 2 의 MARKET REGIME HISTORY 와 TODAY'S MARKET DRIVERS 사이.

실시간 탭의 온도계(SentimentThermometer)를 **그대로** 받는다 — composite · price · news · 재료 값 · 1주 전은 전부 그 객체의 값이고
여기서 다시 계산하지 않는다(두 탭의 숫자가 다를 수 없다). 이 모듈이 하는 일은 config/cockpit.yaml `tone` 의 taxonomy·의미·템플릿으로
상태 라벨, 재료의 투자적 의미, 1주 변화 읽기, 가격 vs 뉴스, regime 확인(CONFIRMED / PARTIAL / DIVERGING), 2문장 읽기를 만드는 것뿐이다.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..models.cockpit import MarketTone, ToneChange, ToneComponent
from ..models.thermometer import SentimentThermometer
from .korean import fix_particles


def _state(cfg: Mapping, v: float | None) -> Mapping:
    if v is None:
        return {"key": "UNKNOWN", "label": "UNKNOWN", "ko": "측정 불가", "dir": 0}
    for st in cfg.get("states", []):
        if v >= float(st["min"]):
            return st
    return cfg.get("states", [{}])[-1]


def _tier(cfg: Mapping, v: float | None) -> str:
    if v is None:
        return "missing"
    strong, mild = float(cfg["component_bands"]["strong"]), float(cfg["component_bands"]["mild"])
    if v >= strong:
        return "up"
    if v >= mild:
        return "mild_up"
    if v <= -strong:
        return "down"
    if v <= -mild:
        return "mild_down"
    return "flat"


def _join(names: Sequence[str]) -> str:
    return "·".join(names)


def build_market_tone(thermo: SentimentThermometer | None, cfg: Mapping, *, regime_key: str | None, regime_label: str | None, history_points: Sequence[object] = ()) -> MarketTone | None:
    """history_points = 저장된 daily snapshot sequence(StateHistoryPoint, 날짜순). composite 1주 전의 보조 출처 — 재계산이 아니라 저장된 값이다."""
    if thermo is None:
        return None
    week_ago_composite = thermo.composite_week_ago; week_ago_source = str(thermo.week_ago_source); week_ago_as_of = thermo.week_ago_as_of
    week_ago_basis = str((cfg.get("change") or {}).get("basis_thermometer", "thermometer"))
    if week_ago_composite is None and len(history_points) >= 6:
        pt = history_points[-6]
        if getattr(pt, "composite", None) is not None:
            week_ago_composite = float(pt.composite); week_ago_source = "history"; week_ago_as_of = getattr(pt, "as_of", None)
            week_ago_basis = str((cfg.get("change") or {}).get("basis_history", "history"))
    if week_ago_composite is None:
        week_ago_basis = ""
    comp_cfg = cfg.get("components", {}) or {}
    words = cfg.get("state_words", {}) or {}
    st = _state(cfg, thermo.composite)
    # ── 재료: 현재값 + 1주 전 + 의미 ───────────────────────
    comps: list[ToneComponent] = []
    for c in thermo.components:
        spec = comp_cfg.get(c.key) or {}
        tier = _tier(cfg, c.value)
        meaning = str(cfg.get("missing_meaning", "데이터 없음")) if c.value is None else str(spec.get(tier, c.label))
        chg = None if c.value is None or c.week_ago is None else round(c.value - c.week_ago, 1)
        comps.append(ToneComponent(key=c.key, label=str(spec.get("label", c.label)), label_ko=str(spec.get("ko", c.label)), value=None if c.value is None else round(c.value, 1),
                                   week_ago=None if c.week_ago is None else round(c.week_ago, 1), change_1w=chg, state=str(words.get(tier, tier.upper())), meaning=meaning))
    # ── 1주 변화가 큰 재료 ≤3 ──────────────────────────────
    ch_cfg = cfg.get("changed", {}) or {}
    cands = [c for c in comps if c.change_1w is not None and abs(c.change_1w) >= float(ch_cfg.get("min_abs", 10))]
    cands.sort(key=lambda c: -abs(c.change_1w or 0))
    changed: list[ToneChange] = []
    for c in cands[: int(ch_cfg.get("max", 3))]:
        a, b = c.week_ago or 0.0, c.value or 0.0
        if a < 0 <= b and b >= float(cfg["component_bands"]["mild"]):
            m = ch_cfg.get("flip_up", "회복")
        elif a > 0 >= b and b <= -float(cfg["component_bands"]["mild"]):
            m = ch_cfg.get("flip_down", "악화")
        elif b > a:
            m = ch_cfg.get("up_strong" if (b - a) >= 2 * float(ch_cfg.get("min_abs", 10)) else "up", "회복")
        else:
            m = ch_cfg.get("down_strong" if (a - b) >= 2 * float(ch_cfg.get("min_abs", 10)) else "down", "악화")
        changed.append(ToneChange(key=c.key, label=c.label, from_value=a, to_value=b, meaning=str(m)))
    # ── 가격 / 뉴스 ─────────────────────────────────────────
    price_read = str((cfg.get("price_read") or {}).get(_tier(cfg, thermo.price), ""))
    news_read = str((cfg.get("news_read") or {}).get(_tier(cfg, thermo.news), ""))
    gcfg = cfg.get("gap", {}) or {}
    if thermo.price is None or thermo.news is None:
        g = gcfg.get("missing", {})
    elif abs(thermo.price - thermo.news) < float(gcfg.get("threshold", 10)):
        g = gcfg.get("aligned", {})
    elif thermo.price > thermo.news:
        g = gcfg.get("price_lead_up" if thermo.price >= 0 else "news_lead_down", {})
    else:
        g = gcfg.get("news_lead_up" if thermo.news >= 0 else "price_lead_down", {})
    # ── 1주 변화 읽기 ───────────────────────────────────────
    ccfg = cfg.get("change", {}) or {}
    change_1w = None if thermo.composite is None or week_ago_composite is None else round(thermo.composite - week_ago_composite, 1)
    prev_st = _state(cfg, week_ago_composite)
    if change_1w is None:
        change_read = str(ccfg.get("none", ""))
    else:
        fast, small = float(ccfg.get("fast", 20)), float(ccfg.get("small", 8))
        crossed = prev_st.get("key") != st.get("key")
        if change_1w >= fast:
            key = "fast_up" if crossed else "fast_up_same"
        elif change_1w <= -fast:
            key = "fast_down" if crossed else "fast_down_same"
        elif crossed and change_1w > 0:
            key = "cross_up"
        elif crossed and change_1w < 0:
            key = "cross_down"
        elif change_1w >= small:
            key = "up"
        elif change_1w <= -small:
            key = "down"
        else:
            key = "flat"
        change_read = fix_particles(str(ccfg.get(key, "")).format(**{"from": prev_st.get("ko", ""), "to": st.get("ko", "")}))
    # ── regime 확인 ─────────────────────────────────────────
    conf_cfg = cfg.get("confirmation", {}) or {}
    expected = (conf_cfg.get("expected") or {})
    tone_dir = int(st.get("dir", 0))
    if thermo.composite is None or not regime_key:
        confirmation, cread = "UNKNOWN", str(conf_cfg.get("unknown", ""))
    else:
        exp = int(expected.get(regime_key, 0))
        if exp == tone_dir:
            confirmation, key = "CONFIRMED", "confirmed"
        elif exp != 0 and tone_dir == 0:
            confirmation, key = "PARTIAL", "partial_regime_ahead"
        elif exp == 0 and tone_dir != 0:
            confirmation, key = "PARTIAL", "partial_tone_ahead"
        else:
            confirmation, key = "DIVERGING", "diverging"
        cread = fix_particles(str(conf_cfg.get(key, "")).format(regime=regime_label or regime_key, tone_ko=st.get("ko", "")))
    # ── MARKET TONE READ (≤2문장, 숫자 재낭독 없음) ─────────
    rcfg = cfg.get("read", {}) or {}
    supports = [c for c in comps if c.value is not None and c.value >= float(cfg["component_bands"]["mild"])]
    pressures = [c for c in comps if c.value is not None and c.value <= -float(cfg["component_bands"]["mild"])]
    supports.sort(key=lambda c: -(c.value or 0)); pressures.sort(key=lambda c: (c.value or 0))
    sup = _join([c.label_ko or c.label for c in supports[:2]]); pre = _join([c.label_ko or c.label for c in pressures[:2]])
    sup_chg = [c.change_1w for c in supports[:2] if c.change_1w is not None]
    sup_trend = "changed_up" if sup_chg and sum(sup_chg) / len(sup_chg) >= float(ccfg.get("small", 8)) else "changed_down" if sup_chg and sum(sup_chg) / len(sup_chg) <= -float(ccfg.get("small", 8)) else "changed_flat"
    d = tone_dir
    if thermo.composite is None:
        first = ""
    elif d > 0:
        tail = str(rcfg.get("risk_on_pressure_tail", "")).format(pressure=pre) if pre else str(rcfg.get("risk_on_no_pressure_tail", ""))
        first = str(rcfg.get("risk_on", "")).format(support=sup or "가격·위험선호", pressure_tail=tail)
    elif d < 0:
        tail = str(rcfg.get("risk_off_support_tail", "")).format(support=sup) if sup else str(rcfg.get("risk_off_no_support_tail", ""))
        first = str(rcfg.get("risk_off", "")).format(pressure=pre or "위험회피 신호", support_tail=tail)
    elif sup and pre:
        first = str(rcfg.get("support_pressure_neutral", "")).format(support=sup, changed_support=str(rcfg.get(sup_trend, "")), pressure=pre)
    elif sup:
        first = str(rcfg.get("support_only_neutral", "")).format(support=sup, changed_support=str(rcfg.get(sup_trend, "")))
    elif pre:
        first = str(rcfg.get("pressure_only_neutral", "")).format(pressure=pre)
    else:
        first = str(rcfg.get("none_neutral", ""))
    trend = "up" if change_1w is not None and change_1w >= float(ccfg.get("small", 8)) else "down" if change_1w is not None and change_1w <= -float(ccfg.get("small", 8)) else "flat"
    second = str(rcfg.get(f"second_{'risk_on' if d > 0 else 'risk_off' if d < 0 else 'neutral'}_{trend}", ""))
    read = fix_particles(" ".join(x for x in (first, second) if x))
    return MarketTone(
        composite=None if thermo.composite is None else round(thermo.composite, 1), state=str(st.get("key", "UNKNOWN")), state_label=str(st.get("label", "")), state_ko=str(st.get("ko", "")),
        band=thermo.band, band_label=thermo.band_label, composite_week_ago=None if week_ago_composite is None else round(week_ago_composite, 1), change_1w=change_1w,
        change_read=change_read, week_ago_source=week_ago_source, week_ago_as_of=week_ago_as_of, week_ago_basis=week_ago_basis,
        price=None if thermo.price is None else round(thermo.price, 1), price_read=price_read, news=None if thermo.news is None else round(thermo.news, 1), news_read=news_read,
        news_events=int(getattr(thermo, "news_events", 0) or 0), gap_label=str(g.get("label", "")), gap_read=str(g.get("read", "")), confidence=round(float(thermo.confidence), 1),
        components=comps, changed=changed, regime_key=regime_key or "", regime_label=regime_label or "", confirmation=confirmation, confirmation_read=cread, read=read,
        subtitle=str(cfg.get("subtitle", "")),
        note=("실시간 탭의 온도계와 같은 source 다 — 종합·가격·뉴스·재료 값과 1주 전은 다시 계산하지 않았다. 모든 값은 -100~+100 눈금이고 위험선호(뜨거운) 쪽이 + 다. "
              "REGIME CONFIRMATION 은 regime 이 기대하는 방향과 현재 tone 방향의 일치 여부이지 확률이 아니다."),
    )
