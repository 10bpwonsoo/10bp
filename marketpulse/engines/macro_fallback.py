"""
신뢰도 기반 macro fallback data layer(2026-10-13) — 수집한 원자료(raw)를 급(tier)별로 풀어 INFLATION PRESSURE MAP 의 macro 구성요소를 만든다.

순서: FRED API(PRIMARY) → FRED 그래프 CSV(MIRROR) → 출처가 붙은 수기 파일의 공식 발표값(SECONDARY) → 경제적으로 비슷한 지표 조합(PROXY)
→ 없으면 UNAVAILABLE. 뉴스(NEWS)는 수치를 대체하지 않고 별도의 INFLATION NEWS PULSE 로만 쓴다.

지키는 것
- 원자료가 있으면 proxy 는 점수에서 빠진다(참고값으로만). 원자료와 proxy 를 같은 가중치로 합산하지 않는다.
- STALE(예상 갱신 주기보다 오래된) 값은 보여주되 점수에는 넣지 않는다.
- 기사 전망치는 쓰지 않는다 — 수기 파일의 actual(발표치)만, 발표일이 as_of 이하인 것만.
- 점수 근거는 가속도 z: (3개월 연율 − 12개월 상승률)을 과거 같은 값의 표준편차로 나눈 값, z_ref 에서 ±100.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import pstdev
from typing import Any, Iterable, Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.macro_data import MacroComponent, MacroDataPoint, MacroInflationLayer, NewsDriver, NewsPulse

RawSeries = Mapping[str, Any]  # {"path": "PRIMARY"|"MIRROR", "observations": [[iso, value|None], ...], "vintage": iso|None, "error": str|None}


@lru_cache(maxsize=4)
def _load(config_dir: Path | None) -> dict:
    return yaml.safe_load(((config_dir or CONFIG_DIR) / "macro_sources.yaml").read_text(encoding="utf-8")) or {}


def load_macro_config(config_dir: Path | None = None) -> dict:
    return _load(config_dir)


def _clip(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _shift(d: date, months: int) -> date:
    m = d.year * 12 + (d.month - 1) + months
    return date(m // 12, m % 12 + 1, 1)


def _obs(raw: RawSeries) -> dict[date, float]:
    out: dict[date, float] = {}
    for row in raw.get("observations") or []:
        try:
            d, v = date.fromisoformat(str(row[0])[:10]), row[1]
        except (ValueError, IndexError, TypeError):
            continue
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isnan(fv):
            out[d] = fv
    return out


def transforms(obs: Mapping[date, float], frequency: str, cfg: Mapping) -> dict[str, Any] | None:
    """마지막 관측의 YoY · MoM(QoQ) · 가속도 z. 중간 결측(예: 미집계 월)은 그 계산만 건너뛴다."""
    if not obs:
        return None
    step = 3 if frequency == "quarterly" else 1           # 개월
    n = 12 // step                                         # 1년의 기간 수
    k = 1 if frequency == "quarterly" else 3              # 가속도의 '최근' 창(기간 수)
    t = max(obs)

    def ratio(a: date, b: date) -> float | None:
        return None if a not in obs or b not in obs or obs[b] == 0 else obs[a] / obs[b]

    def yoy(d: date) -> float | None:
        r = ratio(d, _shift(d, -12)); return None if r is None else (r - 1) * 100

    def chg(d: date) -> float | None:
        r = ratio(d, _shift(d, -step)); return None if r is None else (r - 1) * 100

    def ann(d: date) -> float | None:
        r = ratio(d, _sh(d)); return None if r is None else ((r ** (n / k)) - 1) * 100

    def accel(d: date) -> float | None:
        a, y = ann(d), yoy(d)
        return None if a is None or y is None else a - y

    def _sh(d: date) -> date:
        return _shift(d, -step * k)

    sc = cfg.get("score") or {}
    hist = [a for i in range(1, int(sc.get("history_months", 60)) // step + 1) if (a := accel(_shift(t, -step * i))) is not None]
    a_t = accel(t)
    z = None
    if a_t is not None and len(hist) >= int(sc.get("min_history", 24)) // step:
        sd = pstdev(hist)
        z = None if sd == 0 else a_t / sd
    return {"t": t, "yoy": yoy(t), "yoy_prev": yoy(_shift(t, -step)), "chg": chg(t), "chg_prev": chg(_shift(t, -step)), "ann": ann(t), "accel": a_t, "z": z}


def _freshness(last: date | None, period: date | None, frequency: str, as_of: date, cfg: Mapping) -> tuple[int | None, bool, str]:
    fq = (cfg.get("frequency") or {}).get(frequency) or {"interval_days": 31, "stale_multiple": 1.5}
    limit = float(fq["interval_days"]) * float(fq["stale_multiple"])
    if last is not None:
        age = (as_of - last).days
        return age, age > limit, ""
    if period is not None:
        # 발표일을 모르면 기간 시작에서 한 주기 + 발표 지연을 더 봐 준다 — 그래도 넘으면 STALE
        age = (as_of - period).days
        return None, age > limit + float(fq["interval_days"]), "발표일 미확인 — 기간 기준으로 신선도 판정"
    return None, True, "날짜 없음"


def _period_label(d: date, frequency: str) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}" if frequency == "quarterly" else f"{d.year}-{d.month:02d}"


def _secondary(spec: Mapping, curated: Mapping | None, as_of: date) -> tuple[dict, list[str]] | None:
    """수기 파일에서 같은 발표의 가장 최근 actual(발표일 ≤ as_of). 전망치는 쓰지 않는다."""
    sec = spec.get("secondary")
    if not sec or not curated:
        return None
    rel = [r for r in curated.get("releases", []) if r.get("key") == sec.get("release") and date.fromisoformat(str(r["date"])) <= as_of]
    if not rel:
        return None
    r = max(rel, key=lambda x: x["date"])
    m = {x.get("key"): x for x in r.get("measures", [])}
    y = m.get(sec.get("yoy")) or {}
    if y.get("actual") is None:
        return None
    pubs = sorted({s.get("publisher", "") for s in r.get("sources", []) if s.get("publisher")})
    return {"value": float(y["actual"]), "previous": y.get("prior"), "consensus": y.get("consensus"), "release_date": date.fromisoformat(str(r["date"])),
            "period": str(r.get("period", ""))}, pubs


def _consensus(spec: Mapping, curated: Mapping | None, period: str) -> float | None:
    sec = spec.get("secondary")
    if not sec or not curated:
        return None
    for r in curated.get("releases", []):
        if r.get("key") == sec.get("release") and str(r.get("period")) == period:
            for x in r.get("measures", []):
                if x.get("key") == sec.get("yoy"):
                    return x.get("consensus")
    return None


def resolve_series(sid: str, spec: Mapping, raw: RawSeries | None, curated: Mapping | None, as_of: date, cfg: Mapping) -> MacroDataPoint:
    tiers = cfg.get("tiers") or {}
    freq = str(spec.get("frequency", "monthly"))
    measure = str(spec.get("measure", "YoY"))
    stale_f = float(cfg.get("stale_confidence_factor", 0.5))
    agency = str(spec.get("agency", ""))
    reasons: list[str] = []
    if raw is not None and raw.get("path") in ("PRIMARY", "MIRROR") and not raw.get("error"):
        tr = transforms(_obs(raw), freq, cfg)
        if tr is not None:
            tier = str(raw["path"])
            vintage = date.fromisoformat(str(raw["vintage"])[:10]) if raw.get("vintage") else None
            fresh, stale, fnote = _freshness(vintage, tr["t"], freq, as_of, cfg)
            v, pv = (tr["yoy"], tr["yoy_prev"]) if measure == "YoY" else (tr["chg"], tr["chg_prev"])
            period = _period_label(tr["t"], freq)
            conf = float((tiers.get(tier) or {}).get("confidence", 0.5)) * (stale_f if stale else 1.0)
            via = "FRED" if tier == "PRIMARY" else "FRED CSV 미러"
            return MacroDataPoint(series=sid, label=str(spec.get("label", sid)), value=None if v is None else round(v, 2), unit="%", measure=measure,
                                  previous=None if pv is None else round(pv, 2), consensus=_consensus(spec, curated, period) if measure == "YoY" else None,
                                  period=period, release_date=vintage, source=f"{agency} via {via}", source_tier=tier, is_original_data=True,  # type: ignore[arg-type]
                                  last_updated=vintage, freshness_days=fresh, frequency=freq, stale=stale, confidence=round(conf, 2),  # type: ignore[arg-type]
                                  momentum_ann=None if tr["ann"] is None else round(tr["ann"], 2), pressure_z=None if tr["z"] is None else round(tr["z"], 2), note=fnote)
        reasons.append("FRED 관측치 없음")
    elif raw is not None and raw.get("error"):
        reasons.append(f"FRED: {raw['error']}")
    else:
        reasons.append("FRED 미연결")
    sec = _secondary(spec, curated, as_of)
    if sec is not None:
        s, pubs = sec
        fresh, stale, _ = _freshness(s["release_date"], None, freq, as_of, cfg)
        conf = float((tiers.get("SECONDARY") or {}).get("confidence", 0.7)) * (stale_f if stale else 1.0)
        # 이력 없이 한 점만 있으므로 가속도 대신 '컨센서스 대비 놀람'을 0.2%p 당 1σ 로 본다(낮은 신뢰도 · note 에 적는다)
        z = None if s["consensus"] is None else (s["value"] - float(s["consensus"])) / 0.2
        return MacroDataPoint(series=sid, label=str(spec.get("label", sid)), value=s["value"], unit="%", measure="YoY", previous=s["previous"], consensus=s["consensus"],
                              period=s["period"], release_date=s["release_date"], source=" · ".join(pubs) or "보도", source_tier="SECONDARY", is_original_data=True,
                              fallback_reason="; ".join(reasons) + " — 신뢰 매체가 보도한 공식 발표값 사용", last_updated=s["release_date"], freshness_days=fresh,
                              frequency=freq, stale=stale, confidence=round(conf, 2), pressure_z=None if z is None else round(z, 2),  # type: ignore[arg-type]
                              note="점수 근거: 컨센서스 대비 놀람(이력 없음)")
    return MacroDataPoint(series=sid, label=str(spec.get("label", sid)), measure=measure, source="", source_tier="UNAVAILABLE", is_original_data=False,
                          fallback_reason="; ".join(reasons + ["확인된 보도값도 없음"]), frequency=freq, stale=False, confidence=0.0)  # type: ignore[arg-type]


def _usable(p: MacroDataPoint) -> bool:
    return p.source_tier not in ("UNAVAILABLE", "NEWS") and p.value is not None


def _score(points: Sequence[MacroDataPoint], cfg: Mapping) -> float | None:
    z_ref = float((cfg.get("score") or {}).get("z_ref", 2.0))
    zs = [p.pressure_z for p in points if _usable(p) and not p.stale and p.pressure_z is not None]
    return None if not zs else round(sum(_clip(z / z_ref) for z in zs) / len(zs) * 100.0, 1)


def _worst_tier(points: Sequence[MacroDataPoint], cfg: Mapping) -> str:
    tiers = cfg.get("tiers") or {}
    return max((p.source_tier for p in points), key=lambda t: int((tiers.get(t) or {}).get("rank", 9)))


def _agg(points: Sequence[MacroDataPoint], total: int) -> tuple[date | None, int | None, bool, float]:
    used = [p for p in points if _usable(p)]
    last = max((p.last_updated for p in used if p.last_updated), default=None)
    fresh = min((p.freshness_days for p in used if p.freshness_days is not None), default=None)
    stale = bool(used) and all(p.stale for p in used)
    conf = (sum(p.confidence for p in used) / len(used)) * (len(used) / max(1, total)) ** 0.5 if used else 0.0
    return last, fresh, stale, round(conf, 2)


def build_layer(raw: Mapping[str, RawSeries] | None, *, as_of: datetime, curated: Mapping | None = None, themes: Iterable[Any] = (), events: Iterable[Any] = (),
                config_dir: Path | None = None) -> MacroInflationLayer:
    cfg = load_macro_config(config_dir)
    d = as_of.date()
    specs = cfg.get("series") or {}
    raw = raw or {}
    pts = {sid: resolve_series(sid, spec, raw.get(str(spec.get("fred", sid))), curated, d, cfg) for sid, spec in specs.items()}
    comps: dict[str, MacroComponent] = {}
    cc = cfg.get("components") or {}
    proxy_note = str(cfg.get("proxy_note", ""))

    # ── 실제 물가 ─────────────────────────────────────────
    rc = cc.get("realized") or {}
    real = [pts[s] for s in rc.get("series", []) if s in pts]
    used = [p for p in real if _usable(p)]
    if used:
        last, fresh, stale, conf = _agg(real, len(real))
        tier = _worst_tier(used, cfg)
        proxies = [pts[s] for s in (rc.get("proxy") or {}).get("series", []) if s in pts and _usable(pts[s])]
        comps["realized"] = MacroComponent(key="realized", display_label=str(rc.get("label", "Realized Inflation")), score=_score(used, cfg), source_class=tier,  # type: ignore[arg-type]
                                           source_label=f"{rc.get('agencies', '')}" + (" via FRED" if tier == "PRIMARY" else ""), is_original_data=True,
                                           last_updated=last, freshness_days=fresh, stale=stale, confidence=conf, series=real,
                                           reference=[p.model_copy(update={"note": "참고 — 원데이터가 있어 점수에 넣지 않음"}) for p in proxies],
                                           fallback_reason="" if len(used) == len(real) else "일부 series 미연결: " + ", ".join(p.label for p in real if not _usable(p)))
    else:
        px = rc.get("proxy") or {}
        ppts = [pts[s] for s in px.get("series", []) if s in pts]
        pused = [p for p in ppts if _usable(p)]
        if pused:
            last, fresh, stale, conf = _agg(ppts, len(ppts))
            pconf = float(((cfg.get("tiers") or {}).get("PROXY") or {}).get("confidence", 0.45))
            comps["realized"] = MacroComponent(key="realized", display_label=str(px.get("label", "REALIZED INFLATION PROXY")), score=_score(pused, cfg), source_class="PROXY",
                                               source_label=" · ".join(p.label for p in pused), is_original_data=False, proxy_components=[p.label for p in pused],
                                               fallback_reason=str(px.get("fallback_reason", proxy_note)), last_updated=last, freshness_days=fresh, stale=stale,
                                               confidence=round(min(conf, pconf), 2), series=ppts)
        else:
            comps["realized"] = MacroComponent(key="realized", display_label=str(rc.get("label", "Realized Inflation")), source_class="UNAVAILABLE", is_original_data=False,
                                               fallback_reason=str(rc.get("unavailable_reason", "")), series=real)

    # ── 임금·서비스 — 합성 지표(PROXY) ───────────────────
    wc = cc.get("wages") or {}
    wpts = [pts[s] for s in wc.get("series", []) if s in pts]
    wused = [p for p in wpts if _usable(p)]
    if wused:
        last, fresh, stale, conf = _agg(wpts, len(wpts))
        pconf = float(((cfg.get("tiers") or {}).get("PROXY") or {}).get("confidence", 0.45))
        ws = _score(wused, cfg)
        rs = comps["realized"].score if comps["realized"].is_original_data else None
        cm = wc.get("comment") or {}
        if ws is None or rs is None:
            comment = str(cm.get("alone", ""))
        elif ws - rs >= float(wc.get("compare_margin", 15)):
            comment = str(cm.get("stickier", ""))
        elif rs - ws >= float(wc.get("compare_margin", 15)):
            comment = str(cm.get("faster", ""))
        else:
            comment = str(cm.get("similar", ""))
        comps["wages"] = MacroComponent(key="wages", display_label=str(wc.get("label", "Wage / Services")), score=ws, source_class="PROXY",
                                        source_label=" · ".join(p.label for p in wused), is_original_data=False, proxy_components=[p.label for p in wused],
                                        fallback_reason=str(wc.get("fallback_reason", proxy_note)), last_updated=last, freshness_days=fresh, stale=stale,
                                        confidence=round(min(conf, pconf), 2), series=wpts, comment=comment)
    else:
        comps["wages"] = MacroComponent(key="wages", display_label=str(wc.get("label", "Wage / Services")), source_class="UNAVAILABLE", is_original_data=False,
                                        fallback_reason=str(wc.get("unavailable_reason", "")), series=wpts)

    return MacroInflationLayer(as_of=as_of, components=comps, news=build_news_pulse(themes, events, as_of, cfg), series=list(pts.values()),
                               note="FRED API = PRIMARY(원 발표기관 표기) · FRED CSV = MIRROR · 보도 확인 수기 파일 = SECONDARY · 합성 = PROXY · 뉴스 = NEWS. "
                                    "YoY 는 FRED 계절조정 지수로 계산해 공식 발표(비계절조정) 값과 0.1%p 안팎 다를 수 있다.")


def build_news_pulse(themes: Iterable[Any], events: Iterable[Any], as_of: datetime, cfg: Mapping) -> NewsPulse:
    nc = cfg.get("news") or {}
    by = {getattr(t, "theme_id", None): t for t in themes}
    drivers: list[NewsDriver] = []
    num = den = 0.0
    arrow_abs = float(nc.get("arrow_abs", 10))
    for d in nc.get("drivers", []):
        t = by.get(d["theme"])
        tone = None if t is None else getattr(t, "news_sentiment", None)
        if tone is not None:
            tone = float(tone) * int(d.get("sign", 1))
            num += tone * float(d.get("weight", 1.0)); den += float(d.get("weight", 1.0))
        arrow = "–" if tone is None else ("↑" if tone >= arrow_abs else ("↓" if tone <= -arrow_abs else "→"))
        drivers.append(NewsDriver(label=str(d["label"]), theme=str(d["theme"]), arrow=arrow, tone=None if tone is None else round(tone, 1)))
    themes_set = {d["theme"] for d in nc.get("drivers", [])}
    since = as_of - timedelta(hours=float(nc.get("lookback_hours", 48)))
    n = sum(1 for e in events if getattr(e, "timestamp", None) is not None and since <= e.timestamp <= as_of + timedelta(hours=1)
            and set(getattr(e, "themes", []) or []) & themes_set)
    score = None if den == 0 else round(num / den, 1)
    cm = nc.get("comment") or {}
    if score is None or n == 0:
        comment = str(cm.get("none", ""))
    else:
        comment = str(cm.get("up" if score >= arrow_abs else ("down" if score <= -arrow_abs else "flat"), ""))
    conf = float(((cfg.get("tiers") or {}).get("NEWS") or {}).get("confidence", 0.2)) if score is not None else 0.0
    return NewsPulse(score=score, articles=n, drivers=drivers, comment=comment, confidence=conf)


def news_state(score: float | None, cfg: Mapping | None = None) -> tuple[str, str, str]:
    cfg = cfg or load_macro_config()
    if score is None:
        return "NO SIGNAL", "뉴스 부족", "missing"
    for s in (cfg.get("news") or {}).get("states", []):
        if score >= float(s["min"]):
            return str(s["state"]), str(s.get("ko", "")), str(s.get("tone", "flat"))
    return "NEUTRAL", "중립", "flat"


def wage_state(score: float | None, cfg: Mapping | None = None) -> tuple[str, str, str] | None:
    cfg = cfg or load_macro_config()
    if score is None:
        return None
    for s in ((cfg.get("components") or {}).get("wages") or {}).get("states", []):
        if score >= float(s["min"]):
            return str(s["state"]), str(s.get("ko", "")), str(s.get("tone", "flat"))
    return None


def tier_label(tier: str, cfg: Mapping | None = None) -> str:
    cfg = cfg or load_macro_config()
    return str(((cfg.get("tiers") or {}).get(tier) or {}).get("label", tier))
