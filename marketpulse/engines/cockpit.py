"""
실시간 메인 탭 — decision cockpit 집계 (2026-09-29).

질문 순서대로 답한다: 지금 어떤 시장인가(REGIME) → 무엇이 움직이는가(DRIVERS) → 다른 자산이 확인하는가(CONFIRMATION)
→ 리더십은 어디인가(LEADERSHIP) → 어디로 전달되는가(TRANSMISSION) → 남은 촉매·위험(CATALYSTS) → 무엇이 판단을 바꾸는가(NEXT).

새 데이터를 만들지 않는다. 판정·테마·괴리·뉴스·Investment·AI/금리/유가 판별 층의 값을 config/cockpit.yaml 의 규칙으로 고르고
문장으로 만든다. driver 는 |z| 순이 아니라 강도 × 확보 + 크로스에셋 확인 + 지속 + 뉴스 촉매로 고른다. 확률 표현 없음.
카드에 넣을 것이 없으면 빈 채로 두고 화면이 숨긴다.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from ..config.registry import get_themes
from ..config.settings import CONFIG_DIR
from ..models.cockpit import (
    CatalystItem, Cockpit, CrossAsset, CrossAssetRow, DataStatus, Driver, EarningsPulse, EvidenceRow, KeyDivergence, KeyVariable,
    LeaderRow, Leadership, MarketNow, NextItem, RadarStock, SparkPoint, ThemePulseRow, TransmissionChain, TransmissionStock, UpcomingEvent, WatchRow,
)
from ..models.market import Instrument, MarketSnapshot
from ..models.snapshot import IntelligenceSnapshot

KST = timezone(timedelta(hours=9))
LABEL_TEXT = {"RISK_ON": "RISK-ON", "RISK_OFF": "RISK-OFF", "GROWTH_SHOCK": "GROWTH SHOCK", "INFLATION_SHOCK": "INFLATION SHOCK", "LIQUIDITY_STRESS": "LIQUIDITY STRESS",
              "POLICY_DRIVEN": "POLICY DRIVEN", "GEOPOLITICAL_RISK": "GEOPOLITICAL RISK", "NEUTRAL": "NO REGIME"}
LABEL_KO = {"RISK_ON": "위험선호", "RISK_OFF": "위험회피", "GROWTH_SHOCK": "성장 충격", "INFLATION_SHOCK": "물가 충격", "LIQUIDITY_STRESS": "유동성 경색",
            "POLICY_DRIVEN": "정책 주도", "GEOPOLITICAL_RISK": "지정학 위험", "NEUTRAL": "판정 없음"}


@lru_cache(maxsize=4)
def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_cockpit_config(config_dir: Path | None = None) -> dict:
    return _load((config_dir or CONFIG_DIR) / "cockpit.yaml")


def _clip(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _r(v, d: int = 2):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), d)


def _arrow(z: float | None, hi: float, lo: float) -> str:
    if z is None:
        return "?"
    return "↑↑" if z >= hi else "↑" if z >= lo else "↓↓" if z <= -hi else "↓" if z <= -lo else "→"


def _mean(xs: Sequence[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if v else None


class _Z:
    """z 조회 — 시장 스냅샷(하루·5일 중 |z| 큰 쪽) 위에 대체·AI 파생 z 를 얹는다."""

    def __init__(self, market: MarketSnapshot, extra: Mapping[str, tuple[float | None, float | None]], names: Mapping[str, str], by_id: Mapping[str, Instrument]):
        self.market, self.extra, self.names, self.by_id = market, extra, names, by_id

    def z1(self, iid: str) -> float | None:
        f = self.market.features.get(iid)
        if f is not None:
            return f.z_1d
        return self.extra[iid][0] if iid in self.extra else None

    def z5(self, iid: str) -> float | None:
        f = self.market.features.get(iid)
        if f is not None:
            return f.z_5d
        return self.extra[iid][1] if iid in self.extra else None

    def zmax(self, iid: str) -> tuple[float | None, int | None]:
        a, b = self.z1(iid), self.z5(iid)
        if a is None and b is None:
            return None, None
        if b is None:
            return a, 1
        if a is None:
            return b, 5
        return (a, 1) if abs(a) >= abs(b) else (b, 5)

    def week_ago(self, iid: str) -> float | None:
        f = self.market.features.get(iid)
        return None if f is None else f.z_1d_week_ago

    def ma20(self, iid: str) -> float | None:
        f = self.market.features.get(iid)
        return None if f is None else f.ma_dist_20

    def name(self, iid: str) -> str:
        return self.names.get(iid) or (self.by_id[iid].name if iid in self.by_id else iid)

    def display(self, iid: str, snapshot: IntelligenceSnapshot) -> str:
        for w in snapshot.whats_moving:
            if w.key == iid and w.change_display:
                return w.change_display
        return ""


def build_cockpit(
    snapshot: IntelligenceSnapshot,
    market: MarketSnapshot,
    instruments_by_id: Mapping[str, Instrument],
    *,
    history: object | None = None,
    investment: object | None = None,
    ai_regime: object | None = None,
    rates_regime: object | None = None,
    oil_regime: object | None = None,
    extra_z: Mapping[str, tuple[float | None, float | None, str]] | None = None,
    extra_names: Mapping[str, str] | None = None,
    config_dir: Path | None = None,
) -> Cockpit:
    cfg = load_cockpit_config(config_dir)
    hi, lo = [float(x) for x in cfg.get("arrow", [2.0, 0.8])]; flat = float(cfg.get("flat_abs", 0.5)); z_ref = float(cfg.get("z_ref", 2.0))
    extra: dict[str, tuple[float | None, float | None]] = {k: (v[0], v[1]) for k, v in (extra_z or {}).items()}
    names = dict(extra_names or {})
    # AI 판별의 파생 z 를 증거로 쓸 수 있게 얹는다
    if ai_regime is not None:
        avm = getattr(ai_regime, "ai_vs_market", None)
        if avm is not None and avm.rel_ndx_z is not None:
            extra["AI_REL_NDX"] = (avm.rel_ndx_z_1d, avm.rel_ndx_z_5d); names["AI_REL_NDX"] = "AI 바스켓 / Nasdaq 상대"
        for seg in getattr(getattr(ai_regime, "value_chain", None), "segments", []) or []:
            if seg.rel_z_5d is not None:
                extra[f"AI_{seg.key.upper()}_REL"] = (None, seg.rel_z_5d); names[f"AI_{seg.key.upper()}_REL"] = f"{seg.label} / Nasdaq 상대"
    Z = _Z(market, extra, names, instruments_by_id)
    ms = snapshot.market_state; label = ms.primary_label.value
    theme_by_id = {t.theme_id: t for t in snapshot.themes}
    themes_cfg = {t.id: t for t in get_themes(config_dir).themes}

    # ── 1. MARKET NOW ─────────────────────────────────────────
    conv = next((str(b["label"]) for b in cfg.get("conviction_bands", []) if ms.confidence >= float(b["min"])), "LOW")
    confirmed_ids = set(ms.cross_asset_confirmation.confirmed)
    # 핵심 변수: 판정이 기대한 자산(확인된 것) 먼저, 그다음 |z| 순 — 최대 N
    cands = sorted(ms.main_drivers, key=lambda d: (0 if d.instrument_id in confirmed_ids else 1, -abs(d.z)))
    keyvars = [KeyVariable(id=d.instrument_id, label=d.label, z=round(d.z, 2), arrow=_arrow(d.z, hi, lo), change_display=Z.display(d.instrument_id, snapshot)) for d in cands[: int(cfg.get("key_variables_max", 4))]]  # type: ignore[arg-type]
    clauses = cfg.get("clauses", {}); parts = []
    for kv in sorted(keyvars, key=lambda k: -abs(k.z)):
        c = clauses.get(kv.id)
        if c and abs(kv.z) >= flat:
            parts.append(c[0] if kv.z > 0 else c[1])
        if len(parts) >= 3:
            break
    tail = str(cfg.get("regime_tail", {}).get(label, "이 겹친 환경이다."))
    sentence = ((f"{parts[0]}·{parts[1]}에 {parts[2]}까지 " if len(parts) > 2 else "·".join(parts) + "가 ") if parts else "뚜렷한 방향의 핵심 변수가 없지만 ") + tail
    streak = int(getattr(history, "current_streak", 0) or 0); prev = getattr(history, "previous_label", None)
    prev_s = prev.value if hasattr(prev, "value") else (str(prev) if prev else None)
    change_text = f"{LABEL_TEXT.get(prev_s, prev_s)} → {LABEL_TEXT[label]}" if prev_s else LABEL_TEXT[label]
    spark = [SparkPoint(date=p.date.isoformat(), label=p.label.value) for p in (getattr(history, "points", []) or [])][-22:]
    dh = snapshot.data_health
    now = MarketNow(label=label, secondary=ms.secondary_label.value if ms.secondary_label else None,
                    label_text=LABEL_TEXT[label] + (f" / {LABEL_TEXT[ms.secondary_label.value]}" if ms.secondary_label else ""), conviction=conv, confidence=round(ms.confidence, 1),  # type: ignore[arg-type]
                    persistence_days=streak, previous_label=prev_s, change_text=change_text, key_variables=keyvars, sentence=sentence,
                    interpretation=ms.narrative or "", spark=spark, last_update=snapshot.as_of, coverage=f"{dh.available_instruments}/{dh.expected_instruments}",
                    latency=f"최대 {dh.max_freshness_trading_days}거래일 지연" if dh.max_freshness_trading_days else "")

    # ── 2. TODAY'S MARKET DRIVERS ────────────────────────────
    dc = cfg.get("drivers", {}); w = dc.get("weights", {}); news_ref = float(dc.get("news_ref", 40))
    drivers: list[Driver] = []
    for key, spec in (dc.get("candidates") or {}).items():
        rows: list[EvidenceRow] = []; num = den = tot = 0.0; persist = 0; n_avail = 0
        for e in spec.get("evidence", []):
            iid = str(e["id"]); sign = int(e.get("sign", 1)); wt = float(e.get("weight", 1.0)); tot += wt
            z, win = Z.zmax(iid)
            if z is None:
                rows.append(EvidenceRow(id=iid, label=Z.name(iid), available=False)); continue
            num += _clip(sign * z / z_ref) * wt; den += wt; n_avail += 1
            wa = Z.week_ago(iid)
            if wa is not None and (wa > 0) == (z > 0) and abs(wa) >= flat: persist += 1
            rows.append(EvidenceRow(id=iid, label=Z.name(iid), z=_r(z), display=(Z.display(iid, snapshot) + (" (5일)" if win == 5 else "")).strip()))
        for cid in spec.get("context", []) or []:
            z, _w = Z.zmax(str(cid)); rows.append(EvidenceRow(id=str(cid), label=Z.name(str(cid)), z=_r(z), display=Z.display(str(cid), snapshot), context=True, available=z is not None))
        if den <= 0:
            continue
        strength = num / den; coverage = den / tot
        if abs(strength) < float(dc.get("min_strength", 0.25)) or coverage < float(dc.get("min_coverage", 0.5)):
            continue
        ev_ids = [str(e["id"]) for e in spec.get("evidence", [])]
        confirmed = any(i in confirmed_ids for i in ev_ids)
        t = theme_by_id.get(str(spec.get("theme"))) if spec.get("theme") else None
        tone = None if t is None else t.news_sentiment
        importance = (abs(strength) * float(w.get("strength", 1.0)) + coverage * float(w.get("coverage", 0.4)) + (float(w.get("confirmation", 0.15)) if confirmed else 0)
                      + float(w.get("persistence", 0.1)) * (persist / max(1, n_avail)) + float(w.get("news", 0.15)) * (min(1.0, abs(tone) / news_ref) if tone is not None else 0)) * float(spec.get("impact", 1.0))
        direction = "up" if strength > 0 else "down"
        why = str(spec.get("why", {}).get(direction, ""))
        if key == "long_end_rates" and direction == "up":
            be = Z.zmax("BE10Y")[0]
            if be is not None and be >= lo:
                why = str(spec.get("why_be_up", {}).get("up", why))
        lab = str(spec.get("label", key))
        if key == "ai_semi_relative" and direction == "up" and spec.get("label_resilient") and (Z.zmax("SPX")[0] or 0) < 0:
            lab = str(spec["label_resilient"])
        drivers.append(Driver(key=key, label=lab, label_ko=str(spec.get("label_ko", key)), direction=direction, arrow=_arrow(strength * z_ref, hi, lo), strength=round(strength, 3),  # type: ignore[arg-type]
                              importance=round(importance, 3), coverage=round(coverage, 2), confirmed_by_regime=confirmed, persistent=persist >= max(1, n_avail // 2),
                              news_tone=_r(tone, 0), evidence=rows, why=why))
    # 대체데이터 driver — |z| 가 클 때만
    alt_cfg = dc.get("alt", {}); alt_labels = alt_cfg.get("labels", {}); alt_n = 0
    for p in sorted((getattr(investment, "alternative", None) or []), key=lambda p: -abs(p.z or 0)):
        if p.z is None or abs(p.z) < float(alt_cfg.get("min_z", 1.2)) or p.id not in alt_labels or alt_n >= int(alt_cfg.get("max", 2)):
            continue
        spec = alt_labels[p.id]; direction = "up" if p.z > 0 else "down"
        drivers.append(Driver(key=f"alt_{p.id}", label=str(spec.get("label", p.id)), label_ko=p.label, direction=direction, arrow=_arrow(p.z, hi, lo), strength=round(_clip(p.z / z_ref), 3),  # type: ignore[arg-type]
                              importance=round(abs(_clip(p.z / z_ref)) * 0.8, 3), coverage=1.0, evidence=[EvidenceRow(id=p.id, label=p.label, z=_r(p.z), display=f"{p.change_1d:+.1f}%" if p.change_1d is not None else "")],
                              why=str(spec.get("why", {}).get(direction, "")), source="alternative")); alt_n += 1
    drivers.sort(key=lambda d: -d.importance); drivers = drivers[: int(dc.get("max", 5))]

    # ── 3. CROSS-ASSET CONFIRMATION + KEY DIVERGENCES ────────
    rows_ca: list[CrossAssetRow] = []; confirm = evaluated = 0
    for a in cfg.get("cross_assets", []):
        ids = [str(i) for i in a.get("ids", [])]; iid = next((i for i in ids if Z.zmax(i)[0] is not None), ids[0])
        z, _w = Z.zmax(iid); exp = int((a.get("expect") or {}).get(label, 0))
        if z is None:
            rows_ca.append(CrossAssetRow(key=str(a["key"]), label=str(a["label"]), instrument=iid, arrow="?", status="MISSING", note="결측")); continue
        arrow = _arrow(z, hi, lo)
        if exp == 0:
            st, note = "NEUTRAL", f"{LABEL_TEXT[label]} 판정은 이 자산에 기대 방향이 없다"
        elif abs(z) < flat:
            st, note = "FLAT", "움직임이 작다"
        elif (z > 0) == (exp > 0):
            st, note = "CONFIRM", "판정이 기대한 방향"; confirm += 1
        else:
            st, note = str(a.get("mismatch", "DIVERGE")), "판정이 기대한 방향과 반대"
        if st in ("CONFIRM", "DIVERGE", "HEADWIND"): evaluated += 1
        rows_ca.append(CrossAssetRow(key=str(a["key"]), label=str(a["label"]), instrument=iid, z=_r(z), arrow=arrow, status=st, note=note))  # type: ignore[arg-type]
    divs: list[KeyDivergence] = []
    for d in sorted(snapshot.divergences, key=lambda d: -d.severity):
        meaning = d.explanation.split(". ")[-1].strip() if d.explanation else ""
        title = " / ".join(Z.name(x) for x in d.related_assets[:2]) if d.related_assets else (d.related_theme or d.type.value)
        first = d.explanation.split(". ")[0] if d.explanation else ""
        divs.append(KeyDivergence(title=title, meaning=(first + ". " + meaning).strip(". ") if meaning and meaning != first else first, severity=round(d.severity, 0), assets=list(d.related_assets)))
    for rd in getattr(rates_regime, "divergences", None) or []:
        divs.append(KeyDivergence(title=rd.label, meaning=rd.why, severity=round(min(100.0, rd.severity * 25.0), 0), source="rates_regime", assets=list(rd.values.keys())))
    divs.sort(key=lambda d: -d.severity)
    kmax = int(cfg.get("key_divergences_max", 2))
    ca = CrossAsset(rows=rows_ca, confirm=confirm, evaluated=evaluated, divergences=divs[:kmax], total_divergences=len(divs),
                    sentence=f"{LABEL_TEXT[label]} 판정을 {confirm}/{evaluated} 자산이 확인한다." + (" 반대로 가는 자산은 괴리·역풍으로 아래에 적는다." if evaluated - confirm > 0 else ""))

    # ── 4. LEADERSHIP + THEME PULSE ──────────────────────────
    lc = cfg.get("leadership", {}); bench = str(lc.get("benchmark", "SPX")); bz5 = Z.z5(bench) or 0.0
    lrows: list[LeaderRow] = []
    def _agg(ids_w: Sequence[tuple[str, float, int]]) -> tuple[float | None, float | None, float | None, int]:
        z1s, z5s, ma, n = [], [], [], 0
        for iid, wt, dr in ids_w:
            a, b, m = Z.z1(iid), Z.z5(iid), Z.ma20(iid)
            if a is None and b is None: continue
            n += 1
            if a is not None: z1s.append((dr * a, wt))
            if b is not None: z5s.append((dr * b, wt))
            if m is not None: ma.append(dr * m > 0)
        wz = lambda xs: (sum(v * w_ for v, w_ in xs) / sum(w_ for _, w_ in xs)) if xs else None  # noqa: E731
        return wz(z1s), wz(z5s), (100.0 * sum(ma) / len(ma) if ma else None), n
    excl = set(lc.get("exclude_themes", [])); eq_only = bool(lc.get("equity_only", True))
    for tid, tc in themes_cfg.items():
        if tid in excl: continue
        price_ids = [(i.instrument_id, i.weight, i.direction) for i in tc.instruments if instruments_by_id.get(i.instrument_id)
                     and (instruments_by_id[i.instrument_id].asset_class.value == "equity" if eq_only else instruments_by_id[i.instrument_id].asset_class.value != "flow")]
        z1, z5, br, n = _agg(price_ids)
        if n == 0: continue
        rel = None if z5 is None else z5 - bz5
        lrows.append(LeaderRow(key=tid, label=tc.name, kind="theme", z_1d=_r(z1), rel_1w=_r(rel), breadth=_r(br, 0), arrow=_arrow(rel, hi / 2, lo / 2), instruments=len(price_ids), available=n))  # type: ignore[arg-type]
    dedupe = lc.get("sector_dedupe", {}) or {}
    for sid in lc.get("sectors", []):
        if str(sid) in dedupe and any(r.key == dedupe[str(sid)] for r in lrows): continue
        z1, z5, br, n = _agg([(str(sid), 1.0, 1)])
        if n == 0: continue
        rel = None if z5 is None else z5 - bz5
        lrows.append(LeaderRow(key=str(sid), label=Z.name(str(sid)), kind="sector", z_1d=_r(z1), rel_1w=_r(rel), breadth=_r(br, 0), arrow=_arrow(rel, hi / 2, lo / 2), instruments=1, available=1))  # type: ignore[arg-type]
    ranked = sorted([r for r in lrows if r.rel_1w is not None], key=lambda r: -(r.rel_1w or 0))
    min_rel = float(lc.get("min_rel", 0.3))
    leaders = [r for r in ranked if (r.rel_1w or 0) >= min_rel][: int(lc.get("leaders_max", 4))]
    laggards = [r for r in ranked[::-1] if (r.rel_1w or 0) <= -min_rel][: int(lc.get("laggards_max", 3))]
    tp = cfg.get("theme_pulse", {}); pref = float(tp.get("price_ref", 30)); nref = float(tp.get("news_ref", 30))
    rel_by = {r.key: r.rel_1w for r in lrows}
    scored = sorted(snapshot.themes, key=lambda t: -(abs(t.theme_score) + abs(t.news_sentiment or 0) * 0.5 + abs(t.price_momentum or 0) * 0.5 + (30 if any(d.related_theme == t.theme_id for d in snapshot.divergences) else 0)))
    pulse = []
    for t in scored[: int(tp.get("max", 6))]:
        pa = _arrow(None if t.price_momentum is None else t.price_momentum / pref, 1.5, 0.5); na = _arrow(None if t.news_sentiment is None else t.news_sentiment / nref, 1.5, 0.5)
        ra = _arrow(rel_by.get(t.theme_id), hi / 2, lo / 2)
        why = ("뉴스와 가격이 갈린다" if pa != "?" and na != "?" and ((pa in ("↑", "↑↑")) != (na in ("↑", "↑↑"))) and (pa != "→" and na != "→") else "")
        pulse.append(ThemePulseRow(theme_id=t.theme_id, name=t.name, price=pa, news=na, rel=ra, theme_score=round(t.theme_score, 0), news_sentiment=_r(t.news_sentiment, 0), price_momentum=_r(t.price_momentum, 0), rel_1w=rel_by.get(t.theme_id), why=why))  # type: ignore[arg-type]
    lead_sent = ((f"리더: {' · '.join(r.label for r in leaders)}. " if leaders else "1주 상대강도가 문턱을 넘는 리더가 없다. ") + (f"후미: {' · '.join(r.label for r in laggards)}." if laggards else ""))
    leadership = Leadership(leaders=leaders, laggards=laggards, all_rows=ranked, pulse=pulse, sentence=lead_sent)

    # ── 5. MARKET → STOCK TRANSMISSION ───────────────────────
    tc_ = cfg.get("transmission", {}); chains_cfg = tc_.get("chains", {}); cz = float(tc_.get("confirm_z", 0.3)); max_st = int(tc_.get("max_stocks", 5))
    inv_stocks = getattr(investment, "stocks", None) or {}
    ai_stocks = {s.id: s for s in (getattr(ai_regime, "stocks", None) or [])}
    ai_members = {m.id: m for m in (getattr(ai_regime, "members", None) or [])}
    def _stock(sid: str, expect: int) -> TransmissionStock:
        if sid in inv_stocks:
            s = inv_stocks[sid]; z = s.row.z; name = s.row.name; ch = s.row.change_1d
        elif sid in ai_stocks:
            s = ai_stocks[sid]; mk = next((a.value for a in s.axes if a.key == "market"), None); z = mk; name = s.name; ch = ai_members[sid].ret_1d if sid in ai_members else None
        else:
            return TransmissionStock(id=sid, name=sid, status="NO DATA")
        if z is None:
            return TransmissionStock(id=sid, name=name, status="NO DATA", change_1d=_r(ch))
        if expect == 0:
            st = "CONFIRMED" if abs(z) >= cz else "UNCONFIRMED"
        elif (z > 0) == (expect > 0) and abs(z) >= cz:
            st = "CONFIRMED"
        elif (z > 0) != (expect > 0) and abs(z) >= cz:
            st = "CONTRADICTED"
        else:
            st = "UNCONFIRMED"
        return TransmissionStock(id=sid, name=name, status=st, z=_r(z), change_1d=_r(ch), note=f"{'시장 축' if sid in ai_stocks else 'z'} {z:+.1f}")  # type: ignore[arg-type]
    chains: list[TransmissionChain] = []
    for d in drivers:
        spec = (chains_cfg.get(d.key) or {}).get(d.direction)
        if not spec: continue
        stocks = [_stock(str(s), int(spec.get("expect", 0))) for s in spec.get("stocks", [])][:max_st]
        chains.append(TransmissionChain(driver_key=d.key, driver_label=f"{d.label} {d.arrow}", arrow=d.arrow, mechanism=str(spec.get("mechanism", "")), industries=[str(i) for i in spec.get("industries", [])],
                                        stocks=stocks, confirmed=sum(1 for s in stocks if s.status == "CONFIRMED")))
    for c in (getattr(investment, "commodity_impact", None) or []):
        if abs(c.z) < float(dc.get("alt", {}).get("min_z", 1.2)) or not c.links: continue
        stocks = []
        for l in c.links[:max_st]:
            exp = int(l.direction) * (1 if c.z > 0 else -1)
            stocks.append(_stock(l.stock_id, exp))
        chains.append(TransmissionChain(driver_key=f"alt_{c.commodity_id}", driver_label=f"{c.label} {_arrow(c.z, hi, lo)}", arrow=_arrow(c.z, hi, lo), mechanism=" / ".join(c.industries[:3]) or "원자재 경로",  # type: ignore[arg-type]
                                        industries=list(c.industries[:3]), stocks=stocks, confirmed=sum(1 for s in stocks if s.status == "CONFIRMED"), source="commodity"))

    # ── 6. STOCK RADAR ───────────────────────────────────────
    rc = cfg.get("stock_radar", {}); rw = rc.get("weights", {}); cand: dict[str, dict] = {}
    def _add(sid: str, name: str, pts: float, sig: str, tag: str | None = None, why: str | None = None, kind: str = "why", ch: float | None = None):
        c = cand.setdefault(sid, {"name": name, "score": 0.0, "signals": [], "tag": tag or "", "why": [], "kind": kind, "change": ch})
        c["score"] += pts; c["signals"].append(sig)
        if tag and not c["tag"]: c["tag"] = tag
        if why: c["why"].append(why)
        if ch is not None and c["change"] is None: c["change"] = ch
    for u in (getattr(investment, "unusual_movers", None) or []):
        _add(u.stock_id, u.stock_name, float(rw.get("unusual", 2)) * (0.5 + u.severity / 100), "UNUSUAL", why=f"이상 거동 {u.label}")
    badge_pts = {"NEW_EVENT": ("badge_news", "NEWS", "중요 뉴스"), "EPS_REVISION": ("badge_eps", "EPS", "EPS 수정"), "ANALYST_CHANGE": ("badge_eps", "EPS", "애널리스트 변경"), "FLOW_INFLECTION": ("badge_flow", "FLOW", "수급 전환"),
                 "ALTERNATIVE_DATA_SIGNAL": ("badge_alt", "ALT", "대체데이터 신호"), "COMMODITY_IMPACT": ("badge_alt", "ALT", "원자재 영향"), "UNUSUAL_MOVE": ("unusual", "UNUSUAL", "이상 거동"),
                 "THEME_STRENGTHENING": ("badge_theme", "THEME", "테마 강화"), "THEME_WEAKENING": ("badge_theme", "THEME", "테마 약화")}
    for wr in (getattr(investment, "watchlist", None) or []):
        s = inv_stocks.get(wr.stock_id); ch = s.row.change_1d if s else None
        for b in wr.badges:
            k, sig, why = badge_pts.get(b, ("badge_news", b, b)); _add(wr.stock_id, wr.name, float(rw.get(k, 1)), sig, tag=wr.theme, why=why, ch=ch)
        if s and s.row.relative_z is not None and abs(s.row.relative_z) >= 1.0:
            _add(wr.stock_id, wr.name, float(rw.get("relative_strength", 1)), "REL", tag=wr.theme, why=f"시장 대비 {s.row.relative_z:+.1f}σ", ch=ch)
    for ts in (getattr(investment, "theme_stocks", None) or []):
        if ts.agreement == "confirmed":
            for s in ts.stocks[:2]:
                _add(s.stock_id, s.name, float(rw.get("theme_confirmed", 0.8)), "THEME", tag=ts.theme_name, why=f"{ts.theme_name} 테마 확인", ch=s.change_1d)
    for dcard in (getattr(investment, "drivers", None) or []):
        for imp in dcard.top_stocks[:2]:
            _add(imp.stock_id, imp.stock_name, float(rw.get("driver_impact", 0.8)) * imp.score / 100, "DRIVER", why=f"{dcard.label} {dcard.z:+.1f}σ 영향")
    radar_pts = {"strongest": ("radar_strongest", "AI 확인 강함"), "improving": ("radar_improving", "개선 중"), "narrative_ahead": ("radar_narrative", "뉴스 > 가격"), "macro_pressure": ("radar_macro", "매크로 압박")}
    for b in (getattr(ai_regime, "radar", None) or []):
        k, why = radar_pts.get(b.key, (None, None))
        if not k: continue
        for it in b.items[:3]:
            sid = it["id"]; st = ai_stocks.get(sid); tag = "/".join(st.segments[:2]) if st else "AI"
            _add(sid, it["name"], float(rw.get(k, 1)), b.key.upper(), tag=tag, why=it["reason"], kind="watch" if b.key in ("narrative_ahead", "macro_pressure") else "why", ch=ai_members[sid].ret_1d if sid in ai_members else None)
    radar = [RadarStock(id=sid, name=c["name"], change_1d=_r(c["change"]), tag=c["tag"] or "–", why=" · ".join(dict.fromkeys(c["why"]))[:90], kind=c["kind"], score=round(c["score"], 2), signals=list(dict.fromkeys(c["signals"])))  # type: ignore[arg-type]
             for sid, c in cand.items() if c["score"] >= float(rc.get("min_score", 1.0))]
    radar.sort(key=lambda r: -r.score); radar = radar[: int(rc.get("max", 8))]

    # ── 7. LIVE CATALYSTS ────────────────────────────────────
    cc = cfg.get("catalysts", {}); lv = cc.get("levels", {}); crit = float(lv.get("critical", 55)); high = float(lv.get("high", 35))
    stop = {"the", "and", "for", "with", "that", "this", "from", "into", "over", "amid", "after", "says", "said", "news", "of", "to", "in", "on", "a", "an", "is", "are", "as", "at", "by", "it", "its", "be", "us"}
    def toks(s: str) -> set[str]:
        return {(t[:-1] if t.endswith("s") and len(t) > 4 else t) for t in re.findall(r"[a-z0-9]{3,}|[가-힣]{2,}", s.lower()) if t not in stop}
    clusters: list[dict] = []
    for e in sorted(snapshot.events, key=lambda e: (-e.impact_score, e.timestamp)):
        tk = toks(e.event); placed = False
        for c in clusters:
            inter = len(tk & c["tokens"]); union = len(tk | c["tokens"]) or 1
            same_theme = bool(set(e.themes) & c["themes"])
            if same_theme and union and inter / union >= float(cc.get("cluster_jaccard", 0.34)):
                c["events"].append(e); c["tokens"] |= tk; placed = True; break
        if not placed:
            clusters.append({"rep": e, "events": [e], "tokens": set(tk), "themes": set(e.themes)})
    items: list[CatalystItem] = []
    conf_bands = cc.get("confidence_bands", [])
    universe_names = {sid: s.row.name for sid, s in inv_stocks.items()}
    alias_map: dict[str, list[str]] = {}
    for sid, s in inv_stocks.items():
        alias_map[sid] = [s.row.name] + list(getattr(s.meta, "aliases", []) or [])
    for sid, s in ai_stocks.items():
        alias_map.setdefault(sid, [s.name])
    for c in clusters:
        e = c["rep"]; th = [theme_by_id[t] for t in e.themes if t in theme_by_id]
        tone = e.theme_sentiment.get(th[0].theme_id, e.sentiment) if th else e.sentiment
        pm = th[0].price_momentum if th else None
        confirm_bonus = 0.3 if (pm is not None and tone and (pm > 0) == (tone > 0) and abs(pm) >= 15) else 0.0
        importance = e.impact_score / 100 * (1 + confirm_bonus) + 0.05 * min(3, len(c["events"]) - 1)
        level = "CRITICAL" if e.impact_score >= crit else "HIGH" if e.impact_score >= high else "MEDIUM"
        impacts = [f"{t.name} {'↑' if e.theme_sentiment.get(t.theme_id, e.sentiment) > 0 else '↓' if e.theme_sentiment.get(t.theme_id, e.sentiment) < 0 else '→'}" for t in th[:2]]
        rel_stocks = [n[0] for sid, n in alias_map.items() if any(a and len(a) >= 2 and a.lower() in e.event.lower() for a in n)][:4]
        impacts += [f"{n} {'↑' if tone > 0 else '↓' if tone < 0 else '→'}" for n in rel_stocks[:2]]
        conf_lbl = next((str(b["label"]) for b in conf_bands if e.confidence >= float(b["min"])), "LOW")
        pc = ("CONFIRMED — 테마 가격이 같은 방향" if confirm_bonus else "UNCONFIRMED — 테마 가격이 아직 같은 방향이 아니다") if th and pm is not None else "테마 가격 없음"
        items.append(CatalystItem(id=e.id, time=e.timestamp.astimezone(KST).strftime("%m/%d %H:%M"), tag=" / ".join(t.name for t in th[:2]) or e.event_type.value.upper(), headline=e.event[:140], level=level,  # type: ignore[arg-type]
                                  impact=" · ".join(impacts), confidence=conf_lbl, cluster_size=len(c["events"]), cluster_titles=[x.event[:100] for x in c["events"][1:6]], why=e.reason or "", related_assets=[Z.name(i) for t in th[:1] for i in t.supporting_instruments[:3]],
                                  related_stocks=rel_stocks, price_confirmation=pc, url=e.url, source=e.source, importance=round(importance, 3)))
    for a in snapshot.alerts:
        if a.type.value in set(cc.get("alert_types", [])) and a.severity >= float(cc.get("alert_min_severity", 45)):
            items.append(CatalystItem(id=a.id, time=a.last_fired_at.astimezone(KST).strftime("%m/%d %H:%M"), tag="⚠ " + a.type.value.replace("_", " "), headline=a.title, level="CRITICAL" if a.severity >= 70 else "HIGH",  # type: ignore[arg-type]
                                      kind="alert", impact=a.message[:120], confidence="", why=a.message, related_assets=[Z.name(x) for x in a.related_assets[:4]], importance=round(a.severity / 100, 3)))
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    items.sort(key=lambda i: (order[i.level], -i.importance)); items = items[: int(cc.get("max", 12))]

    # ── 8. EARNINGS PULSE — 데이터 있을 때만 ─────────────────
    an = [a for a in (getattr(investment, "analyst", None) or []) if a.available and (a.eps_revision_1m is not None or a.eps_revision_1w is not None)]
    earnings = None
    if an:
        rows = [{"name": a.stock_name, "value": f"{(a.eps_revision_1m if a.eps_revision_1m is not None else a.eps_revision_1w):+.1f}%", "arrow": "↑" if (a.eps_revision_1m or a.eps_revision_1w or 0) > 0 else "↓"} for a in sorted(an, key=lambda a: -abs(a.eps_revision_1m or a.eps_revision_1w or 0))[:6]]
        earnings = EarningsPulse(rows=rows, note=f"컨센서스 {len(an)}종목")

    # ── 9. WHAT MATTERS NEXT ─────────────────────────────────
    nxt: list[NextItem] = []
    for d in drivers:
        spec = (dc.get("candidates") or {}).get(d.key) or {}
        text = str((spec.get("next") or {}).get(d.direction, "")) if not d.key.startswith("alt_") else f"{d.label_ko} {'상승' if d.direction == 'up' else '하락'}이 이어지는가"
        if not text: continue
        lead_id = next((e.id for e in d.evidence if e.available and not e.context), None)
        z1 = Z.z1(lead_id) if lead_id else None; sgn = 1 if d.direction == "up" else -1
        ev_sign = int(next((int(e.get("sign", 1)) for e in spec.get("evidence", []) if str(e["id"]) == lead_id), 1))
        if z1 is None: st = "WATCH"
        elif (z1 * ev_sign > 0) == (sgn > 0) and abs(z1) >= flat: st = "CONFIRMING"
        elif (z1 * ev_sign > 0) != (sgn > 0) and abs(z1) >= flat: st = "REVERSING"
        else: st = "WATCH"
        nxt.append(NextItem(text=text, status=st, metric=Z.name(lead_id) if lead_id else d.label, current="–" if z1 is None else f"하루 z {z1:+.1f}σ", driver_key=d.key))  # type: ignore[arg-type]
        if len(nxt) >= int(cfg.get("what_matters_next", {}).get("max", 5)): break
    upcoming = []
    cal = snapshot.calendar
    if cal is not None:
        for ev in list(cal.in_window) + list(cal.upcoming):
            upcoming.append(UpcomingEvent(date=ev.date.isoformat(), label=ev.label, days_until=ev.days_until, verified=ev.verified))

    # ── 10. WATCHLIST (compact) ──────────────────────────────
    ind_map = {"NEW_EVENT": "NEWS", "EPS_REVISION": "EPS", "ANALYST_CHANGE": "EPS", "FLOW_INFLECTION": "FLOW", "ALTERNATIVE_DATA_SIGNAL": "ALT", "COMMODITY_IMPACT": "ALT", "UNUSUAL_MOVE": "PRICE", "THEME_STRENGTHENING": "THEME", "THEME_WEAKENING": "THEME"}
    wl = []
    for wr in sorted((getattr(investment, "watchlist", None) or []), key=lambda w: -len(w.badges)):
        s = inv_stocks.get(wr.stock_id)
        inds = list(dict.fromkeys(ind_map.get(b, b) for b in wr.badges))
        if wr.macro_driver: inds.append("MACRO")
        wl.append(WatchRow(id=wr.stock_id, name=wr.name, change_1d=_r(s.row.change_1d) if s else None, watch=wr.macro_driver or wr.theme or "", indicators=inds))
        if len(wl) >= int(cfg.get("watchlist_max", 5)): break

    # ── 11. DATA STATUS ──────────────────────────────────────
    ds = cfg.get("data_status", {}); important = set(ds.get("important", []))
    warns = [f"⚠ {Z.name(i)} stale" for i in dh.stale if i in important][:3]
    if dh.max_freshness_trading_days >= int(ds.get("stale_warn_days", 3)): warns.append(f"⚠ 최대 지연 {dh.max_freshness_trading_days}거래일")
    missing_imp = [i for i in dh.missing if i in important]
    if missing_imp: warns.append(f"⚠ 결측 {', '.join(Z.name(i) for i in missing_imp[:3])}")
    status = DataStatus(line=f"{dh.available_instruments}/{dh.expected_instruments} · 지연 {len(dh.stale)} · 최대 지연 {dh.max_freshness_trading_days}D" + (" · 뉴스 판단 수기" if dh.news_judgment == "manual" else ""),
                        warnings=warns[:4], coverage=round(dh.coverage, 2), available=dh.available_instruments, expected=dh.expected_instruments, stale=len(dh.stale), max_lag_days=dh.max_freshness_trading_days, news_judgment=dh.news_judgment)

    note = ("메인 탭은 기존 층(판정·테마·괴리·뉴스·Investment·AI/금리/유가 판별)의 값을 config/cockpit.yaml 규칙으로 고른 것이다. driver 는 |z| 순이 아니라 "
            "증거 강도 × 확보 + 크로스에셋 확인 + 지속성 + 뉴스 촉매 점수로 뽑는다. 확인 n/m 은 확률이 아니다. 데이터가 없는 카드는 숨긴다. 전체 표·진단은 Details / Diagnostics 에 있다.")
    return Cockpit(as_of=snapshot.as_of, market_now=now, drivers=drivers, cross_asset=ca, leadership=leadership, transmission=chains, radar=radar, catalysts=items,
                   earnings=earnings, what_matters_next=nxt, upcoming=upcoming, watchlist=wl, data_status=status, note=note)
