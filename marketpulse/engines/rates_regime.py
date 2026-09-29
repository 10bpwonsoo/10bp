"""
Inflation & Rates Intelligence — config/rates_regime.yaml 의 표를 실데이터에 대어
driver 점수 · 물가 구성 · 커브 · 명목 분해 · 크로스에셋 확인 · 핵심 괴리 · 시장 함의 · 전환 조건을 만든다.

판정 룰(state_rules)은 건드리지 않는다. 그쪽은 Diagnostics 로 내려간다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.market import Instrument, MarketFeature, MarketSnapshot
from ..models.rates_regime import (
    ComponentScore, ConfirmationRow, CurveView, DriverScore, EvidenceItem, ImplicationRow, KeyDivergence,
    MarketImplication, RateMove, RatesRegime, TenorPoint, TriggerItem, YieldDecomposition,
)
from ..models.theme import ThemeState

ENGINE_VERSION = "0.1.0"
STATUS_KO = {"CONFIRMED": "확인됨", "UNCONFIRMED": "미확인", "CONTRADICTED": "반박됨"}
STATUS_EN = {"CONFIRMED": "Confirmed", "UNCONFIRMED": "Not Confirmed", "CONTRADICTED": "Contradicted"}
ExtraZ = Mapping[str, tuple[float | None, float | None, str]]


@lru_cache(maxsize=4)
def _load(config_dir: Path | None) -> dict:
    return yaml.safe_load(((config_dir or CONFIG_DIR) / "rates_regime.yaml").read_text(encoding="utf-8")) or {}


def load_rates_regime_config(config_dir: Path | None = None) -> dict:
    return _load(config_dir)


def reset_cache() -> None:
    _load.cache_clear()


def _clip(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _feat(iid: str, market: MarketSnapshot) -> MarketFeature | None:
    return market.features.get(iid)


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


def _name(iid: str, by_id: Mapping[str, Instrument], names: Mapping[str, str]) -> str:
    return names.get(iid) or (by_id[iid].name if iid in by_id else iid)


def _strength(score: float, bands: Sequence[dict]) -> str:
    for b in bands:
        if abs(score) >= float(b["min"]):
            return str(b["label"])
    return str(bands[-1]["label"]) if bands else ""


def _sign(v: float | None, flat: float) -> int:
    if v is None or abs(v) < flat:
        return 0
    return 1 if v > 0 else -1


def _score_table(evidence: Sequence[dict], market: MarketSnapshot, themes: Mapping[str, ThemeState], extra: ExtraZ,
                 by_id: Mapping[str, Instrument], names: Mapping[str, str], *, z_ref: float, news_ref: float, window: str
                 ) -> tuple[list[EvidenceItem], float | None, float]:
    """증거표 → (항목, 점수, 확보 비율). 항목이 하나도 없으면 점수 None."""
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
        else:
            iid = str(e["id"])
            z, win, layer = _z_of(iid, market, extra, window)
            label = _name(iid, by_id, names)
            if z is None:
                items.append(EvidenceItem(id=iid, label=label, layer=layer, sign=sign, weight=w, available=False, note=str(e.get("note", "")) or "결측"))  # type: ignore[arg-type]
                continue
            c = _clip(sign * z / z_ref) * w
            items.append(EvidenceItem(id=iid, label=label, layer=layer, value=round(z, 2), window=win, sign=sign, weight=w, contribution=round(c, 3), note=str(e.get("note", ""))))  # type: ignore[arg-type]
        num += c; den += w
    items.sort(key=lambda i: -abs(i.contribution))
    score = round(100.0 * num / den, 1) if den > 0 else None
    return items, score, (round(den / tot, 3) if tot > 0 else 0.0)


def build_rates_regime(
    market: MarketSnapshot,
    themes: Sequence[ThemeState],
    instruments_by_id: Mapping[str, Instrument],
    *,
    extra_z: ExtraZ | None = None,
    extra_names: Mapping[str, str] | None = None,
    config_dir: Path | None = None,
) -> RatesRegime:
    cfg = load_rates_regime_config(config_dir)
    z_ref = float(cfg.get("z_ref", 2.0)); news_ref = float(cfg.get("news_ref", 40.0)); window = str(cfg.get("window", "max"))
    bands = list(cfg.get("strength_bands", []))
    extra = extra_z or {}; names = dict(extra_names or {})
    theme_by_id = {t.theme_id: t for t in themes}
    common = dict(z_ref=z_ref, news_ref=news_ref, window=window)

    # ── 금리 관측 ──────────────────────────────────────────
    rm = cfg.get("rate_move", {}); rid = str(rm.get("instrument", "US10Y")); flat = float(rm.get("flat_abs", 0.5))
    z10, w10, _ = _z_of(rid, market, extra, window)
    f10 = _feat(rid, market)
    direction = "unknown" if z10 is None else ("flat" if abs(z10) < flat else ("up" if z10 > 0 else "down"))
    rate_move = RateMove(instrument=rid, z=None if z10 is None else round(z10, 2), window=w10, direction=direction,  # type: ignore[arg-type]
                         change_5d_bp=None if f10 is None or f10.ret_5d is None else round(f10.ret_5d, 1),
                         level=None if f10 is None or rid not in market.points else round(market.points[rid].value, 3))

    # ── driver ─────────────────────────────────────────────
    min_score = float(cfg.get("status", {}).get("min_score", 25))
    drivers: list[DriverScore] = []
    for did, spec in (cfg.get("drivers") or {}).items():
        items, score, cov = _score_table(spec.get("evidence", []), market, theme_by_id, extra, instruments_by_id, names, **common)
        score = score if score is not None else 0.0
        s_drv, s_rate = _sign(score, min_score), _sign(z10, flat)
        if s_drv == 0:
            status, reason = "UNCONFIRMED", f"증거가 약하다(|{score:+.0f}| < {min_score:.0f})."
        elif s_rate == 0:
            status, reason = "UNCONFIRMED", f"10년 금리가 평탄하다({'–' if z10 is None else f'{z10:+.1f}σ'}) — 방향이 아직 금리에 안 찍혔다."
        elif s_rate == s_drv:
            status, reason = "CONFIRMED", f"driver 방향({'상승' if s_drv > 0 else '하락'})과 10년 금리({z10:+.1f}σ)가 같다."
        else:
            status, reason = "CONTRADICTED", f"driver 는 금리 {'상승' if s_drv > 0 else '하락'} 압력인데 10년 금리는 반대({z10:+.1f}σ)다."
        drivers.append(DriverScore(id=did, label=str(spec.get("label", did)), label_ko=str(spec.get("label_ko", did)), headline=str(spec.get("headline", did)),
                                   score=score, strength=_strength(score, bands), status=status, status_reason=reason, coverage=cov,  # type: ignore[arg-type]
                                   evidence=items, implication=str(spec.get("implication", ""))))
    # 지배 driver: 10년 금리가 방향을 찍었으면 그 방향과 맞는(CONFIRMED) driver 가 먼저, 그 안에서 |점수| 순. 금리와 반대로 가는 driver 는
    # 아무리 커도 '금리를 움직인 원인' 이 될 수 없다 — 그건 확인표·괴리에서 드러난다. 금리가 평탄하면 |점수| 순.
    ranked = sorted(drivers, key=lambda d: (0 if d.status == "CONFIRMED" else 1, -abs(d.score)))
    dom, run = ranked[0], (ranked[1] if len(ranked) > 1 else None)
    margin = round(abs(dom.score) - (abs(run.score) if run else 0.0), 1)
    infl = next(d for d in drivers if d.id == "inflation_repricing")
    infl_status = infl.status if infl.score > 0 or infl.status == "CONTRADICTED" else ("CONTRADICTED" if infl.score <= -min_score and direction == "up" else "UNCONFIRMED")
    if direction == "flat":
        regime_label = f"RATES IN RANGE (LEANING {dom.headline}) — Inflation Repricing {STATUS_EN[infl_status]}"
    elif direction == "unknown":
        regime_label = f"RATE MOVE UNKNOWN — Inflation Repricing {STATUS_EN[infl_status]}"
    else:
        regime_label = f"{dom.headline} — Inflation Repricing {STATUS_EN[infl_status]}"
    headline = (f"금리를 움직이는 증거는 {dom.label_ko} 쪽이 가장 크다({dom.score:+.0f}, {dom.strength})"
                + (f" — {run.label_ko} {run.score:+.0f} 보다 {margin:.0f} 앞선다." if run else ".")
                + f" 물가 리프라이싱은 {STATUS_KO[infl_status]}({infl.score:+.0f}). 상태: {dom.status_reason}")

    # ── 물가 압력 구성 ─────────────────────────────────────
    comps: list[ComponentScore] = []
    for c in cfg.get("inflation_components", []):
        items, score, cov = _score_table(c.get("evidence", []), market, theme_by_id, extra, instruments_by_id, names, **common)
        note = str(c.get("missing_note", ""))
        if score is None:
            t = theme_by_id.get(str(c.get("theme"))) if c.get("theme") else None
            if t is not None and t.news_sentiment is not None:
                note += f" 뉴스 톤 {t.news_sentiment:+.0f}."
            comps.append(ComponentScore(key=c["key"], label=c["label"], label_ko=c.get("label_ko", c["label"]), score=None, status="missing", coverage=0.0, evidence=items, note=note))
            continue
        st = "flat" if abs(score) < min_score else ("up" if score > 0 else "down")
        comps.append(ComponentScore(key=c["key"], label=c["label"], label_ko=c.get("label_ko", c["label"]), score=score, status=st, coverage=cov, evidence=items, note=note if cov < 1 else ""))  # type: ignore[arg-type]

    # ── 커브 ───────────────────────────────────────────────
    cc = cfg.get("curve", {}); cmin = float(cc.get("min_abs", 0.5)); lead_m = float(cc.get("lead_margin", 0.5))
    tenors: list[TenorPoint] = []
    for t in cc.get("tenors", []):
        f = _feat(t["id"], market)
        z, _w, _l = _z_of(t["id"], market, extra, window)
        tenors.append(TenorPoint(id=t["id"], label=t["label"], level=None if t["id"] not in market.points else round(market.points[t["id"]].value, 3),
                                 z_1d=None if f is None else f.z_1d, z_5d=None if f is None else f.z_5d, z=None if z is None else round(z, 2),
                                 change_5d_bp=None if f is None or f.ret_5d is None else round(f.ret_5d, 1)))
    sp_z, _sw, _sl = _z_of(str(cc.get("spread", "CURVE_2S10S")), market, extra, window)
    front = next((t.z for t in tenors if t.label == "2Y"), None); long_ = next((t.z for t in tenors if t.label in ("30Y",)), None) or next((t.z for t in tenors if t.label == "10Y"), None)
    lvl_dir = _sign(z10, cmin)
    if front is None or long_ is None:
        shape, lead, sent = "unknown", "none", "테너가 부족해 커브 모양을 판별하지 못한다."
    else:
        st_sign = _sign(sp_z, cmin)
        # 주도 구간: 전체 움직임 방향(10Y 기준, 없으면 장기물)으로 잰 각 구간의 기여. 단기물이 반대로 가면(트위스트) 그쪽이 아니라 같이 가는 구간이 주도다.
        move_dir = lvl_dir if lvl_dir != 0 else (1 if long_ > 0 else -1)
        front_in, long_in = front * move_dir, long_ * move_dir
        if long_in - front_in >= lead_m:
            lead = "long"
        elif front_in - long_in >= lead_m:
            lead = "front"
        else:
            lead = "parallel"
        if lvl_dir == 0 and st_sign == 0:
            shape, lead = "flat", "none"
        elif st_sign > 0:
            shape = "bear_steepening" if long_ > 0 else "bull_steepening"
        elif st_sign < 0:
            shape = "bear_flattening" if front > 0 else "bull_flattening"
        else:
            shape, lead = ("parallel_up" if lvl_dir > 0 else "parallel_down"), "parallel"
        ko = {"bear_steepening": "베어 스티프닝(장기물 상승 주도)", "bear_flattening": "베어 플래트닝(단기물 상승 주도)", "bull_steepening": "불 스티프닝(단기물 하락 주도)",
              "bull_flattening": "불 플래트닝(장기물 하락 주도)", "parallel_up": "평행 상승", "parallel_down": "평행 하락", "flat": "보합"}[shape]
        lead_ko = {"front": "단기 구간(2Y)", "long": "장기 구간(10Y·30Y)", "parallel": "전 구간 비슷", "none": ""}[lead]
        sent = f"{ko}. 2Y {front:+.1f}σ · 10Y {'–' if z10 is None else f'{z10:+.1f}σ'} · 30Y {long_:+.1f}σ, 2s10s {'–' if sp_z is None else f'{sp_z:+.1f}σ'} — 움직이는 구간은 {lead_ko}."
    curve = CurveView(tenors=tenors, spread_z=None if sp_z is None else round(sp_z, 2), shape=shape, lead=lead, sentence=sent)  # type: ignore[arg-type]

    # ── 명목 = 실질 + 기대인플레 ──────────────────────────
    dc = cfg.get("decomposition", {})
    wdays = int(dc.get("window_days", 5))
    decomp: list[YieldDecomposition] = []
    for d in dc.get("tenors", []):
        fn, fb, fr = _feat(d["nominal"], market), _feat(d["breakeven"], market), _feat(d["real"], market)
        nom = None if fn is None or fn.ret_5d is None else round(fn.ret_5d, 1)
        be = None if fb is None or fb.ret_5d is None else round(fb.ret_5d, 1)
        real_m = None if fr is None or fr.ret_5d is None else round(fr.ret_5d, 1)
        missing = [k for k, f in (("명목", fn), ("기대인플레", fb), ("TIPS 실질", fr)) if f is None]
        if nom is None or be is None:
            decomp.append(YieldDecomposition(tenor=d["tenor"], window_days=wdays, nominal_bp=nom, breakeven_bp=be, real_measured_bp=real_m, dominant="unknown",
                                             sentence=f"{d['tenor']}: {' · '.join(missing) or '변화'} 계열이 없어 분해하지 못한다.", missing=missing))
            continue
        real_i = round(nom - be, 1)
        if abs(nom) < 3:
            dom_part, sent = "mixed", f"{d['tenor']} 명목 {nom:+.0f}bp({wdays}일) — 움직임이 작아 분해 의미가 없다."
        elif abs(real_i) >= abs(be) * 1.5:
            dom_part, sent = "real", f"{d['tenor']} 명목 {nom:+.0f}bp = 실질 {real_i:+.0f}bp + 기대인플레 {be:+.0f}bp — 금리 {'상승' if nom > 0 else '하락'}의 대부분이 실질금리다."
        elif abs(be) >= abs(real_i) * 1.5:
            dom_part, sent = "breakeven", f"{d['tenor']} 명목 {nom:+.0f}bp = 실질 {real_i:+.0f}bp + 기대인플레 {be:+.0f}bp — 물가 기대가 금리를 움직인다."
        else:
            dom_part, sent = "mixed", f"{d['tenor']} 명목 {nom:+.0f}bp = 실질 {real_i:+.0f}bp + 기대인플레 {be:+.0f}bp — 둘이 비슷하게 기여한다."
        if real_m is not None:
            sent += f" TIPS 실측 {real_m:+.0f}bp{'(항등식과 일치)' if abs(real_m - real_i) <= 5 else '(항등식과 차이 — 유동성·계절 요인)'}."
        decomp.append(YieldDecomposition(tenor=d["tenor"], window_days=wdays, nominal_bp=nom, breakeven_bp=be, real_implied_bp=real_i, real_measured_bp=real_m, dominant=dom_part, sentence=sent, missing=missing))  # type: ignore[arg-type]

    # ── 크로스에셋 확인 ───────────────────────────────────
    cmin2 = float(cfg.get("confirm_min_abs", 0.5))
    rows: list[ConfirmationRow] = []
    for c in cfg.get("confirmations", []):
        ids = list(c.get("instruments", [])); exp = c.get("expect", {}).get(dom.id)
        vals = {iid: (lambda z: None if z is None else round(z, 2))(_z_of(iid, market, extra, window)[0]) for iid in ids}
        have = [v for v in vals.values() if v is not None]
        if not have:
            rows.append(ConfirmationRow(key=c["key"], label=c["label"], instruments=ids, values=vals, expected_sign=exp, status="MISSING", note=str(c.get("missing_note", "결측"))))
            continue
        if exp is None:
            rows.append(ConfirmationRow(key=c["key"], label=c["label"], instruments=ids, values=vals, expected_sign=None, status="MIXED", note=f"{dom.label} 과 직접 관련 없는 줄"))
            continue
        judged = [(v > 0) == (int(exp) > 0) for v in have if abs(v) >= cmin2]
        if not judged:
            status, note = "MIXED", f"움직임이 작다(|z| < {cmin2})"
        elif all(judged):
            status, note = "CONFIRMED", f"{dom.label} 아래서 기대 방향({'+' if int(exp) > 0 else '−'})과 같다"
        elif not any(judged):
            status, note = "NOT_CONFIRMED", f"{dom.label} 아래서는 {'+' if int(exp) > 0 else '−'} 여야 하는데 반대다"
        else:
            status, note = "MIXED", "계열끼리 갈린다"
        rows.append(ConfirmationRow(key=c["key"], label=c["label"], instruments=ids, values=vals, expected_sign=int(exp), status=status, note=note))  # type: ignore[arg-type]

    # ── 핵심 괴리 ─────────────────────────────────────────
    def _cond(spec: dict) -> tuple[bool, float | None]:
        z, _w, _l = _z_of(str(spec["id"]), market, extra, window)
        if z is None:
            return False, None
        op, thr = str(spec["op"]), float(spec["z"])
        ok = {">=": z >= thr, "<=": z <= thr, "abs<": abs(z) < thr, "abs>=": abs(z) >= thr}[op]
        return ok, z
    divs: list[KeyDivergence] = []
    for d in cfg.get("divergences", []):
        ok_a, za = _cond(d["a"]); ok_b, zb = _cond(d["b"])
        if ok_a and ok_b:
            sev = min(abs(za or 0.0), abs(zb or 0.0)) if d["b"].get("op") not in ("abs<",) else abs(za or 0.0)
            divs.append(KeyDivergence(key=d["key"], label=d["label"], why=d["why"], severity=round(sev, 2), values={d["a"]["id"]: za, d["b"]["id"]: zb}))
    divs.sort(key=lambda x: -x.severity)

    # ── 시장 함의 ─────────────────────────────────────────
    ic = cfg.get("implications", {}); tbl = (ic.get("by_driver") or {}).get(dom.id, {})
    imp_rows = [ImplicationRow(key=t["key"], label=t["label"], pressure=int(tbl.get(t["key"], 0))) for t in ic.get("targets", [])]  # type: ignore[arg-type]
    implication = MarketImplication(driver=dom.id, why=str(tbl.get("why", "")), rows=imp_rows)

    # ── 전환 조건 ─────────────────────────────────────────
    tc = cfg.get("triggers", {})
    triggers: list[TriggerItem] = []
    # 물가 리프라이싱이 지배가 아니면 '그쪽으로 넘어가는 조건', 이미 지배면 '그 판단이 깨지는 조건'
    for t in tc.get("from_inflation_repricing" if dom.id == "inflation_repricing" else "to_inflation_repricing", []):
        if "missing" in t:
            triggers.append(TriggerItem(text=str(t["text"]), metric=str(t["missing"]), current="계열 없음", condition="—", met=False, measurable=False))
        elif "theme" in t:
            th = theme_by_id.get(str(t["theme"])); cur = None if th is None else getattr(th, str(t.get("field", "news_sentiment")), None)
            met = cur is not None and (cur >= float(t["value"]) if t.get("op", ">=") == ">=" else cur <= float(t["value"]))
            triggers.append(TriggerItem(text=str(t["text"]), metric=f"{t['theme']} 뉴스 톤", current="–" if cur is None else f"{cur:+.0f}", condition=f"{t['op']} {float(t['value']):+.0f}", met=bool(met)))
        else:
            z, _w, _l = _z_of(str(t["id"]), market, extra, window)
            met = z is not None and (z >= float(t["z"]) if t["op"] == ">=" else z <= float(t["z"]))
            triggers.append(TriggerItem(text=str(t["text"]), metric=_name(str(t["id"]), instruments_by_id, names), current="–" if z is None else f"{z:+.1f}σ", condition=f"z {t['op']} {float(t['z']):+.1f}", met=bool(met)))
    rel = tc.get("release", {}); rel_abs = float(rel.get("driver_release_abs", 25)); rmargin = float(rel.get("runner_up_margin", 10))
    release: list[TriggerItem] = []
    top = [e for e in dom.evidence if e.available][:2]
    if top:
        ev_txt = " · ".join(f"{e.label} {e.value:+.1f}{'σ' if e.kind == 'price' else ''}" for e in top)
        release.append(TriggerItem(text=f"{dom.label_ko} 우세 해제: {ev_txt} 가 되돌려져 |{dom.score:+.0f}| 가 {rel_abs:.0f} 아래로.",
                                   metric=dom.label, current=f"{dom.score:+.0f}", condition=f"|score| < {rel_abs:.0f}"))
    if run:
        release.append(TriggerItem(text=f"{run.label_ko}(으)로 교체: |{run.score:+.0f}| 가 {abs(dom.score) + rmargin:.0f} 를 넘으면.", metric=run.label, current=f"{run.score:+.0f}", condition=f"|score| > {abs(dom.score) + rmargin:.0f}"))

    note = ("driver 점수는 설정(rates_regime.yaml)의 증거표를 실데이터 z(하루·5일 중 큰 쪽)와 테마 뉴스 톤에 대어 만든 가중 평균이다. 부호는 장기 명목금리에 주는 방향, 결측은 분모에서 뺀다. "
            "상태는 10년 명목금리의 움직임과 driver 방향의 일치 여부다. 명목 분해는 항등식(명목 − 기대인플레 = 실질)이며 TIPS 는 실측 대조다. "
            "확률이 아니라 증거 크기이고, 판정 룰(Inflation Shock)은 그대로 돌아 Diagnostics 에 있다. FRED 금리는 하루 지연이다.")
    return RatesRegime(as_of=market.as_of, rate_move=rate_move, drivers=drivers, dominant=dom.id, runner_up=run.id if run else None, margin=margin,
                       signal_strength=round(min(100.0, abs(dom.score)), 1), signal_strength_label=dom.strength, inflation_status=infl_status,  # type: ignore[arg-type]
                       regime_label=regime_label, headline=headline, implication=dom.implication, inflation_components=comps, curve=curve, decomposition=decomp,
                       confirmations=rows, divergences=divs, market_implication=implication, triggers=triggers, release=release, note=note)
