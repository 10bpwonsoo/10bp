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
    Horizon, LeaderRow, Leadership, MarketNow, NextItem, RadarStock, RegimeHistory, SparkPoint, SystemAxis, ThemePulseRow, TransmissionChain, TransmissionStock, UpcomingEvent, WatchLink, WatchRow,
)
from ..models.market import Instrument, MarketSnapshot
from .korean import fix_particles
from .regime_history import StateObservation, build_regime_history
from .issue_path import Observer, build_issue_path
from .leadership_intel import build_leadership_intel, leadership_read, load_street_views
from ..models.snapshot import IntelligenceSnapshot

KST = timezone(timedelta(hours=9))
LABEL_TEXT = {"RISK_ON": "RISK-ON", "RISK_OFF": "RISK-OFF", "GROWTH_SHOCK": "GROWTH SHOCK", "INFLATION_SHOCK": "INFLATION SHOCK", "LIQUIDITY_STRESS": "LIQUIDITY STRESS",
              "POLICY_DRIVEN": "POLICY DRIVEN", "GEOPOLITICAL_RISK": "GEOPOLITICAL RISK", "NEUTRAL": "NEUTRAL / MIXED"}  # 2026-10-22: NEUTRAL 은 어디서나 Neutral / Mixed
LABEL_KO = {"RISK_ON": "위험선호", "RISK_OFF": "위험회피", "GROWTH_SHOCK": "성장 충격", "INFLATION_SHOCK": "물가 충격", "LIQUIDITY_STRESS": "유동성 경색",
            "POLICY_DRIVEN": "정책 주도", "GEOPOLITICAL_RISK": "지정학 위험", "NEUTRAL": "중립·혼조"}


@lru_cache(maxsize=4)
def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_cockpit_config(config_dir: Path | None = None) -> dict:
    return _load((config_dir or CONFIG_DIR) / "cockpit.yaml")


def _clip(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _tax_key(cfg: Mapping, label: str) -> str:
    """StateLabel → history taxonomy key (risk_on · neutral · liquidity_stress …). 히스토리가 없을 때 tone 확인에 쓴다."""
    t = ((cfg.get("history") or {}).get("taxonomy") or {}).get(label)
    return str(t["key"]) if t else label.lower()


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


def _now_sentence(cfg: Mapping, keyvars: Sequence[KeyVariable], label: str, flat: float) -> str:
    clauses = cfg.get("clauses", {}); parts: list[str] = []
    for kv in sorted(keyvars, key=lambda k: -abs(k.z)):
        c = clauses.get(kv.id)
        if c and abs(kv.z) >= flat:
            parts.append(c[0] if kv.z > 0 else c[1])
        if len(parts) >= 3:
            break
    tail = str(cfg.get("regime_tail", {}).get(label, "이 겹친 환경이다."))
    if not parts and tail.startswith("있지만 "):
        # NEUTRAL 꼬리는 'X이(가) 있지만 …' 을 전제한다 — 핵심 변수 문구가 없을 때 '없지만 있지만' 이 겹치지 않게(2026-10-14)
        return fix_particles("뚜렷한 방향의 핵심 변수가 없고 " + tail[len("있지만 "):])
    return fix_particles(((f"{parts[0]}·{parts[1]}에 {parts[2]}까지 " if len(parts) > 2 else "·".join(parts) + "이(가) ") if parts else "뚜렷한 방향의 핵심 변수가 없지만 ") + tail)


NOW_READ_KEY = {"STABLE": "confirmed", "PENDING": "watch", "CONFIRMED": "changed", "NO_HISTORY": "no_history"}


def now_regime_fields(cfg: Mapping, rh: RegimeHistory | None, *, raw_label: str, raw_secondary: str | None, keyvars: Sequence[KeyVariable], flat: float) -> dict:
    """
    MARKET NOW 의 공식 판정 칸 — MARKET REGIME HISTORY 와 같은 rh.state 에서만 만든다(2026-10-22).
    label = Daily Snapshot 의 공식(confirmed) regime, raw_* = 마지막 Daily Snapshot 의 신호(CURRENT SIGNAL), 장중 LIVE 는 state.live_signal.
    rh 가 없으면(저장 sequence 없음) 지금 raw 를 그대로 공식으로 쓴다(NO_HISTORY). 아카이브 화면도 이 함수로 다시 그린다.
    """
    inv_tax = {str(v["key"]): str(k) for k, v in ((cfg.get("history") or {}).get("taxonomy") or {}).items() if str(k) != "RISK_OFF"}
    nr = cfg.get("now_read", {}) or {}
    st = rh.state if rh is not None else None
    if rh is None or st is None or st.official_state not in LABEL_TEXT:
        label = raw_label if raw_label in LABEL_TEXT else "NEUTRAL"
        read = fix_particles(str(nr.get("no_history", "")))
        return dict(label=label, label_text=LABEL_TEXT[label], persistence_days=0, previous_label=None, change_text="", raw_label=label, raw_text=LABEL_TEXT[label],
                    raw_secondary=raw_secondary, raw_persistence_days=0, transition_status="NO_HISTORY", transition_status_ko="저장된 판정 sequence 가 없어 raw 판정을 그대로 공식 regime 으로 쓴다",
                    potential_change_text="", required_days=0, conviction_trend="STABLE", read=read, spark=[], sentence=_now_sentence(cfg, keyvars, label, flat), state=None)
    label = st.official_state
    raw = st.raw_state if st.raw_state in LABEL_TEXT else label
    prev_s = inv_tax.get(st.previous_regime or "", None)
    last = rh.days[-1]
    change_text = f"{LABEL_TEXT.get(prev_s or '', prev_s or '')} → {LABEL_TEXT[label]}" if (st.transition_status == "CONFIRMED" and prev_s) else ""
    potential = f"{LABEL_TEXT[label]} → {LABEL_TEXT.get(raw, raw)}" if st.transition_status == "PENDING" else ""
    ev = [d.evidence_strength for d in rh.days]
    dlt = float((cfg.get("conviction_trend") or {}).get("delta", 10))
    c_trend = "STABLE" if len(ev) < 2 else ("WEAKENING" if ev[-1] - ev[-2] <= -dlt else "STRENGTHENING" if ev[-1] - ev[-2] >= dlt else "STABLE")
    read = fix_particles(str(nr.get(NOW_READ_KEY.get(st.transition_status, "confirmed"), "")).format(official=LABEL_TEXT[label], raw=LABEL_TEXT.get(raw, raw),
                                                                                                    prev=LABEL_TEXT.get(prev_s or "", prev_s or ""), n=st.transition_days, need=st.required_days))
    lv = st.live_signal
    if lv is not None and lv.state and lv.state != raw and lv.state in LABEL_TEXT:
        read += " " + fix_particles(str(nr.get("live", "")).format(live=LABEL_TEXT[lv.state]))
    spark = [SparkPoint(date=d.date, label=inv_tax.get(d.display_regime, d.raw_state)) for d in rh.days][-22:]  # 공식(confirmed) regime 의 띠 — Daily Snapshot 만
    return dict(label=label, label_text=LABEL_TEXT[label], persistence_days=st.official_days, previous_label=prev_s, change_text=change_text, raw_label=raw, raw_text=LABEL_TEXT.get(raw, raw),
                raw_secondary=last.raw_secondary, raw_persistence_days=st.transition_days, transition_status=st.transition_status, transition_status_ko=st.transition_status_ko,
                potential_change_text=potential, required_days=st.required_days, conviction_trend=c_trend, read=read.strip(), spark=spark,
                sentence=_now_sentence(cfg, keyvars, label, flat), state=st)


def cross_eval(cfg: Mapping, label: str, rows: Sequence[CrossAssetRow], *, flat: float, z_raw: Mapping[str, float | None] | None = None) -> dict:
    """
    CROSS-ASSET CONFIRMATION — 공식 regime(label)이 기대한 방향과 각 자산의 z 를 맞춰 본다. 행의 z 는 그대로 두고 상태·문장만 만든다.
    아카이브 화면은 저장된 z 로 이 함수를 다시 불러 공식 regime 기준(2026-10-22)으로 그린다.
    """
    ex = cfg.get("explain", {}) or {}
    regime_short = str((ex.get("regime_short") or {}).get(label, LABEL_TEXT[label]))
    cm = ex.get("cross_meaning") or {}
    spec = {str(a["key"]): a for a in cfg.get("cross_assets", [])}

    def _meaning(st: str, key: str) -> str:
        m = cm.get(st) or {}
        return str(m.get(key) or m.get("default") or "").replace("{regime}", regime_short)

    out: list[CrossAssetRow] = []; confirm = evaluated = 0
    for r in rows:
        a = spec.get(r.key) or {}
        z = (z_raw or {}).get(r.key, r.z) if z_raw is not None else r.z
        if z is None or r.status == "MISSING":
            out.append(r.model_copy(update={"status": "MISSING", "note": "결측", "meaning": _meaning("MISSING", r.key)})); continue
        exp = int((a.get("expect") or {}).get(label, 0))
        if exp == 0:
            st, note = "NEUTRAL", f"{LABEL_TEXT[label]} 판정은 이 자산에 기대 방향이 없다"
        elif abs(z) < flat:
            st, note = "FLAT", "움직임이 작다"
        elif (z > 0) == (exp > 0):
            st, note = "CONFIRM", "판정이 기대한 방향"; confirm += 1
        else:
            st, note = str(a.get("mismatch", "DIVERGE")), "판정이 기대한 방향과 반대"
        if st in ("CONFIRM", "DIVERGE", "HEADWIND"): evaluated += 1
        out.append(r.model_copy(update={"status": st, "note": note, "meaning": _meaning(st, r.key)}))
    # MARKET READ — 숫자를 반복하지 않고, 확인한 자산군 · 역풍 · 괴리를 1~2문장으로
    gko = ex.get("cross_group_ko") or {}
    conf_names = [str(gko.get(r.key, r.label)) for r in out if r.status == "CONFIRM"]
    head_rows = [r for r in out if r.status == "HEADWIND"]; div_rows = [r for r in out if r.status == "DIVERGE"]

    def _josa(word: str, with_b: str, without_b: str) -> str:
        ch = word[-1] if word else ""
        has_b = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0
        return word + (with_b if has_b or not ("가" <= ch <= "힣") else without_b)
    if conf_names:
        read = f"{_josa('·'.join(conf_names), '이', '가')} {regime_short} 판단을 확인하고 있습니다."
    else:
        read = f"{regime_short} 판단을 같은 방향으로 확인하는 자산군이 아직 없습니다."
    if head_rows:
        read += " " + " ".join(f"{_josa(str(gko.get(r.key, r.label)) + (' 상승' if (r.z or 0) > 0 else ' 하락'), '이', '가')} 위험자산에 추가 부담을 주고 있습니다." for r in head_rows[:2])
    if div_rows:
        read += " 다만 " + _josa("·".join(str(gko.get(r.key, r.label)) for r in div_rows[:2]), "은", "는") + " 전형적인 패턴과 다르게 움직이고 있습니다."
    n_rows = len(out)
    return dict(rows=out, confirm=confirm, evaluated=evaluated,
                sentence=f"{LABEL_TEXT[label]} 판정을 {confirm}/{evaluated} 자산이 확인한다." + (" 반대로 가는 자산은 괴리·역풍으로 아래에 적는다." if evaluated - confirm > 0 else ""),
                current_view=LABEL_TEXT[label], regime_short=regime_short,
                confirm_text=f"{n_rows}개 주요 자산군 중 {confirm}개가 현재 {regime_short} 판단과 같은 방향" + (f" · 평가 제외 {n_rows - evaluated}개(방향 없음·결측)" if n_rows - evaluated > 0 else ""),
                market_read=read)


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
    observations: Sequence[StateObservation] = (),
    stored_days: int | None = None,
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

    # ── 1b. MARKET REGIME HISTORY · 1M (실시간 2 전용) ────────
    hz_ids = [str((d.get("horizon") or {}).get("id")) for d in (cfg.get("history", {}).get("drivers") or []) if d.get("horizon")]
    # 공식 판정은 Daily Snapshot 만으로 정한다 — MARKET NOW 와 History 가 같은 state 를 쓴다(2026-10-22). 장중 LIVE 는 state.live_signal
    regime_history = build_regime_history(history, cfg.get("history", {}), observations=observations, as_of=snapshot.as_of, stored_days=stored_days,
                                          horizon_z={i: (Z.z1(i), Z.z5(i)) for i in hz_ids}) if history is not None else None
    raw_label = label

    # ── 1. MARKET NOW ─────────────────────────────────────────
    conv = next((str(b["label"]) for b in cfg.get("conviction_bands", []) if ms.confidence >= float(b["min"])), "LOW")
    confirmed_ids = set(ms.cross_asset_confirmation.confirmed)
    # 핵심 변수: 판정이 기대한 자산(확인된 것) 먼저, 그다음 |z| 순 — 최대 N
    cands = sorted(ms.main_drivers, key=lambda d: (0 if d.instrument_id in confirmed_ids else 1, -abs(d.z)))
    keyvars = [KeyVariable(id=d.instrument_id, label=d.label, z=round(d.z, 2), arrow=_arrow(d.z, hi, lo), change_display=Z.display(d.instrument_id, snapshot)) for d in cands[: int(cfg.get("key_variables_max", 4))]]  # type: ignore[arg-type]
    rf = now_regime_fields(cfg, regime_history, raw_label=raw_label, raw_secondary=ms.secondary_label.value if ms.secondary_label else None, keyvars=keyvars, flat=flat)
    label = rf["label"]
    dh = snapshot.data_health
    now = MarketNow(secondary=None, conviction=conv, confidence=round(ms.confidence, 1), key_variables=keyvars,  # type: ignore[arg-type]
                    interpretation=ms.narrative or "", last_update=snapshot.as_of, coverage=f"{dh.available_instruments}/{dh.expected_instruments}",
                    latency=f"최대 {dh.max_freshness_trading_days}거래일 지연" if dh.max_freshness_trading_days else "", **rf)

    # ── 1c. MARKET TONE SNAPSHOT (2026-10-07) — 온도계를 그대로, regime 과 대조 ──
    from .market_tone import build_market_tone
    _rk = regime_history.current_regime if regime_history is not None else _tax_key(cfg, label)
    _rl = regime_history.current_label if regime_history is not None else LABEL_TEXT.get(label, label)
    market_tone = build_market_tone(snapshot.thermometer, cfg.get("tone", {}) or {}, regime_key=_rk, regime_label=_rl, history_points=list(getattr(history, "points", []) or []))

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
    ex = cfg.get("explain", {}) or {}
    base_ca: list[CrossAssetRow] = []
    for a in cfg.get("cross_assets", []):
        ids = [str(i) for i in a.get("ids", [])]; iid = next((i for i in ids if Z.zmax(i)[0] is not None), ids[0])
        z, _w = Z.zmax(iid)
        grp = str(a.get("group", "RISK"))
        base_ca.append(CrossAssetRow(key=str(a["key"]), label=str(a["label"]), instrument=iid, instrument_label=Z.name(iid), group=grp, z=_r(z) if z is not None else None,  # type: ignore[arg-type]
                                     arrow=_arrow(z, hi, lo) if z is not None else "?", status="MISSING" if z is None else "NEUTRAL", note="결측" if z is None else ""))
    dnotes = ex.get("divergence_notes") or {}
    def _note(assets: Sequence[str]) -> dict:
        ids = list(assets[:2])
        return dict(dnotes.get("|".join(ids)) or dnotes.get("|".join(reversed(ids))) or {})
    dir_ko = {"up": "상승", "down": "하락", "flat": "제자리"}
    divs: list[KeyDivergence] = []
    for d in sorted(snapshot.divergences, key=lambda d: -d.severity):
        meaning = d.explanation.split(". ")[-1].strip() if d.explanation else ""
        title = " / ".join(Z.name(x) for x in d.related_assets[:2]) if d.related_assets else (d.related_theme or d.type.value)
        first = d.explanation.split(". ")[0] if d.explanation else ""
        nt = _note(d.related_assets)
        legs = list(d.legs)
        phen = str(nt.get("phenomenon") or (f"{legs[0].name}는 {dir_ko.get(legs[0].direction, legs[0].direction)}인데 {legs[1].name}는 {dir_ko.get(legs[1].direction, legs[1].direction)}" if len(legs) >= 2 else first))
        why = str(nt.get("why") or meaning or first)
        ref = [f"{lg.name} {lg.value:+.0f}" + (f" (z {lg.z:+.1f}σ)" if lg.z is not None else "") for lg in legs[:2]]
        if d.type.value == "CORRELATION_REGIME" and len(legs) >= 2:
            ref = [f"Expected relationship {legs[0].value:+.0f}", f"Recent correlation {legs[1].value:+.0f}"]
        divs.append(KeyDivergence(title=title, meaning=(first + ". " + meaning).strip(". ") if meaning and meaning != first else first, severity=round(d.severity, 0), assets=list(d.related_assets),
                                  phenomenon=phen, why=why, reference=ref))
    for rd in getattr(rates_regime, "divergences", None) or []:
        ids = list(rd.values.keys()); nt = _note(ids)
        divs.append(KeyDivergence(title=rd.label, meaning=rd.why, severity=round(min(100.0, rd.severity * 25.0), 0), source="rates_regime", assets=ids,
                                  phenomenon=str(nt.get("phenomenon") or rd.label), why=str(nt.get("why") or rd.why), reference=[f"{Z.name(k)} z {v:+.1f}σ" for k, v in list(rd.values.items())[:3] if v is not None]))
    divs.sort(key=lambda d: -d.severity)
    kmax = int(cfg.get("key_divergences_max", 2))
    ca = CrossAsset(divergences=divs[:kmax], total_divergences=len(divs), **cross_eval(cfg, label, base_ca, flat=flat, z_raw={r.key: Z.zmax(r.instrument)[0] for r in base_ca}))

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
    ind_lbl = tc_.get("industry_labels") or {}
    def _industry(sid: str) -> str:
        if sid in inv_stocks:
            k = str(getattr(inv_stocks[sid].meta, "industry", "") or "")
        elif sid in ai_stocks and ai_stocks[sid].segments:
            k = str(ai_stocks[sid].segments[0])
        else:
            k = ""
        return str(ind_lbl.get(k, k))
    def _stock(sid: str, expect: int) -> TransmissionStock:
        if sid in inv_stocks:
            s = inv_stocks[sid]; z = s.row.z; name = s.row.name; ch = s.row.change_1d
        elif sid in ai_stocks:
            s = ai_stocks[sid]; mk = next((a.value for a in s.axes if a.key == "market"), None); z = mk; name = s.name; ch = ai_members[sid].ret_1d if sid in ai_members else None
        else:
            return TransmissionStock(id=sid, name=sid, status="NO DATA")
        if z is None:
            return TransmissionStock(id=sid, name=name, status="NO DATA", change_1d=_r(ch), industry=_industry(sid))
        if expect == 0:
            st = "CONFIRMED" if abs(z) >= cz else "UNCONFIRMED"
        elif (z > 0) == (expect > 0) and abs(z) >= cz:
            st = "CONFIRMED"
        elif (z > 0) != (expect > 0) and abs(z) >= cz:
            st = "CONTRADICTED"
        else:
            st = "UNCONFIRMED"
        return TransmissionStock(id=sid, name=name, status=st, z=_r(z), change_1d=_r(ch), note=f"{'시장 축' if sid in ai_stocks else 'z'} {z:+.1f}", industry=_industry(sid))  # type: ignore[arg-type]
    # TRANSMISSION STRENGTH + READ — 확인 비율 × driver 강도. 원인을 단정하지 않고 '확인되고 있다 / 점검 필요' 로 쓴다.
    sc = tc_.get("strength") or {}; sko = tc_.get("strength_ko") or {}; subj_cfg = tc_.get("subject_ko") or {}
    def _strength(stocks: list[TransmissionStock], dstrength: float | None) -> tuple[str, int]:
        ev = [x for x in stocks if x.status != "NO DATA"]; conf = sum(1 for x in ev if x.status == "CONFIRMED")
        if len(ev) < int(sc.get("min_evaluated", 2)) or conf == 0:
            return ("UNCONFIRMED" if conf == 0 else "LIMITED"), len(ev)
        ratio = conf / len(ev)
        if ratio >= float(sc.get("strong", 0.66)) and (dstrength is None or abs(dstrength) >= float(sc.get("driver_min", 0.35))):
            return "STRONG", len(ev)
        if ratio >= float(sc.get("partial", 0.4)):
            return "PARTIAL", len(ev)
        return "LIMITED", len(ev)
    def _read(subject: str, expect: int, stocks: list[TransmissionStock], strength: str) -> str:
        conf = [x for x in stocks if x.status == "CONFIRMED"]; contra = [x for x in stocks if x.status == "CONTRADICTED"]; unc = [x for x in stocks if x.status == "UNCONFIRMED"]
        inds = lambda xs: " · ".join(dict.fromkeys(x.industry or x.name for x in xs))  # noqa: E731
        if strength == "STRONG":
            s1 = f"{subject}이 {inds(conf)} 까지 실제 가격에서 폭넓게 확인되고 있다."
        elif strength == "PARTIAL":
            s1 = f"{subject}은 {inds(conf)} 에서 먼저 확인되고 있으나 " + (f"{inds(unc + contra)} 로의 확산 여부는 추가 확인이 필요하다." if (unc or contra) else "확산은 아직 일부다.")
        elif strength == "LIMITED":
            s1 = f"{subject} 자체는 나타났지만 종목 전반으로의 가격 전파는 아직 제한적이다" + (f" ({inds(conf)} 만 확인)." if conf else ".")
        else:
            s1 = f"{subject}은 아직 종목 가격에서 확인되지 않는다" + (f" — {inds(unc)} 는 움직임이 작다." if unc else ".")
        s2 = ""
        if contra:
            names = " · ".join(x.name for x in contra[:3])
            s2 = f" {names} 는 예상과 다르게 {'상대강도를 유지한다' if expect < 0 else '약세다'} — 종목·테마 고유 driver 가능성을 점검할 필요가 있다."
        return (s1 + s2).strip()
    chains: list[TransmissionChain] = []
    for d in drivers:
        spec = (chains_cfg.get(d.key) or {}).get(d.direction)
        if not spec: continue
        stocks = [_stock(str(s), int(spec.get("expect", 0))) for s in spec.get("stocks", [])][:max_st]
        strength, n_ev = _strength(stocks, d.strength)
        subject = str((subj_cfg.get(d.key) or {}).get(d.direction) or f"{d.label_ko} {'상승' if d.direction == 'up' else '하락'}의 영향")
        chains.append(TransmissionChain(driver_key=d.key, driver_label=f"{d.label} {d.arrow}", arrow=d.arrow, mechanism=str(spec.get("mechanism", "")), industries=[str(i) for i in spec.get("industries", [])],
                                        stocks=stocks, confirmed=sum(1 for s in stocks if s.status == "CONFIRMED"), evaluated=n_ev, strength=strength, strength_ko=str(sko.get(strength, "")),  # type: ignore[arg-type]
                                        read=_read(subject, int(spec.get("expect", 0)), stocks, strength)))
    for c in (getattr(investment, "commodity_impact", None) or []):
        if abs(c.z) < float(dc.get("alt", {}).get("min_z", 1.2)) or not c.links: continue
        stocks = []
        for l in c.links[:max_st]:
            exp = int(l.direction) * (1 if c.z > 0 else -1)
            stocks.append(_stock(l.stock_id, exp))
        strength, n_ev = _strength(stocks, c.z / 2.0)
        chains.append(TransmissionChain(driver_key=f"alt_{c.commodity_id}", driver_label=f"{c.label} {_arrow(c.z, hi, lo)}", arrow=_arrow(c.z, hi, lo), mechanism=" / ".join(c.industries[:3]) or "원자재 경로",  # type: ignore[arg-type]
                                        industries=list(c.industries[:3]), stocks=stocks, confirmed=sum(1 for s in stocks if s.status == "CONFIRMED"), source="commodity", evaluated=n_ev, strength=strength, strength_ko=str(sko.get(strength, "")),
                                        read=_read(f"{c.label} {'상승' if c.z > 0 else '하락'}의 영향", 1 if c.z > 0 else -1, stocks, strength)))

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

    # ── 4b. LEADERSHIP INTELLIGENCE — 왜 강한가 · 확인 · 질 · 종목 · 외부 view (섹션 5·6 의 종목 자료를 쓴다) ──
    li = cfg.get("leadership_intel", {}) or {}
    ex_ = cfg.get("explain", {}) or {}
    rs_ = str((ex_.get("regime_short") or {}).get(label, LABEL_TEXT[label]))
    segments_li = {str(sg.key): sg for sg in (getattr(getattr(ai_regime, "value_chain", None), "segments", None) or [])}
    def _stock_li(sid: str):
        if sid in inv_stocks:
            st = inv_stocks[sid]; return (st.row.name, st.row.relative_z if st.row.relative_z is not None else st.row.z, str(getattr(st.meta, "industry", "") or ""))
        if sid in ai_stocks:
            st = ai_stocks[sid]; mk = next((a.value for a in st.axes if a.key == "market"), None)
            return (st.name, mk, str(st.segments[0]) if st.segments else "")
        return None
    street = load_street_views(Path(__file__).resolve().parents[1] / str(li.get("street_path", "data/street_views/manual")), as_of=snapshot.as_of, max_age_days=int(li.get("street_max_age_days", 30)))
    lead_ids = {r.key for r in leaders}
    radar_ids_li = {r.id for r in radar}
    tr_stages = {str(st.key): st for st in (getattr(getattr(ai_regime, "transmission", None), "stages", None) or [])}
    def _fund_of(seg_key: str) -> tuple[float | None, str]:
        st = tr_stages.get(seg_key)
        return (None, "") if st is None or getattr(st, "score", None) is None else (float(st.score), f"{st.label} 전파 {st.status}")
    enriched = build_leadership_intel(leaders + laggards, li, z_of=lambda k: Z.zmax(k)[0], name_of=Z.name, themes=theme_by_id, segments=segments_li, stock_of=_stock_li,
                                      radar_ids=radar_ids_li, street=street, regime_short=rs_, is_leader=lambda r: r.key in lead_ids, fund_of=_fund_of)
    leaders = [r for r in enriched if r.key in lead_ids]; laggards = [r for r in enriched if r.key not in lead_ids]
    leadership = leadership.model_copy(update={"leaders": leaders, "laggards": laggards, "read": leadership_read(leaders, laggards, regime_short=rs_, label=label)})

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
        f = market.features.get(lead_id) if lead_id else None
        z5 = f.z_5d if f is not None else (Z.z5(lead_id) if lead_id else None); z20 = f.z_20d if f is not None else None
        hz = [Horizon(key="1D", z=_r(z1), arrow=_arrow(z1, hi, lo)), Horizon(key="5D", z=_r(z5), arrow=_arrow(z5, hi, lo))]  # type: ignore[arg-type]
        if z20 is not None: hz.append(Horizon(key="1M", z=_r(z20), arrow=_arrow(z20, hi, lo)))  # type: ignore[arg-type]
        hr = cfg.get("explain", {}).get("horizon_read") or {}
        if z1 is None or z5 is None: hread = ""
        elif abs(z1) < flat and abs(z5) < flat: hread = str(hr.get("flat", ""))
        elif abs(z5) >= flat and (abs(z1) < flat or (z1 > 0) == (z5 > 0)) and abs(z1) < abs(z5): hread = str(hr.get("same_up" if z5 > 0 and abs(z1) >= flat else "same_down" if z5 < 0 and abs(z1) >= flat else ("pullback_up" if z5 > 0 else "pullback_down"), ""))
        elif abs(z5) >= flat and (z1 > 0) != (z5 > 0): hread = str(hr.get("pullback_up" if z5 > 0 else "pullback_down", ""))
        elif abs(z5) >= flat and (z1 > 0) == (z5 > 0): hread = str(hr.get("same_up" if z5 > 0 else "same_down", ""))
        else: hread = str(hr.get("turn_up" if z1 > 0 else "turn_down", ""))
        wn = str((spec.get("why_next") or {}).get(d.direction, "")) or d.why
        nxt.append(NextItem(text=text, status=st, metric=Z.name(lead_id) if lead_id else d.label, current="–" if z1 is None else f"하루 z {z1:+.1f}σ", driver_key=d.key, horizons=hz, horizon_read=hread, why_next=wn))  # type: ignore[arg-type]
        if len(nxt) >= int(cfg.get("what_matters_next", {}).get("max", 5)): break
    # ── 9b. MARKET TRANSMISSION PATH — 이슈가 더 진행되면 어디로 번지는가 (예상 vs 관측) ──
    wm = cfg.get("what_matters_next", {}); paths_cfg = wm.get("paths") or {}
    segments = {str(sg.key): sg for sg in (getattr(getattr(ai_regime, "value_chain", None), "segments", None) or [])}
    def _stock_obs(sid: str):
        if sid in inv_stocks:
            st = inv_stocks[sid]; return (st.row.name, st.row.z, st.row.change_1d, str(getattr(st.meta, "industry", "") or ""))
        if sid in ai_stocks:
            st = ai_stocks[sid]; mk = next((a.value for a in st.axes if a.key == "market"), None)
            return (st.name, mk, ai_members[sid].ret_1d if sid in ai_members else None, str(st.segments[0]) if st.segments else "")
        return None
    theme_scale = float(wm.get("theme_confirm", 20)) / max(1e-6, float(wm.get("confirm_z", 0.5)))
    observer = Observer(z_of=lambda k: Z.zmax(k)[0], name_of=Z.name, segments=segments, themes=theme_by_id, theme_scale=theme_scale, stock_of=_stock_obs)
    radar_ids = {r.id for r in radar}
    with_paths: list[NextItem] = []
    for it in nxt:
        d = next((x for x in drivers if x.key == it.driver_key), None)
        spec = ((paths_cfg.get(it.driver_key) or {}).get(d.direction) if d is not None else None) or None
        path = build_issue_path(spec, wm, observer, radar_ids=radar_ids, ai_regime=ai_regime, driver_label=d.label if d else it.metric, explain=cfg.get("explain", {})) if spec else None
        with_paths.append(it.model_copy(update={"id": f"{it.driver_key}:{d.direction if d else 'na'}", "path": path}))
    nxt = with_paths
    # STOCK RADAR ↔ ISSUE 양방향: radar 종목의 시스템 축과 관련 이슈
    issue_of_stock: dict[str, list[str]] = {}
    for it in nxt:
        if it.path is None: continue
        for t in it.path.tiers:
            for ps in t.stocks:
                issue_of_stock.setdefault(ps.id, []).append(it.id)
    def _axes(sid: str) -> list[SystemAxis]:
        if sid in ai_stocks:
            return [SystemAxis(key=a.key, label=a.key.upper(), arrow=a.arrow, detail=a.detail) for a in ai_stocks[sid].axes]  # type: ignore[arg-type]
        if sid in inv_stocks:
            r = inv_stocks[sid].row; out = []
            if r.z is not None: out.append(SystemAxis(key="market", label="MARKET", arrow=_arrow(r.z, hi, lo), detail=f"하루 z {r.z:+.1f}σ"))  # type: ignore[arg-type]
            if r.relative_z is not None: out.append(SystemAxis(key="relative", label="RELATIVE", arrow=_arrow(r.relative_z, hi, lo), detail=f"시장 대비 {r.relative_z:+.1f}σ"))  # type: ignore[arg-type]
            return out
        return []
    radar = [r.model_copy(update={"system_axes": _axes(r.id), "related_issues": issue_of_stock.get(r.id, [])}) for r in radar]
    upcoming = []
    cal = snapshot.calendar
    if cal is not None:
        for ev in list(cal.in_window) + list(cal.upcoming):
            upcoming.append(UpcomingEvent(date=ev.date.isoformat(), label=ev.label, days_until=ev.days_until, verified=ev.verified))

    # ── 10. WATCHLIST — 오늘 다시 확인해야 할 종목과 기다리는 trigger (radar 는 '이미 움직인 것', 여기는 '다음에 무엇을 볼 것인가') ──
    ind_map = {"NEW_EVENT": "NEWS", "EPS_REVISION": "EPS", "ANALYST_CHANGE": "EPS", "FLOW_INFLECTION": "FLOW", "ALTERNATIVE_DATA_SIGNAL": "ALT", "COMMODITY_IMPACT": "ALT", "UNUSUAL_MOVE": "PRICE", "THEME_STRENGTHENING": "THEME", "THEME_WEAKENING": "THEME"}
    wc = cfg.get("watchlist", {}) or {}; ww = wc.get("weights") or {}; dl = wc.get("driver_labels") or {}; whints = wc.get("hints") or {}
    lead_keys = {r.label: r for r in leaders}; lag_keys = {r.label: r for r in laggards}
    chain_of_stock: dict[str, list[WatchLink]] = {}
    for ch_ in chains:
        for st_ in ch_.stocks:
            chain_of_stock.setdefault(st_.id, []).append(WatchLink(key=ch_.driver_key, label=ch_.driver_label))
    issue_of_stock_w: dict[str, list[WatchLink]] = {}
    for it in nxt:
        if it.path is None: continue
        for t in it.path.tiers:
            for ps in t.stocks:
                issue_of_stock_w.setdefault(ps.id, []).append(WatchLink(key=it.id, label=it.text))
    def _arrow_word(v: float | None, up: str, down: str, flat: str, thr: float = 0.8, lo_: float = 0.3) -> str:
        if v is None: return ""
        return up if v >= thr else down if v <= -thr else flat if abs(v) < lo_ else (up if v > 0 else down)
    cand_w: list[tuple[float, WatchRow]] = []
    for wr in (getattr(investment, "watchlist", None) or []):
        s_ = inv_stocks.get(wr.stock_id); row = s_.row if s_ else None; meta = s_.meta if s_ else None
        h = dict(whints.get(wr.stock_id) or {})
        inds = list(dict.fromkeys(ind_map.get(b_, b_) for b_ in wr.badges))
        if wr.macro_driver: inds.append("MACRO")
        # 선정 점수 — 수익률 순 아님
        score = float(ww.get("badge", 1.0)) * len(wr.badges)
        rel = row.relative_z if row is not None else None
        if rel is not None: score += float(ww.get("relative", 0.6)) * min(2.0, abs(rel))
        if wr.macro_driver and wr.macro_impact is not None: score += float(ww.get("macro", 0.8)) * min(1.0, abs(wr.macro_impact) / 10.0)
        theme_lead = wr.theme in lead_keys or wr.theme in lag_keys
        if theme_lead: score += float(ww.get("theme_lead", 0.8))
        if wr.stock_id in chain_of_stock: score += float(ww.get("transmission", 0.9))
        if wr.stock_id in issue_of_stock_w: score += float(ww.get("issue", 0.7))
        if wr.alt_signal: score += float(ww.get("alt", 0.6))
        if wr.stock_id in radar_ids: score += float(ww.get("radar_penalty", -0.3))
        # WHY WATCH — 지금 데이터만: 테마 leadership 상태 + 가격 confirmation + 매크로/뉴스/대체데이터
        ai_st = ai_stocks.get(wr.stock_id)
        axes_ = {a_.key: a_ for a_ in (ai_st.axes if ai_st else [])}
        # 앞절(테마/펀더멘털 상태) + 뒷절(가격 confirmation). 뒷절이 확인이면 '이고', 아니면 '지만' 으로 잇는다.
        mk_ = axes_.get("market"); fd_ = axes_.get("fundamental")
        if fd_ is not None and fd_.arrow in ("↑", "↑↑"):
            head = f"{seg_word if (seg_word := (str(ind_lbl.get(str(ai_st.segments[0]), ai_st.segments[0])) if ai_st and ai_st.segments else '')) else '세그먼트'} 펀더멘털 확인은 강하"
        elif wr.theme in lead_keys: head = f"{wr.theme} leadership 은 개선되고 있"
        elif wr.theme in lag_keys: head = f"{wr.theme} 테마는 leadership 에서 이탈하고 있"
        elif wr.theme: head = f"{wr.theme} 테마의 변화가 감지됐"
        else: head = ""
        if mk_ is not None:
            price_state = ("시장 대비 강세로 가격 confirmation 이 나타난다" if mk_.arrow in ("↑", "↑↑") else "가격은 상대 약세라 confirmation 이 없다" if mk_.arrow in ("↓", "↓↓") else "가격 confirmation 은 아직 부분적이다")
            confirmed_ = mk_.arrow in ("↑", "↑↑")
        else:
            price_state = _arrow_word(rel, "시장 대비 강세로 가격 confirmation 이 나타난다", "시장 대비 약세라 가격 confirmation 은 없다", "가격은 아직 반응이 작다")
            if rel is not None and 0.3 <= abs(rel) < 0.8: price_state = "가격 confirmation 은 아직 부분적이다"
            confirmed_ = rel is not None and rel >= 0.8
        parts = []
        if head and price_state: parts.append(head + ("고 " if confirmed_ else "지만 ") + price_state)
        elif head: parts.append(head + "다")
        elif price_state: parts.append(price_state)
        tail_bits = []
        if wr.macro_driver: tail_bits.append(f"{wr.macro_driver} 노출이 커 매크로 방향에 민감하다")
        if "NEW_EVENT" in wr.badges: tail_bits.append("종목 지목 뉴스가 있어 재료 확인이 필요하다")
        if wr.alt_signal: tail_bits.append(f"대체데이터({wr.alt_signal})가 먼저 움직이고 있다")
        why = (" ".join(parts).rstrip(".") + ".") if parts else ""
        if tail_bits: why = (why + " " + tail_bits[0] + ".").strip()
        # KEY DRIVER ≤3 · TRIGGER
        drv_ids = [str(x) for x in (h.get("drivers") or (list(meta.drivers) if meta is not None else []))][:3]
        key_drivers = [str(dl.get(x, x)) for x in drv_ids]
        trigger = str(h.get("trigger") or (f"{key_drivers[0]} 방향 전환 시 재평가" if key_drivers else "상대강도 방향 전환 시 재평가"))
        reasons = []
        if "NEW_EVENT" in wr.badges: reasons.append("NEWS")
        if theme_lead: reasons.append("THEME")
        if wr.macro_driver: reasons.append("MACRO")
        if wr.eps_revision_1m is not None or "EPS_REVISION" in wr.badges: reasons.append("FUNDAMENTAL")
        if "fundamental" in axes_ and "market" in axes_ and axes_["fundamental"].arrow in ("↑", "↑↑") and axes_["market"].arrow in ("↓", "↓↓", "→"): reasons.append("DIVERGENCE")
        if wr.alt_signal: reasons.append("ALT DATA")
        if wr.stock_id in chain_of_stock: reasons.append("TRANSMISSION")
        seg_lbl = ""
        if ai_st and ai_st.segments: seg_lbl = str(ind_lbl.get(str(ai_st.segments[0]), ai_st.segments[0]))
        elif meta is not None: seg_lbl = str(ind_lbl.get(str(meta.industry), meta.industry))
        theme_txt = " / ".join(x for x in [seg_lbl, wr.theme] if x)
        cand_w.append((score, WatchRow(id=wr.stock_id, name=wr.name, change_1d=_r(wr.change_1d), watch=wr.macro_driver or wr.theme or "", indicators=inds, theme=theme_txt, why=why or "의미 있는 변화가 감지된 종목 — 아래 driver 를 확인",
                                       key_drivers=key_drivers, trigger=trigger, reasons=reasons[:3], priority="HIGH" if score >= float(wc.get("priority_high", 2.4)) else "MEDIUM",
                                       transmission=chain_of_stock.get(wr.stock_id, [])[:2], issues=issue_of_stock_w.get(wr.stock_id, [])[:2], commentary=(wr.commentary_excerpt or "")[:160], eps_revision=wr.eps_revision_1m)))
    cand_w.sort(key=lambda x: -x[0])
    wl = [w for _sc, w in cand_w[: int(wc.get("max", cfg.get("watchlist_max", 5)))]]

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
    return Cockpit(as_of=snapshot.as_of, market_now=now, history=regime_history, tone=market_tone, drivers=drivers, cross_asset=ca, leadership=leadership, transmission=chains, radar=radar, catalysts=items,
                   earnings=earnings, what_matters_next=nxt, upcoming=upcoming, watchlist=wl, data_status=status, note=note)
