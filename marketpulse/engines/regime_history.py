"""
MARKET REGIME HISTORY · 1M — 실시간 2 탭의 히스토리 층 (2026-09-29).

"최근 한 달 동안 시장의 색이 어떻게 변해 왔는가" 에 답한다. 새 판정을 만들지 않는다 —
state_history 재생(같은 엔진)의 날짜별 raw 판정 위에 두 가지를 얹는다.

1. 거래일 스냅샷: 장중 관측(저장소·메모리 스냅샷)이 있으면 그날 가장 오래 유지된 regime(dominant) 과
   마지막 regime(end) 을 구분하고 dwell(유지 비중) 을 남긴다. 관측이 하나뿐이면 dwell 은 None — 0 이나 100 으로 채우지 않는다.
2. Display Regime: 하루짜리 flip 이 띠의 뜻을 지우지 않게 config 의 규칙(연속 일수 · 강한 증거 · dwell)으로 안정화한다.
   Raw State 는 같은 줄에 그대로 남는다(days[].raw_state).

확률 표현 없음. 3M/6M 은 데이터가 쌓여야 켜진다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping, Sequence

from ..models.cockpit import DriverHeat, HistoryRange, Horizon, RegimeBlock, RegimeDay, RegimeHistory, RegimeShare, RegimeTransition

ARROW_TXT = {"↑↑": "↑↑", "↑": "↑", "↓": "↓", "↓↓": "↓↓", "→": "→", "?": "?"}


@dataclass(frozen=True)
class StateObservation:
    """장중 한 틱의 판정 — 저장소나 메모리 히스토리의 스냅샷에서 뽑는다."""

    as_of: datetime
    label: str
    confidence: float


def _arrow(z: float | None, hi: float, lo: float) -> str:
    if z is None:
        return "?"
    return "↑↑" if z >= hi else "↑" if z >= lo else "↓↓" if z <= -hi else "↓" if z <= -lo else "→"


def _tax(cfg: Mapping, label: str) -> tuple[str, str]:
    t = (cfg.get("taxonomy") or {}).get(label)
    if not t:
        return label.lower(), label.replace("_", " ").title()
    return str(t["key"]), str(t["label"])


def _driver_phrase(text: str) -> str:
    """'US HY OAS +3.9σ' → 'US HY OAS ↑'. 방향만 남긴다 — 히스토리 카드에 숫자를 늘어놓지 않는다."""
    if not text:
        return ""
    parts = text.rsplit(" ", 1)
    if len(parts) != 2:
        return text
    name, z = parts
    return f"{name} {'↑' if z.startswith('+') else '↓'}"


def _day_from_observations(obs: Sequence[StateObservation], day_end: datetime, cfg: Mapping) -> tuple[str, str, float | None, int, int]:
    """(dominant label, end label, dwell, observations, transitions). 관측 간격을 유지 시간으로 본다; 마지막 관측은 day_end 까지."""
    if not obs:
        return "", "", None, 0, 0
    obs = sorted(obs, key=lambda o: o.as_of)
    if len(obs) == 1:
        return obs[0].label, obs[0].label, None, 1, 0
    dwell: dict[str, float] = {}
    for i, o in enumerate(obs):
        nxt = obs[i + 1].as_of if i + 1 < len(obs) else max(day_end, o.as_of)
        dwell[o.label] = dwell.get(o.label, 0.0) + max(0.0, (nxt - o.as_of).total_seconds())
    total = sum(dwell.values())
    dominant = max(dwell.items(), key=lambda kv: kv[1])[0] if total > 0 else obs[-1].label
    transitions = sum(1 for a, b in zip(obs, obs[1:]) if a.label != b.label)
    return dominant, obs[-1].label, (dwell[dominant] / total if total > 0 else None), len(obs), transitions


def stabilize(keys: Sequence[str], strengths: Sequence[float], dwells: Sequence[float | None], cfg: Mapping) -> list[str]:
    """
    OFFICIAL (confirmed) regime — 인과적(causal) 상태 기계. 날짜 i 의 공식 regime 은 i 까지의 raw 만 본다(미래를 보지 않는다 → 과거 값은 뒤에 날이
    붙어도 바뀌지 않는다). 새 regime K 로 바뀌는 조건(둘 중 하나):
      (a) 오늘까지 연속 min_dwell_days 거래일이 raw K (dwell 이 있으면 min_dwell_share 이상인 날만 센다)
      (b) 오늘 확신 ≥ strong_evidence
    그 외의 날은 직전 공식 regime 이 이어진다(raw 는 '후보 신호' 로만 남는다). 첫날은 raw 그대로.
    """
    d = cfg.get("display") or {}
    min_days = int(d.get("min_dwell_days", 2)); strong = float(d.get("strong_evidence", 80)); min_share = float(d.get("min_dwell_share", 0.5))
    out: list[str] = []
    cur: str | None = None

    def counts(i: int, k: str) -> bool:
        dw = dwells[i]
        return keys[i] == k and (dw is None or dw >= min_share)

    for i, k in enumerate(keys):
        if cur is None:
            cur = k
        elif k != cur:
            run = 0
            j = i
            while j >= 0 and counts(j, k):
                run += 1; j -= 1
            if run >= min_days or (strengths[i] >= strong and counts(i, k)):
                cur = k
        out.append(cur)
    return out


def raw_run(keys: Sequence[str]) -> int:
    """오늘까지 같은 raw 가 이어진 거래일 수 (RAW SIGNAL PERSISTENCE)."""
    if not keys:
        return 0
    n = 1
    for a, b in zip(reversed(keys[:-1]), reversed(keys[1:])):
        if a == b:
            n += 1
        else:
            break
    return n


def build_regime_history(
    history: object,
    cfg: Mapping,
    *,
    observations: Sequence[StateObservation] = (),
    as_of: datetime | None = None,
    stored_days: int | None = None,
    horizon_z: Mapping[str, tuple[float | None, float | None]] | None = None,
) -> RegimeHistory | None:
    """history = MarketStateHistory(재생). 없거나 비면 None — 카드를 숨긴다."""
    points = list(getattr(history, "points", []) or [])
    if not points:
        return None
    hcfg = dict(cfg or {})
    days_n = int(hcfg.get("days", 22))
    points = points[-days_n:]
    hi, lo = [float(x) for x in hcfg.get("heat_arrow", [1.5, 0.5])]
    drivers_cfg = list(hcfg.get("drivers") or [])
    driver_keys = [str(d["key"]) for d in drivers_cfg]

    by_date: dict[date, list[StateObservation]] = {}
    for o in observations:
        by_date.setdefault(o.as_of.date(), []).append(o)

    raw_keys: list[str] = []; strengths: list[float] = []; dwells: list[float | None] = []; rows: list[dict] = []
    for p in points:
        raw_label = p.label.value if hasattr(p.label, "value") else str(p.label)
        end_key, _ = _tax(hcfg, raw_label)
        obs = by_date.get(p.date, [])
        dom_label, end_label, dwell, n_obs, n_tr = _day_from_observations(obs, p.as_of, hcfg)
        if n_obs == 0:
            dom_key, n_obs = end_key, 1
        else:
            dom_key, _ = _tax(hcfg, dom_label)
            if end_label:
                end_key, _ = _tax(hcfg, end_label)
        key_change = ""
        if dom_key != end_key:
            key_change = "Late-session deterioration" if end_key in ("liquidity_stress", "growth", "geopolitical") and dom_key not in ("liquidity_stress", "growth", "geopolitical") else "Late-session shift"
        raw_keys.append(dom_key); strengths.append(float(p.confidence)); dwells.append(dwell)
        drv = list(getattr(p, "drivers", []) or [])
        comp = p.composite if p.composite is not None else p.price_temperature
        rows.append(dict(
            date=p.date.isoformat(), raw_state=raw_label, raw_secondary=(p.secondary_label.value if p.secondary_label is not None and hasattr(p.secondary_label, "value") else (str(p.secondary_label) if p.secondary_label else None)),
            dominant_regime=dom_key, end_regime=end_key, evidence_strength=round(float(p.confidence), 1), dominant_driver=drv[0] if drv else "",
            top_driver_1=drv[0] if drv else "", top_driver_2=drv[1] if len(drv) > 1 else "", top_evidence=drv[: int(hcfg.get("top_evidence", 2))],
            dominant_regime_dwell=None if dwell is None else round(dwell, 2), observations=n_obs, transition_count=n_tr, key_change=key_change,
            data_quality=(f"확보 {p.coverage * 100:.0f}% · " + (f"장중 관측 {n_obs}회" if n_obs > 1 else "재생 1회")), coverage=float(p.coverage), composite=None if comp is None else round(float(comp), 1),
            factors={k: (None if p.factors.get(k) is None else round(float(p.factors[k]), 2)) for k in driver_keys},
            source=str(getattr(p, "source", "RECOMPUTED") or "RECOMPUTED"), calculated_at=(getattr(p, "calculated_at", None).isoformat() if getattr(p, "calculated_at", None) else ""),
            model_version=str(getattr(p, "model_version", "") or ""), logic_version=str(getattr(p, "logic_version", "") or ""), locked=bool(getattr(p, "locked", False)),
        ))
    disp = stabilize(raw_keys, strengths, dwells, hcfg)
    labels = {str(v["key"]): str(v["label"]) for v in (hcfg.get("taxonomy") or {}).values()}
    days: list[RegimeDay] = []
    for i, r in enumerate(rows):
        days.append(RegimeDay(**r, display_regime=disp[i], display_label=labels.get(disp[i], disp[i]), bridged=disp[i] != r["dominant_regime"],
                              is_transition=i > 0 and disp[i] != disp[i - 1]))

    blocks: list[RegimeBlock] = []
    for d in days:
        if blocks and blocks[-1].regime == d.display_regime:
            b = blocks[-1]; blocks[-1] = b.model_copy(update={"end": d.date, "days": b.days + 1})
        else:
            blocks.append(RegimeBlock(regime=d.display_regime, label=d.display_label, start=d.date, end=d.date, days=1))
    if blocks:
        blocks[-1] = blocks[-1].model_copy(update={"current": True})

    # 전환 — display 가 바뀐 날. primary driver = factor 변화가 가장 큰 driver, confirmation = 그날 주도 변수 1~2.
    transitions: list[RegimeTransition] = []
    for i, d in enumerate(days):
        if not d.is_transition:
            continue
        prev = days[i - 1]
        # primary driver: 도착 regime 과 결이 맞는 factor(Neutral 이면 떠난 regime 의 factor) 중 변화가 가장 큰 것. 문턱 아래면 그날 주도 변수.
        rf = hcfg.get("regime_factors") or {}
        pool = [str(x) for x in (rf.get(d.display_regime) or rf.get(prev.display_regime) or [])] or [str(dk["key"]) for dk in drivers_cfg]
        label_of = {str(dk["key"]): str(dk["label"]) for dk in drivers_cfg}
        best: tuple[str, float] | None = None
        for k in pool:
            a, b = prev.factors.get(k), d.factors.get(k)
            if a is None or b is None:
                continue
            if best is None or abs(b - a) > abs(best[1]):
                best = (label_of.get(k, k), b - a)
        if best and abs(best[1]) >= float(hcfg.get("primary_min_change", 0.5)):
            primary = f"{best[0]} {'↑' if best[1] > 0 else '↓'}"
        else:
            primary = _driver_phrase(d.top_driver_1)
        conf = " / ".join(_driver_phrase(x) for x in d.top_evidence if x)
        ev = [f"Raw {prev.raw_state} → {d.raw_state}" + (f" (보조 {d.raw_secondary})" if d.raw_secondary else ""), f"확신 {prev.evidence_strength:.0f}% → {d.evidence_strength:.0f}%"]
        for dk in drivers_cfg:
            k = str(dk["key"]); a, b = prev.factors.get(k), d.factors.get(k)
            if a is not None and b is not None and abs(b - a) >= 0.5:
                ev.append(f"{dk['label']} {a:+.1f} → {b:+.1f}")
        if d.top_driver_1: ev.append(f"주도 변수 {d.top_driver_1}" + (f" · {d.top_driver_2}" if d.top_driver_2 else ""))
        if d.dominant_regime_dwell is not None: ev.append(f"Daily dwell {d.dominant_regime_dwell * 100:.0f}%")
        transitions.append(RegimeTransition(date=d.date, from_regime=prev.display_regime, from_label=prev.display_label, to_regime=d.display_regime, to_label=d.display_label,
                                            primary_driver=primary, confirmation=conf, evidence=ev, evidence_strength=d.evidence_strength))
    total_tr = len(transitions)
    transitions = list(reversed(transitions))[: int(hcfg.get("transitions_max", 3))]

    # share — 기간 중 일수 비중(확률 아님)
    n = len(days); cnt: dict[str, int] = {}
    for d in days:
        cnt[d.display_regime] = cnt.get(d.display_regime, 0) + 1
    share = [RegimeShare(regime=k, label=labels.get(k, k), days=v, share=round(100.0 * v / n, 0)) for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])]

    comp = [d.composite for d in days]
    sd = int(hcfg.get("composite_slope_days", 5))
    valid = [(i, c) for i, c in enumerate(comp) if c is not None]
    slope = None
    if len(valid) >= 2:
        last_i, last_c = valid[-1]
        base = next(((i, c) for i, c in reversed(valid) if i <= last_i - sd), None) or valid[0]
        if base[0] < last_i:
            slope = round(last_c - base[1], 1)
    heat = []
    for dk in drivers_cfg:
        k = str(dk["key"]); vals = [d.factors.get(k) for d in days]; cur_v = next((v for v in reversed(vals) if v is not None), None)
        arrow = _arrow(cur_v, hi, lo)
        mean = dk.get("meaning") or {}
        meaning = str(mean.get("up" if arrow in ("↑", "↑↑") else "down" if arrow in ("↓", "↓↓") else "flat", "")) if cur_v is not None else "데이터 없음"
        hz_cfg = dk.get("horizon") or {}; hzs: list[Horizon] = []; hread = ""
        if hz_cfg and horizon_z and str(hz_cfg.get("id")) in horizon_z:
            z1, z5 = horizon_z[str(hz_cfg["id"])]; sgn = int(hz_cfg.get("sign", 1))
            a1 = None if z1 is None else z1 * sgn; a5 = None if z5 is None else z5 * sgn
            hzs = [Horizon(key="1D", z=None if a1 is None else round(a1, 2), arrow=_arrow(a1, hi, lo)), Horizon(key="5D", z=None if a5 is None else round(a5, 2), arrow=_arrow(a5, hi, lo))]  # type: ignore[arg-type]
            rd = dk.get("read") or {}
            if a1 is not None and a5 is not None and abs(a5) >= lo and (a1 > 0) != (a5 > 0) and abs(a1) >= lo * 0.6:
                hread = str(rd.get("pullback_up" if a5 > 0 else "pullback_down", ""))
            elif a1 is not None and a5 is not None and abs(a1) >= lo and abs(a5) >= lo:
                hread = f"오늘도, 최근 5일도 {mean.get('up' if a5 > 0 else 'down', '')} 방향"
        heat.append(DriverHeat(key=k, label=str(dk["label"]), values=vals, current=cur_v, arrow=arrow, label_ui=str(dk.get("label_ui") or dk["label"]), label_ko=str(dk.get("label_ko") or ""),  # type: ignore[arg-type]
                               meaning=meaning, horizon_label=str(dk.get("horizon_label") or ""), horizons=hzs, horizon_read=hread))

    cur = blocks[-1]; prev_b = blocks[-2] if len(blocks) >= 2 else None
    last = days[-1]
    raw_today = None if last.dominant_regime == last.display_regime else labels.get(last.dominant_regime, last.dominant_regime)
    # ── CANONICAL CURRENT REGIME: 공식 = display(확정) · raw = 오늘 후보 · 전환 상태 ──
    dcfg = hcfg.get("display") or {}; need_days = int(dcfg.get("min_dwell_days", 2))
    rrun = raw_run(raw_keys)
    inv_tax = {str(v["key"]): str(k) for k, v in (hcfg.get("taxonomy") or {}).items() if str(k) != "RISK_OFF"}
    tcfg = hcfg.get("transition") or {}
    if last.is_transition:
        t_status, t_ko = "CHANGED", str(tcfg.get("changed", "")).format(prev=prev_b.label if prev_b else "", cur=cur.label)
    elif last.dominant_regime == last.display_regime:
        t_status, t_ko = "CONFIRMED", str(tcfg.get("confirmed", "")).format(cur=cur.label)
    elif rrun >= need_days - 1:
        t_status, t_ko = "TRANSITION_WATCH", str(tcfg.get("watch", "")).format(raw=labels.get(last.dominant_regime, last.dominant_regime), n=rrun, need=need_days)
    else:
        t_status, t_ko = "UNCONFIRMED_TRANSITION", str(tcfg.get("unconfirmed", "")).format(raw=labels.get(last.dominant_regime, last.dominant_regime), n=rrun, need=need_days)
    ranges = []
    for r in hcfg.get("ranges") or []:
        need = int(r["days"]); key = str(r["key"])
        have = max(n, int(stored_days or 0))
        ok = key == "1M" or have >= need  # 1M 은 재생으로 나온다; 나머지는 저장된 일별 스냅샷이 그만큼 있어야
        ranges.append(HistoryRange(key=key, days=need, available=ok, reason="" if ok else f"일별 스냅샷 {have}/{need}일 — 쌓이면 켜진다"))
    return RegimeHistory(
        range="1M", ranges=ranges, current_regime=cur.regime, current_label=cur.label, duration_days=cur.days,
        previous_regime=prev_b.regime if prev_b else None, previous_label=prev_b.label if prev_b else None, transitions_1m=total_tr,
        share_pct=next((s.share for s in share if s.regime == cur.regime), 0.0), raw_today=raw_today, days=days, blocks=blocks,
        official_state_label=inv_tax.get(cur.regime, last.raw_state), raw_regime=last.dominant_regime, raw_label=labels.get(last.dominant_regime, last.dominant_regime),
        raw_persistence_days=rrun, required_days=need_days, transition_status=t_status, transition_status_ko=t_ko,
        pending_regime=None if last.dominant_regime == last.display_regime else last.dominant_regime,
        pending_label=None if last.dominant_regime == last.display_regime else labels.get(last.dominant_regime, last.dominant_regime), changed_today=bool(last.is_transition),
        composite=comp, composite_current=comp[-1] if comp and comp[-1] is not None else next((c for c in reversed(comp) if c is not None), None),
        composite_slope=slope, composite_slope_days=sd, drivers=heat, share=share, transitions=transitions, total_transitions=total_tr,
        palette=labels,
        history_mode=str(getattr(history, "history_mode", "recomputed") or "recomputed"), footnote=str(getattr(history, "footnote", "") or ""),
        recorded_days=sum(1 for d in days if d.source == "RECORDED"), backfilled_days=sum(1 for d in days if d.source == "BACKFILLED"),
        note=("current_regime 은 대시보드의 유일한 공식(confirmed) regime 이다 — 연속 일수·강한 증거·장중 dwell 규칙(config/cockpit.yaml history.display)을 통과해야 바뀌고, 그 전까지 raw 판정은 후보 신호다. 과거 날짜의 공식 regime 은 그날까지의 raw 만으로 정해져 뒤에 날이 붙어도 바뀌지 않는다. "
              "Raw State 는 days[].raw_state 에 그대로 있다. dominant/end 는 장중 관측이 2회 이상인 날만 갈린다(관측 1회면 dwell None). "
              "비중 % 는 기간 중 일수이지 확률이 아니다. 3M/6M 은 일별 스냅샷이 쌓여야 켜진다."),
    )
