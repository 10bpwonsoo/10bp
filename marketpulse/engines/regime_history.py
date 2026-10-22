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
from datetime import date, datetime, timezone
from typing import Mapping, Sequence

from ..models.cockpit import DriverHeat, HistoryRange, Horizon, RegimeBlock, RegimeDay, RegimeHistory, RegimeIntraday, RegimeLiveSignal, RegimeShare, RegimeState, RegimeTransition

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


def _distinct(idx: Sequence[int], markets: Sequence[str] | None) -> int:
    """연속 구간의 일수 — 같은 미국 장(market_date)은 한 번만 센다(2026-10-22). market_date 를 모르면 행마다 하루."""
    if not markets:
        return len(idx)
    return len({(markets[i] or f"#{i}") for i in idx})


def stabilize(keys: Sequence[str], strengths: Sequence[float], dwells: Sequence[float | None], cfg: Mapping, markets: Sequence[str] | None = None) -> list[str]:
    """
    OFFICIAL (confirmed) regime — 인과적(causal) 상태 기계. 날짜 i 의 공식 regime 은 i 까지의 raw 만 본다(미래를 보지 않는다 → 과거 값은 뒤에 날이
    붙어도 바뀌지 않는다). 새 regime K 로 바뀌는 조건(둘 중 하나):
      (a) 오늘까지 연속 min_dwell_days 거래일이 raw K (dwell 이 있으면 min_dwell_share 이상인 날만 센다) — 같은 미국 장(markets)은 하루로 센다
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
            idx: list[int] = []
            j = i
            while j >= 0 and counts(j, k):
                idx.append(j); j -= 1
            if _distinct(idx, markets) >= min_days or (strengths[i] >= strong and counts(i, k)):
                cur = k
        out.append(cur)
    return out


def raw_run(keys: Sequence[str], markets: Sequence[str] | None = None) -> int:
    """오늘까지 같은 raw 가 이어진 거래일 수 (RAW SIGNAL PERSISTENCE) — 같은 미국 장(markets)은 한 번만 센다."""
    if not keys:
        return 0
    idx = [len(keys) - 1]
    for i in range(len(keys) - 2, -1, -1):
        if keys[i] == keys[-1]:
            idx.append(i)
        else:
            break
    return _distinct(idx, markets)


def regime_state(days: Sequence[RegimeDay], hcfg: Mapping, *, live: RegimeLiveSignal | None = None) -> RegimeState:
    """
    공식 regime 판정 — MARKET NOW 와 MARKET REGIME HISTORY 가 함께 쓰는 하나의 계산 (2026-10-22).
    days = Daily Snapshot 만(장중 LIVE 제외). 연속일수는 서로 다른 미국 장(market_date)만 센다. 장중 LIVE 는 live_signal 로 붙일 뿐 공식 판정·일수에 넣지 않는다.
      CONFIRMED  마지막 Daily Snapshot 에서 공식 regime 이 바뀌었다 (연속 required_days 또는 강한 증거)
      PENDING    마지막 Daily Snapshot 의 raw 가 공식과 다르다 — 후보, transition_days / required_days
      STABLE     raw 가 공식과 같다
    """
    labels = {str(v["key"]): str(v["label"]) for v in (hcfg.get("taxonomy") or {}).values()}
    inv_tax = {str(v["key"]): str(k) for k, v in (hcfg.get("taxonomy") or {}).items() if str(k) != "RISK_OFF"}
    dcfg = hcfg.get("display") or {}; need = int(dcfg.get("min_dwell_days", 2)); strong = float(dcfg.get("strong_evidence", 80))
    tcfg = hcfg.get("state_text") or {}
    last = days[-1]
    markets = [d.market_date for d in days]
    keys = [d.dominant_regime for d in days]
    n = raw_run(keys, markets)
    off = last.display_regime
    # 공식 regime 이 이어진 Daily Snapshot 수 (같은 미국 장은 한 번)
    idx = [len(days) - 1]
    for i in range(len(days) - 2, -1, -1):
        if days[i].display_regime == off:
            idx.append(i)
        else:
            break
    off_days = _distinct(idx, markets)
    prev = next((d.display_regime for d in reversed(days[: len(days) - len(idx)])), None)
    raw = last.dominant_regime
    if last.is_transition:
        by = "persistence" if n >= need else "strong_evidence"
        status = "CONFIRMED"
        text = f"CONFIRMED · {min(n, need)} / {need}" if by == "persistence" else f"CONFIRMED · 강한 증거 {last.evidence_strength:.0f}%"
        ko = str(tcfg.get("confirmed" if by == "persistence" else "confirmed_strong", "")).format(prev=labels.get(prev or "", prev or ""), cur=labels.get(off, off), n=min(n, need), need=need,
                                                                                                    conf=f"{last.evidence_strength:.0f}", strong=f"{strong:.0f}")
    elif raw != off:
        by = ""
        status, text = "PENDING", f"PENDING · {n} / {need}"
        ko = str(tcfg.get("pending", "")).format(raw=labels.get(raw, raw), cur=labels.get(off, off), n=n, need=need)
    else:
        by = ""
        status, text = "STABLE", f"STABLE · {off_days}D"
        ko = str(tcfg.get("stable", "")).format(cur=labels.get(off, off), n=off_days)
    return RegimeState(official_regime=off, official_state=inv_tax.get(off, last.raw_state), official_label=labels.get(off, off), official_days=off_days,
                       previous_regime=prev, previous_label=labels.get(prev, prev) if prev else None,
                       raw_signal=raw, raw_state=last.raw_state if _tax(hcfg, last.raw_state)[0] == raw else inv_tax.get(raw, last.raw_state), raw_label=labels.get(raw, raw),
                       candidate_regime=raw if raw != off else None, candidate_label=labels.get(raw, raw) if raw != off else None,
                       transition_days=n, required_days=need, transition_status=status, transition_text=text, transition_status_ko=ko,  # type: ignore[arg-type]
                       confirmed_by=by, evidence_strength=last.evidence_strength, snapshot_date=last.date, market_date=last.market_date, live_signal=live)


def build_regime_history(
    history: object,
    cfg: Mapping,
    *,
    observations: Sequence[StateObservation] = (),
    as_of: datetime | None = None,
    stored_days: int | None = None,
    horizon_z: Mapping[str, tuple[float | None, float | None]] | None = None,
) -> RegimeHistory | None:
    """
    history = MarketStateHistory. 없거나 비면 None — 카드를 숨긴다.

    history.date_basis='kst_snapshot' 이면 points 는 KST Daily Snapshot 날짜의 daily 값이고 history.intraday 는 장중 LIVE 다.
    공식 판정(state)은 daily 값만으로 정하고, 장중 LIVE 는 state.live_signal(후보 신호)로만 붙인다 — MARKET NOW 도 같은 state 를 쓴다(2026-10-22).
    """
    points = list(getattr(history, "points", []) or [])
    if not points:
        return None
    hcfg = dict(cfg or {})
    days_n = int(hcfg.get("days", 22))
    points = points[-days_n:]
    intr = getattr(history, "intraday", None)
    basis = str(getattr(history, "date_basis", "storage_utc") or "storage_utc")

    by_date: dict[date, list[StateObservation]] = {}
    for o in observations:
        by_date.setdefault(o.as_of.astimezone(timezone.utc).date() if o.as_of.tzinfo else o.as_of.date(), []).append(o)

    rows, raw_keys, strengths, dwells = _rows(points, by_date, hcfg)
    live_row = _rows([intr], by_date, hcfg)[0][0] if intr is not None else None
    out = finish_regime_history(rows, raw_keys, strengths, dwells, hcfg, history_mode=str(getattr(history, "history_mode", "recomputed") or "recomputed"),
                                footnote=str(getattr(history, "footnote", "") or ""), stored_days=stored_days, horizon_z=horizon_z,
                                live=live_signal_of(live_row, out_days_market(rows), hcfg) if live_row is not None else None)
    upd: dict = {"date_basis": basis, "gaps": [g.isoformat() if hasattr(g, "isoformat") else str(g) for g in getattr(history, "gaps", []) or []]}
    if basis == "kst_snapshot":
        from ..history.dates import load_rule
        upd["snapshot_time"] = load_rule().label
    if live_row is not None:
        upd["intraday"] = intraday_summary(out, live_row, hcfg)
    return out.model_copy(update=upd)


def out_days_market(rows: Sequence[Mapping]) -> str:
    return str(rows[-1].get("market_date") or "") if rows else ""


def live_signal_of(row: Mapping, last_market: str, hcfg: Mapping) -> RegimeLiveSignal:
    labels = {str(v["key"]): str(v["label"]) for v in (hcfg.get("taxonomy") or {}).values()}
    key = str(row.get("dominant_regime") or "")
    mk = str(row.get("market_date") or "")
    return RegimeLiveSignal(state=str(row.get("raw_state") or ""), regime=key, label=labels.get(key, key), as_of=str(row.get("data_asof") or ""), market_date=mk,
                            same_market_date=(not mk or not last_market or mk <= last_market), evidence_strength=row.get("evidence_strength"))


def intraday_summary(daily: RegimeHistory, row: Mapping, hcfg: Mapping) -> RegimeIntraday:
    """장중 LIVE 요약 — official_* 는 daily 공식 판정 그대로(장중 값이 공식을 바꾸지 않는다)."""
    labels = {str(v["key"]): str(v["label"]) for v in (hcfg.get("taxonomy") or {}).values()}
    st = daily.state
    return RegimeIntraday(date=str(row["date"]).split(" ")[0], as_of=str(row.get("data_asof") or ""), market_date=str(row.get("market_date") or ""), raw_state=str(row["raw_state"]),
                          raw_regime=str(row["dominant_regime"]), raw_label=labels.get(str(row["dominant_regime"]), str(row["dominant_regime"])), evidence_strength=float(row["evidence_strength"]),
                          official_regime=daily.current_regime, official_label=daily.current_label, transition_status=st.transition_status if st else daily.transition_status,
                          transition_status_ko=st.transition_status_ko if st else daily.transition_status_ko, calculated_at=str(row.get("calculated_at") or ""), source=str(row.get("source") or "LIVE"))


def _rows(points: Sequence, by_date: Mapping[date, list[StateObservation]], hcfg: Mapping) -> tuple[list[dict], list[str], list[float], list[float | None]]:
    """점 → 하루 한 줄(dict). 장중 관측은 저장 키(UTC 날짜)로 붙는다 — 그 행이 모은 관측이다."""
    drivers_cfg = list(hcfg.get("drivers") or [])
    driver_keys = [str(d["key"]) for d in drivers_cfg]
    raw_keys: list[str] = []; strengths: list[float] = []; dwells: list[float | None] = []; rows: list[dict] = []
    for p in points:
        raw_label = p.label.value if hasattr(p.label, "value") else str(p.label)
        end_key, _ = _tax(hcfg, raw_label)
        obs = by_date.get(getattr(p, "storage_date", None) or p.date, [])
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
            market_date=getattr(p, "market_date", None).isoformat() if getattr(p, "market_date", None) else "",
            storage_date=getattr(p, "storage_date", None).isoformat() if getattr(p, "storage_date", None) else "",
            data_asof=p.as_of.isoformat() if getattr(p, "as_of", None) else "", merged=list(getattr(p, "merged", []) or []),
        ))
    return rows, raw_keys, strengths, dwells


def finish_regime_history(rows: Sequence[Mapping], raw_keys: Sequence[str], strengths: Sequence[float], dwells: Sequence[float | None], hcfg: Mapping, *,
                          history_mode: str = "recomputed", footnote: str = "", stored_days: int | None = None,
                          horizon_z: Mapping[str, tuple[float | None, float | None]] | None = None, live: RegimeLiveSignal | None = None) -> RegimeHistory:
    """하루 한 줄들 → 공식(display) regime · 구간 · 전환 · 비중 · heat. 줄 값은 그대로 쓰고 파생값만 이 sequence 에서 만든다."""
    rows = [dict(r) for r in rows]
    hi, lo = [float(x) for x in hcfg.get("heat_arrow", [1.5, 0.5])]
    drivers_cfg = list(hcfg.get("drivers") or [])
    markets = [str(r.get("market_date") or "") for r in rows]
    disp = stabilize(raw_keys, strengths, dwells, hcfg, markets if any(markets) else None)
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
    # ── CANONICAL CURRENT REGIME (2026-10-22): MARKET NOW 와 같은 regime_state — 공식 = Daily Snapshot 의 확정 상태, raw = 후보, 장중 LIVE 는 live_signal ──
    st = regime_state(days, hcfg, live=live)
    ranges = []
    for r in hcfg.get("ranges") or []:
        need = int(r["days"]); key = str(r["key"])
        have = max(n, int(stored_days or 0))
        ok = key == "1M" or have >= need  # 1M 은 재생으로 나온다; 나머지는 저장된 일별 스냅샷이 그만큼 있어야
        ranges.append(HistoryRange(key=key, days=need, available=ok, reason="" if ok else f"일별 스냅샷 {have}/{need}일 — 쌓이면 켜진다"))
    return RegimeHistory(
        range="1M", ranges=ranges, current_regime=cur.regime, current_label=cur.label, duration_days=st.official_days, state=st,
        previous_regime=prev_b.regime if prev_b else None, previous_label=prev_b.label if prev_b else None, transitions_1m=total_tr,
        share_pct=next((s.share for s in share if s.regime == cur.regime), 0.0), raw_today=raw_today, days=days, blocks=blocks,
        official_state_label=st.official_state, raw_regime=st.raw_signal, raw_label=st.raw_label,
        raw_persistence_days=st.transition_days, required_days=st.required_days, transition_status=st.transition_status, transition_status_ko=st.transition_status_ko,
        pending_regime=st.candidate_regime, pending_label=st.candidate_label, changed_today=bool(last.is_transition),
        composite=comp, composite_current=comp[-1] if comp and comp[-1] is not None else next((c for c in reversed(comp) if c is not None), None),
        composite_slope=slope, composite_slope_days=sd, drivers=heat, share=share, transitions=transitions, total_transitions=total_tr,
        palette=labels,
        history_mode=history_mode, footnote=footnote,
        recorded_days=sum(1 for d in days if d.source == "RECORDED"), backfilled_days=sum(1 for d in days if d.source == "BACKFILLED"),
        note=("current_regime 은 대시보드의 유일한 공식(confirmed) regime 이다 — 연속 일수·강한 증거·장중 dwell 규칙(config/cockpit.yaml history.display)을 통과해야 바뀌고, 그 전까지 raw 판정은 후보 신호다. 과거 날짜의 공식 regime 은 그날까지의 raw 만으로 정해져 뒤에 날이 붙어도 바뀌지 않는다. "
              "Raw State 는 days[].raw_state 에 그대로 있다. dominant/end 는 장중 관측이 2회 이상인 날만 갈린다(관측 1회면 dwell None). "
              "비중 % 는 기간 중 일수이지 확률이 아니다. 3M/6M 은 일별 스냅샷이 쌓여야 켜진다."),
    )
