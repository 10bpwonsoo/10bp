"""
유가 시장 원인 판별 — config/oil_regime.yaml 의 표를 실데이터에 대어 driver 점수·상태·확인표·내러티브·감시 조건을 만든다.

판정 룰(state_rules)은 건드리지 않는다. 그쪽은 Diagnostics 로 내려가고, 이 엔진은 "무엇이 유가를 움직이나" 만 답한다.
숫자는 전부 설정에서 오고 문장은 그 숫자를 채운 템플릿이다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.divergence import Divergence
from ..models.market import Instrument, MarketSnapshot
from ..models.oil_regime import (
    ConfirmationRow, DriverScore, EvidenceItem, NarrativeRow, OilMove, OilRegime, WatchItem,
)
from ..models.theme import ThemeState

ENGINE_VERSION = "0.1.0"
STATUS_KO = {"CONFIRMED": "확인됨", "UNCONFIRMED": "미확인", "CONTRADICTED": "반박됨"}

#: 시장 층 밖의 z: id → (z_1d, z_5d, layer)
ExtraZ = Mapping[str, tuple[float | None, float | None, str]]


@lru_cache(maxsize=4)
def _load(config_dir: Path | None) -> dict:
    return yaml.safe_load(((config_dir or CONFIG_DIR) / "oil_regime.yaml").read_text(encoding="utf-8")) or {}


def load_oil_regime_config(config_dir: Path | None = None) -> dict:
    return _load(config_dir)


def reset_cache() -> None:
    _load.cache_clear()


def _clip(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


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


def _name(iid: str, by_id: Mapping[str, Instrument]) -> str:
    return by_id[iid].name if iid in by_id else iid


def _strength(score: float, bands: Sequence[dict]) -> str:
    a = abs(score)
    for b in bands:
        if a >= float(b["min"]):
            return str(b["label"])
    return str(bands[-1]["label"]) if bands else ""


def _sign(v: float | None, flat: float) -> int:
    if v is None or abs(v) < flat:
        return 0
    return 1 if v > 0 else -1


def build_oil_regime(
    market: MarketSnapshot,
    themes: Sequence[ThemeState],
    divergences: Sequence[Divergence],
    instruments_by_id: Mapping[str, Instrument],
    *,
    extra_z: ExtraZ | None = None,
    extra_names: Mapping[str, str] | None = None,
    config_dir: Path | None = None,
) -> OilRegime:
    cfg = load_oil_regime_config(config_dir)
    z_ref = float(cfg.get("z_ref", 2.0)); news_ref = float(cfg.get("news_ref", 40.0))
    window = str(cfg.get("window", "max"))
    bands = list(cfg.get("strength_bands", []))
    extra = extra_z or {}
    names = dict(extra_names or {})
    theme_by_id = {t.theme_id: t for t in themes}

    # ── 유가 관측 ───────────────────────────────────────────
    om = cfg.get("oil_move", {})
    oil_ids = list(om.get("instruments", ["BRENT", "WTI"]))
    zs = {iid: (market.features[iid].z_1d if iid in market.features else None) for iid in oil_ids}
    have = [v for v in zs.values() if v is not None]
    oil_z = sum(have) / len(have) if have else None
    flat = float(om.get("flat_abs", 0.5))
    suspect = len(have) >= 2 and (max(have) - min(have)) >= float(om.get("suspect_gap", 1.5))
    direction = "unknown" if oil_z is None else ("flat" if abs(oil_z) < flat else ("up" if oil_z > 0 else "down"))
    oil_note = ""
    if suspect:
        parts = [f"{_name(k, instruments_by_id)} {v:+.1f}σ" for k, v in zs.items() if v is not None]
        oil_note = f"브렌트·WTI 가 갈린다({' vs '.join(parts)}) — 연속물 계약 교체나 봉 오류 가능성. 유가 관측으로 driver 를 확인(CONFIRMED)하지 않는다."
    elif oil_z is None:
        oil_note = "브렌트·WTI 봉이 없다."
    oil_move = OilMove(brent_z=zs.get("BRENT"), wti_z=zs.get("WTI"), oil_z=oil_z, direction=direction, suspect=suspect, note=oil_note)  # type: ignore[arg-type]

    # ── driver 점수 ──────────────────────────────────────────
    min_score = float(cfg.get("status", {}).get("min_score", 25))
    drivers: list[DriverScore] = []
    for did, spec in (cfg.get("drivers") or {}).items():
        items: list[EvidenceItem] = []
        num = den = tot = 0.0
        for e in spec.get("evidence", []):
            sign = int(e.get("sign", 1)); w = float(e.get("weight", 1.0)); tot += w
            if "theme" in e:
                t = theme_by_id.get(str(e["theme"]))
                raw = None if t is None else getattr(t, str(e.get("field", "news_sentiment")), None)
                label = str(e.get("label") or f"{e['theme']} 뉴스 톤")
                if raw is None:
                    items.append(EvidenceItem(id=f"theme:{e['theme']}", label=label, kind="news", layer="theme", sign=sign, weight=w, available=False, note="뉴스 없음"))
                    continue
                contrib = _clip(sign * float(raw) / news_ref) * w
                items.append(EvidenceItem(id=f"theme:{e['theme']}", label=label, kind="news", layer="theme", value=round(float(raw), 1), sign=sign, weight=w, contribution=round(contrib, 3), note=str(e.get("note", ""))))
            else:
                iid = str(e["id"])
                z, win, layer = _z_of(iid, market, extra, window)
                label = names.get(iid) or _name(iid, instruments_by_id)
                if z is None:
                    items.append(EvidenceItem(id=iid, label=label, layer=layer, sign=sign, weight=w, available=False, note=str(e.get("note", "")) or "결측"))  # type: ignore[arg-type]
                    continue
                contrib = _clip(sign * z / z_ref) * w
                items.append(EvidenceItem(id=iid, label=label, layer=layer, value=round(z, 2), window=win, sign=sign, weight=w, contribution=round(contrib, 3), note=str(e.get("note", ""))))  # type: ignore[arg-type]
            num += contrib; den += w
        score = round(100.0 * num / den, 1) if den > 0 else 0.0
        coverage = round(den / tot, 3) if tot > 0 else 0.0
        # 상태 — 유가 관측에 비춰
        s_drv, s_oil = _sign(score, min_score), _sign(oil_z, flat)
        if s_drv == 0:
            status, reason = "UNCONFIRMED", f"증거가 약하다(|{score:+.0f}| < {min_score:.0f})."
        elif suspect:
            status, reason = "UNCONFIRMED", "유가 관측이 의심스러워(브렌트·WTI 불일치) 확인을 보류한다."
        elif s_oil == 0:
            status, reason = "UNCONFIRMED", f"유가가 평탄하다({'–' if oil_z is None else f'{oil_z:+.1f}σ'}) — 이 driver 의 방향이 가격에 아직 안 찍혔다."
        elif s_oil == s_drv:
            status, reason = "CONFIRMED", f"driver 방향({'상승' if s_drv > 0 else '하락'})과 유가({oil_z:+.1f}σ)가 같다."
        else:
            status, reason = "CONTRADICTED", f"driver 는 {'상승' if s_drv > 0 else '하락'} 압력인데 유가는 반대({oil_z:+.1f}σ)로 움직였다."
        items.sort(key=lambda i: -abs(i.contribution))
        drivers.append(DriverScore(id=did, label=str(spec.get("label", did)), label_ko=str(spec.get("label_ko", did)), score=score,
                                   strength=_strength(score, bands), status=status, status_reason=reason, coverage=coverage,  # type: ignore[arg-type]
                                   evidence=items, implication=str(spec.get("implication", ""))))
    ranked = sorted(drivers, key=lambda d: -abs(d.score))
    dom = ranked[0]
    run = ranked[1] if len(ranked) > 1 else None
    margin = round(abs(dom.score) - (abs(run.score) if run else 0.0), 1)
    strength_val = round(min(100.0, abs(dom.score)), 1)
    regime_label = f"{dom.label}{' Risk-Off' if dom.id == 'macro_liquidity' and dom.score < 0 else ''} — {dom.status}"
    headline = (f"지금 유가는 {dom.label_ko} 쪽 증거가 가장 크다({dom.score:+.0f}, {dom.strength})"
                + (f" — {run.label_ko} {run.score:+.0f} 보다 {margin:.0f} 앞선다." if run else ".")
                + f" 상태 {STATUS_KO[dom.status]}: {dom.status_reason}")

    # ── 시장 확인 ──────────────────────────────────────────
    conf_min = float(cfg.get("confirm_min_abs", 0.5))
    rows: list[ConfirmationRow] = []
    for c in cfg.get("confirmations", []):
        ids = list(c.get("instruments", []))
        exp = c.get("expect", {}).get(dom.id)
        vals: dict[str, float | None] = {}
        for iid in ids:
            z, _w, _l = _z_of(iid, market, extra, window)
            vals[iid] = None if z is None else round(z, 2)
        have_v = [v for v in vals.values() if v is not None]
        if not ids or not have_v:
            rows.append(ConfirmationRow(key=c["key"], label=c["label"], instruments=ids, values=vals, expected_sign=exp, status="missing", note=str(c.get("missing_note", "결측"))))
            continue
        # 대표값: 절댓값 큰 쪽
        rep = max(have_v, key=abs)
        if exp is None:
            status, note = "neutral", f"{dom.label} 과 무관한 줄"
        elif abs(rep) < conf_min:
            status, note = "neutral", f"움직임이 작다(|z| < {conf_min})"
        elif (rep > 0) == (int(exp) > 0):
            status, note = "confirms", f"{dom.label} 아래서 기대 방향({'+' if int(exp) > 0 else '−'})과 같다"
        else:
            status, note = "contradicts", f"{dom.label} 아래서는 {'+' if int(exp) > 0 else '−'} 여야 하는데 반대다"
        if c["key"] == "crude" and suspect:
            status, note = "neutral", "브렌트·WTI 불일치 — 관측 자체가 의심"
        rows.append(ConfirmationRow(key=c["key"], label=c["label"], instruments=ids, values=vals, expected_sign=exp, status=status, note=note))  # type: ignore[arg-type]

    # ── 내러티브 vs 가격 ────────────────────────────────────
    nar_cfg = cfg.get("narrative", {}); nmin = float(nar_cfg.get("min_abs", 10))
    div_by_theme = {d.related_theme: d for d in divergences if d.related_theme}
    narrative: list[NarrativeRow] = []
    for spec in nar_cfg.get("themes", []):
        t = theme_by_id.get(str(spec["theme"]))
        if t is None:
            continue
        news, price, noun = t.news_sentiment, t.price_momentum, str(spec.get("noun", "재료"))
        if news is None:
            sent = f"{t.name}: 기사가 없어 내러티브를 잴 수 없다 — 가격만 {('–' if price is None else f'{price:+.0f}')}."
        elif price is None:
            sent = f"{t.name}: 뉴스는 {noun}({news:+.0f})을 말하지만 가격 모멘텀이 없다."
        elif news >= nmin and price <= -nmin:
            sent = f"뉴스는 {noun}({news:+.0f})를 말하지만 가격({price:+.0f})은 이를 확인하지 않는다 — 내러티브가 가격을 앞서거나, 다른 driver 가 가격을 누른다."
        elif news >= nmin and price >= nmin:
            sent = f"뉴스({noun} {news:+.0f})와 가격({price:+.0f})이 같은 방향 — 시장이 {noun}를 반영하고 있다."
        elif news <= -nmin and price >= nmin:
            sent = f"뉴스는 {noun} 완화({news:+.0f})를 말하는데 가격({price:+.0f})은 오른다 — 가격을 움직이는 것은 이 내러티브가 아니다."
        elif news <= -nmin and price <= -nmin:
            sent = f"뉴스({noun} 완화 {news:+.0f})와 가격({price:+.0f})이 같은 방향 — 완화가 가격에 반영된다."
        else:
            sent = f"{t.name}: 뉴스({news:+.0f})·가격({price:+.0f}) 모두 뚜렷하지 않다."
        d = div_by_theme.get(t.theme_id)
        narrative.append(NarrativeRow(theme_id=t.theme_id, name=t.name, news=None if news is None else round(news, 1), price=None if price is None else round(price, 1),
                                      sentence=sent, divergence_severity=None if d is None else round(d.severity, 0)))

    # ── 무엇이 바뀌면 판단이 바뀌나 ──────────────────────────
    wc = cfg.get("watch", {})
    watch: list[WatchItem] = []
    rel = float(wc.get("driver_release_abs", 25)); oil_c = float(wc.get("oil_confirm_abs", 1.0))
    top_ev = [e for e in dom.evidence if e.available][:2]
    if top_ev:
        names = " · ".join(f"{e.label} {e.value:+.1f}{'σ' if e.kind == 'price' else ''}" for e in top_ev)
        watch.append(WatchItem(text=f"{dom.label_ko} 우세 해제: 핵심 증거({names})가 되돌려져 driver 점수 |{dom.score:+.0f}| 가 {rel:.0f} 아래로 내려오면.",
                               metric=dom.label, current=f"{dom.score:+.0f}", condition=f"|score| < {rel:.0f}", effect="dominant driver 교체"))
    if run:
        need = abs(dom.score) + float(wc.get("runner_up_takeover_margin", 10))
        top_run = [e for e in run.evidence if e.available][:2]
        names = " · ".join(f"{e.label}" for e in top_run) or "핵심 증거"
        watch.append(WatchItem(text=f"{run.label_ko}(으)로 교체: {names}가 강해져 |{run.score:+.0f}| 가 {need:.0f} 를 넘으면.",
                               metric=run.label, current=f"{run.score:+.0f}", condition=f"|score| > {need:.0f}", effect=f"dominant → {run.label}"))
    if suspect or oil_z is None:
        now_txt = " vs ".join(f"{_name(k, instruments_by_id)} {v:+.1f}σ" for k, v in zs.items() if v is not None) or "봉 없음"
        watch.append(WatchItem(text=f"유가 관측 정합: 브렌트·WTI 가 같은 방향으로 |z| ≥ {oil_c:.1f} 을 넘으면 driver 상태가 미확인에서 확인/반박으로 바뀐다 (지금 {now_txt}).",
                               metric="Brent/WTI", current=" / ".join(f"{v:+.1f}σ" if v is not None else "–" for v in zs.values()), condition=f"둘 다 같은 부호, |z| ≥ {oil_c:.1f}", effect="CONFIRMED / CONTRADICTED 판정 가능"))
    else:
        watch.append(WatchItem(text=f"유가 자체가 |z| ≥ {oil_c:.1f} 으로 {'하락' if dom.score < 0 else '상승'}하면 {dom.label} 이 CONFIRMED, 반대로 가면 CONTRADICTED.",
                               metric="Brent/WTI", current=f"{oil_z:+.1f}σ", condition=f"|z| ≥ {oil_c:.1f}", effect="상태 확정"))
    geo = next((d for d in drivers if d.id == "geopolitical"), None)
    if geo is not None:
        news_ev = next((e for e in geo.evidence if e.kind == "news" and e.available), None)
        nr = float(wc.get("news_release_abs", 10))
        if news_ev is not None and news_ev.value is not None and abs(news_ev.value) >= nr:
            watch.append(WatchItem(text=f"지정학 프리미엄 후보 소거: 지정학 뉴스 톤({news_ev.value:+.0f})이 ±{nr:.0f} 안으로 식으면 — 반대로 브렌트·WTI 가 같이 오르면 CONFIRMED.",
                                   metric="지정학 뉴스 톤", current=f"{news_ev.value:+.0f}", condition=f"|톤| < {nr:.0f}", effect="Geopolitical 후보 제거"))
    hy = market.features.get("US_HY_OAS")
    if hy is not None and hy.z_1d is not None and abs(hy.z_1d) >= float(wc.get("hy_release_abs", 1.0)):
        watch.append(WatchItem(text=f"신용 스프레드 되돌림: HY OAS {hy.z_1d:+.1f}σ 가 |z| < {float(wc.get('hy_release_abs', 1.0)):.1f} 로 돌아오면 거시·유동성 증거의 절반이 빠진다.",
                               metric="US HY OAS", current=f"{hy.z_1d:+.1f}σ", condition=f"|z| < {float(wc.get('hy_release_abs', 1.0)):.1f}", effect="Macro / Liquidity 약화"))
    missing_rows = [r.label for r in rows if r.status == "missing"]
    if missing_rows:
        watch.append(WatchItem(text=f"결측 확인 줄이 채워지면 확인표가 바뀐다: {', '.join(missing_rows[:3])}.", metric="결측", current=f"{len(missing_rows)}줄", condition="계열 확보", effect="확인/반박 재계산"))
    watch = watch[:5]

    note = ("driver 점수는 설정(oil_regime.yaml)의 증거표를 실데이터 z(하루·5일 중 큰 쪽)와 테마 뉴스 톤에 대어 만든 가중 평균이다. "
            "부호는 유가에 주는 방향, 결측은 분모에서 뺀다. 상태는 유가 관측(브렌트·WTI 평균)과 driver 방향의 일치 여부이며, 두 유가가 갈리면 확인을 보류한다. "
            "판정 룰(Geopolitical Risk 등)은 그대로 돌고 Diagnostics 에 있다 — 이 화면은 원인 후보의 증거 크기를 비교할 뿐 원인을 단정하지 않는다.")
    return OilRegime(as_of=market.as_of, oil_move=oil_move, drivers=drivers, dominant=dom.id, runner_up=run.id if run else None, margin=margin,
                     signal_strength=strength_val, signal_strength_label=dom.strength, regime_label=regime_label, headline=headline,
                     implication=dom.implication, confirmations=rows, narrative=narrative, watch=watch, note=note)
