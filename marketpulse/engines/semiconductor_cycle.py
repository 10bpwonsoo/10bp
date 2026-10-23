"""
SEMICONDUCTOR CYCLE (2026-10-23) — 메모리 가격 → Spot Premium → 계약가 → HBM / 공급 → 한국 반도체 수출 → 매출 / EPS → 주가.

결정론적 계산만 한다. 없는 데이터는 None · 'NO DATA' 로 남기고 0 으로 채우지 않는다. 시각 절단(as_of) 이후에 공개된 값은 쓰지 않는다:
  현물·계약가 = 공개 시각(updated_at) ≤ as_of · HBM 앵커 = 앵커 날짜 ≤ as_of · 수출 = 발표 시각(release_at) ≤ as_of · 종목 = 이미 절단된 계열.
확률·매수·매도 표현을 만들지 않는다. 시장 해석 문장(market_read)은 ai/semi_read.py 가 같은 결과로 만든다.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from ..config.settings import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config" / "semiconductor_cycle.yaml"
DATA = PACKAGE_ROOT / "data" / "semiconductor"
REPLAY = PACKAGE_ROOT / "data" / "replay" / "alternative"
NO_DATA = "NO DATA"
ENGINE_VERSION = "0.1.0"


@lru_cache(maxsize=2)
def load_config(path: str | None = None) -> dict:
    return yaml.safe_load(Path(path or CONFIG).read_text(encoding="utf-8")) or {}


# ── 입력 ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Obs:
    t: datetime
    v: float
    meta: Mapping[str, Any]


def _dt(s: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _read(path: Path, value_col: str, as_of: datetime) -> list[Obs]:
    if not path.is_file():
        return []
    out = []
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            t = _dt(r.get("updated_at") or "")
            try:
                v = float(r.get(value_col) or "")
            except ValueError:
                continue
            if t is not None and t <= as_of and math.isfinite(v):
                out.append(Obs(t, v, r))
    return sorted(out, key=lambda o: o.t)


def load_spot(as_of: datetime, data_dir: Path = DATA, cfg: Mapping | None = None) -> dict[str, list[Obs]]:
    cfg = cfg or load_config()
    return {p["id"]: _read(data_dir / "spot" / f"{p['id']}.csv", "close", as_of) for p in cfg.get("products", [])}


def load_contract(as_of: datetime, data_dir: Path = DATA, cfg: Mapping | None = None) -> dict[str, list[Obs]]:
    cfg = cfg or load_config()
    ids = {m["contract"] for m in cfg.get("premium_map", []) if m.get("contract")}
    return {i: _read(data_dir / "contract" / f"{i}.csv", "avg", as_of) for i in sorted(ids)}


def load_hbm(as_of: datetime, replay_dir: Path = REPLAY, cfg: Mapping | None = None) -> dict[str, list[Obs]]:
    cfg = cfg or load_config()
    out: dict[str, list[Obs]] = {}
    for s in (cfg.get("hbm") or {}).get("series", []):
        p = replay_dir / f"{s['id']}.csv"
        rows: list[Obs] = []
        if p.is_file():
            with p.open(encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    try:
                        d = date.fromisoformat(r["date"]); v = float(r["close"])
                    except (KeyError, ValueError):
                        continue
                    t = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
                    if t <= as_of:
                        rows.append(Obs(t, v, r))
        out[s["id"]] = sorted(rows, key=lambda o: o.t)
    return out


def load_exports(as_of: datetime, path: Path = DATA / "exports.json") -> dict:
    if not path.is_file():
        return {"releases": [], "working_days": {}}
    doc = json.loads(path.read_text(encoding="utf-8"))
    rel = [r for r in doc.get("releases", []) if (_dt(r["release_at"]) or as_of) <= as_of]
    return {**doc, "releases": rel}


# ── 공통 계산 ─────────────────────────────────────────────────────
def _pct(a: float, b: float) -> float | None:
    return None if b == 0 else round((a / b - 1.0) * 100.0, 2)


def _state(value: float | None, table: Sequence[Mapping], key: str = "key") -> str | None:
    if value is None:
        return None
    for row in table:
        if value >= float(row["min"]):
            return str(row[key])
    return str(table[-1][key]) if table else None


def window_ref(obs: Sequence[Obs], days: int, tol: int) -> Obs | None:
    """마지막 관측에서 days 전 시점의 기준 관측 — 그 시점 이전의 가장 가까운 관측이 tol 일 안이어야 한다."""
    if len(obs) < 2:
        return None
    now = obs[-1].t; target = now - timedelta(days=days)
    cands = [o for o in obs[:-1] if o.t <= target + timedelta(hours=12)]
    if not cands:
        return None
    ref = cands[-1]
    return ref if (target - ref.t) <= timedelta(days=tol) else None


def changes(obs: Sequence[Obs], cfg: Mapping) -> dict:
    wins = cfg.get("windows") or {}; tols = cfg.get("window_tolerance") or {}
    out: dict[str, Any] = {}
    for k, d in wins.items():
        ref = window_ref(obs, int(d), int(tols.get(k, 3)))
        out[k] = None if ref is None else _pct(obs[-1].v, ref.v)
        out[f"{k}_ref"] = None if ref is None else ref.t.date().isoformat()
    if len(obs) >= 2:
        out["since_first"] = _pct(obs[-1].v, obs[0].v); out["since_first_from"] = obs[0].t.date().isoformat()
        out["since_first_days"] = (obs[-1].t - obs[0].t).days
    else:
        out["since_first"] = None; out["since_first_from"] = None; out["since_first_days"] = 0
    return out


def momentum_score(ch: Mapping, mcfg: Mapping) -> tuple[float | None, str]:
    scale = mcfg.get("scale") or {}; weight = mcfg.get("weight") or {}
    num = den = 0.0
    for k, sc in scale.items():
        v = ch.get(k)
        if v is None:
            continue
        w = float(weight.get(k, 1.0)); num += max(-1.0, min(1.0, v / float(sc))) * w; den += w
    if den > 0:
        return round(100.0 * num / den, 1), "WINDOWS"
    if ch.get("since_first") is not None and (ch.get("since_first_days") or 0) >= 7:
        return round(100.0 * max(-1.0, min(1.0, ch["since_first"] / float(mcfg.get("since_first_scale", 15.0)))), 1), "SINCE_FIRST"
    return None, "NONE"


def zscore_pct(values: Sequence[float], min_obs: int) -> tuple[float | None, float | None]:
    if len(values) < min_obs:
        return None, None
    hist = list(values[:-1]); cur = values[-1]
    mu = sum(hist) / len(hist); sd = (sum((x - mu) ** 2 for x in hist) / max(1, len(hist) - 1)) ** 0.5
    z = None if sd == 0 else round((cur - mu) / sd, 2)
    pct = round(100.0 * sum(1 for x in values if x <= cur) / len(values), 0)
    return z, pct


def _arrow(v: float | None, flat: float = 0.5) -> str:
    return "?" if v is None else "↑" if v > flat else "↓" if v < -flat else "→"


def _tone(score: float | None) -> str:
    return "unknown" if score is None else "good" if score >= 10 else "bad" if score <= -10 else "neutral"


# ── 본체 ──────────────────────────────────────────────────────────
def build_semiconductor_cycle(*, as_of: datetime, series_by_id: Mapping[str, Any] | None = None, events: Sequence[Mapping] = (),
                              session_read: Mapping | None = None, memory_history: Mapping | None = None, client: Any = None,
                              data_dir: Path = DATA, replay_dir: Path = REPLAY, cfg: Mapping | None = None) -> dict:
    cfg = cfg or load_config()
    series_by_id = series_by_id or {}
    spot = load_spot(as_of, data_dir, cfg); contract = load_contract(as_of, data_dir, cfg); hbm_obs = load_hbm(as_of, replay_dir, cfg)
    exports = load_exports(as_of, data_dir / "exports.json")
    pcfg = {p["id"]: p for p in cfg.get("products", [])}

    # 1) 제품 카드 · 모멘텀
    products: list[dict] = []
    for pid, p in pcfg.items():
        obs = spot.get(pid) or []
        ch = changes(obs, cfg) if obs else {}
        score, basis = momentum_score(ch, cfg.get("momentum") or {}) if obs else (None, "NONE")
        products.append({
            "id": pid, "label": p["label"], "spec": p["spec"], "family": p["family"], "tier": p["tier"], "selector": bool(p.get("selector")),
            "available": bool(obs), "current": obs[-1].v if obs else None, "updated_at": obs[-1].t.isoformat() if obs else None,
            "change_1d": ch.get("1D"), "change_1w": ch.get("1W"), "change_1m": ch.get("1M"), "change_3m": ch.get("3M"), "change_1y": ch.get("1Y"),
            "since_first": ch.get("since_first"), "since_first_from": ch.get("since_first_from"), "observations": len(obs),
            "momentum": score, "momentum_basis": basis, "momentum_state": _state(score, (cfg.get("momentum") or {}).get("states") or []),
            "history": [{"t": o.t.isoformat(), "v": round(o.v, 4)} for o in obs],
        })
    by_pid = {p["id"]: p for p in products}

    # 2) Spot Premium
    zmin = int(cfg.get("zscore_min_obs", 20)); dpp = float(cfg.get("premium_direction_pp", 2.0)); stale_days = int(cfg.get("contract_stale_days", 45))
    premiums: list[dict] = []
    for m in cfg.get("premium_map", []):
        sp = spot.get(m["spot"]) or []
        base = {"spot": m["spot"], "spot_label": pcfg.get(m["spot"], {}).get("label", m["spot"]), "contract": m.get("contract"), "contract_label": m.get("contract_label"),
                "comparability": m.get("comparability", "NONE"), "weight": float(m.get("weight", 0.0)), "note": m.get("note", "")}
        if not m.get("contract") or m.get("comparability") == "NONE":
            premiums.append({**base, "available": False, "reason": m.get("note") or "비교 가능한 계약가 없음"}); continue
        co = contract.get(m["contract"]) or []
        units = float(m.get("units", 1))
        series = []
        for o in sp:
            anchor = next((c for c in reversed(co) if c.t <= o.t), None)
            if anchor is None:
                continue
            ceq = anchor.v / units
            series.append({"t": o.t.isoformat(), "spot": round(o.v, 4), "contract": round(ceq, 4), "anchor": anchor.t.date().isoformat(), "premium": round((o.v / ceq - 1.0) * 100.0, 2)})
        if not series:
            premiums.append({**base, "available": False, "reason": "그 시점에 공개된 계약가가 없다"}); continue
        vals = [s["premium"] for s in series]
        pobs = [Obs(_dt(s["t"]) or as_of, s["premium"], {}) for s in series]
        w1 = window_ref(pobs, 7, 3); m1 = window_ref(pobs, 30, 7)
        d1w = None if w1 is None else round(vals[-1] - w1.v, 2); d1m = None if m1 is None else round(vals[-1] - m1.v, 2)
        dsf = round(vals[-1] - vals[0], 2) if len(vals) >= 2 else None
        ref_change = d1w if d1w is not None else d1m if d1m is not None else dsf
        direction = "UNKNOWN" if ref_change is None else "EXPANDING" if ref_change > dpp else "COMPRESSING" if ref_change < -dpp else "STABLE"
        z, pct = zscore_pct(vals, zmin)
        last_anchor = next((c for c in reversed(co) if c.t <= as_of), None)
        age = (as_of - last_anchor.t).days if last_anchor else None
        premiums.append({**base, "available": True, "current": vals[-1], "spot_price": series[-1]["spot"], "contract_equiv": series[-1]["contract"],
                         "spot_date": series[-1]["t"][:10], "contract_anchor": series[-1]["anchor"], "contract_anchor_label": (_dt(series[-1]["anchor"] + "T00:00:00+00:00") or as_of).strftime("%b-%Y"),
                         "contract_age_days": age, "contract_stale": age is not None and age > stale_days,
                         "change_1w_pp": d1w, "change_1m_pp": d1m, "change_since_first_pp": dsf, "direction": direction,
                         "zscore": z, "percentile_1y": pct, "observations": len(vals), "zscore_min_obs": zmin,
                         "state": _state(vals[-1], cfg.get("premium_states") or []), "series": series,
                         "proxy": m.get("comparability") == "LOW"})

    # 3) Breadth
    prem_ok = [p for p in premiums if p.get("available")]
    mom_ok = [p for p in products if p["momentum"] is not None and p["tier"] == "main"]
    in_prem = sum(1 for p in prem_ok if (p.get("current") or 0) >= 10); expanding = sum(1 for p in prem_ok if p.get("direction") == "EXPANDING")
    pos_mom = sum(1 for p in mom_ok if (p["momentum"] or 0) > 0)
    frac = (pos_mom / len(mom_ok)) if len(mom_ok) >= int(cfg.get("breadth_min_products", 2)) else None
    breadth = {"products_in_premium": [in_prem, len(prem_ok)], "expanding_premium": [expanding, len(prem_ok)], "positive_momentum": [pos_mom, len(mom_ok)],
               "state": _state(frac, cfg.get("breadth_states") or []) if frac is not None else NO_DATA,
               "note": "모멘텀은 표준 등급(main) 제품만 센다. 표준 창(1W·1M·3M)이 없으면 첫 관측 이후 변화로 대신한다."}

    # 4) 정규화 비교 (기간 시작 = 100)
    normalized: dict[str, list] = {}
    for key, days in (("1M", 30), ("3M", 91), ("6M", 182)):
        rows = []
        for p in products:
            if p["tier"] != "main" or not p["history"]:
                continue
            start = (_dt(p["history"][-1]["t"]) or as_of) - timedelta(days=days)
            pts = [h for h in p["history"] if (_dt(h["t"]) or as_of) >= start]
            if len(pts) < 2:
                continue
            b = pts[0]["v"]
            rows.append({"id": p["id"], "label": p["label"], "base_date": pts[0]["t"][:10], "points": [{"t": h["t"], "v": round(h["v"] / b * 100.0, 2)} for h in pts],
                         "last": round(pts[-1]["v"] / b * 100.0, 1)})
        normalized[key] = sorted(rows, key=lambda r: -r["last"])

    # 5) 제품 맵
    def pmap(family: Sequence[str]) -> list[dict]:
        out = []
        for p in products:
            if p["family"] not in family:
                continue
            pr = next((x for x in prem_ok if x["spot"] == p["id"]), None)
            out.append({"id": p["id"], "label": p["label"], "tier": p["tier"], "available": p["available"], "spot": p["current"], "change_1w": p["change_1w"], "change_1m": p["change_1m"],
                        "since_first": p["since_first"], "since_first_from": p["since_first_from"], "premium": pr["current"] if pr else None,
                        "premium_proxy": bool(pr and pr.get("proxy")), "zscore": pr["zscore"] if pr else None, "momentum": p["momentum"], "momentum_basis": p["momentum_basis"],
                        "strength": p["momentum_state"] or NO_DATA})
        return out

    # 6) 계약가 추세
    con_rows = []
    for cid, co in contract.items():
        if not co:
            continue
        last = co[-1]; age = (as_of - last.t).days
        con_rows.append({"id": cid, "label": (last.meta.get("item") or cid), "avg": last.v, "period": last.t.date().isoformat(), "change_pct": float(last.meta.get("avg_change_pct") or 0.0),
                         "age_days": age, "stale": age > stale_days})
    con_changes = [r["change_pct"] for r in con_rows]
    con_trend = None if not con_changes else sum(con_changes) / len(con_changes)
    con_state = NO_DATA if con_trend is None else ("RISING" if con_trend > 1 else "FALLING" if con_trend < -1 else "FLAT")
    con_stale = bool(con_rows) and all(r["stale"] for r in con_rows)

    # 7) HBM
    hcfg = cfg.get("hbm") or {}; firm = float(hcfg.get("firm_pct", 5.0))
    hbm_rows = []
    for s in hcfg.get("series", []):
        ob = hbm_obs.get(s["id"]) or []
        if not ob:
            hbm_rows.append({"id": s["id"], "label": s["label"], "available": False}); continue
        prev = ob[-2] if len(ob) >= 2 else None
        hbm_rows.append({"id": s["id"], "label": s["label"], "available": True, "value": ob[-1].v, "date": ob[-1].t.date().isoformat(), "period": ob[-1].meta.get("period", ""),
                         "confidence": ob[-1].meta.get("confidence", ""), "source": ob[-1].meta.get("source", ""), "prev": prev.v if prev else None,
                         "prev_date": prev.t.date().isoformat() if prev else None, "change_pct": _pct(ob[-1].v, prev.v) if prev else None})
    hchg = [r["change_pct"] for r in hbm_rows if r.get("change_pct") is not None]
    hbm_pricing = NO_DATA if not hchg else ("FIRM" if min(hchg) >= firm else "MIXED" if max(hchg) >= firm else "SOFT")
    news = classify_news(events, cfg)
    hbm_news = [n for n in news if "HBM" in n["categories"]]
    cap_news = [n for n in news if "CAPACITY" in n["categories"] and "HBM" in n["categories"]]
    commentary = NO_DATA if not hbm_news else ("POSITIVE" if sum(n["sentiment"] for n in hbm_news) > 0 else "NEGATIVE" if sum(n["sentiment"] for n in hbm_news) < 0 else "MIXED")
    ddr5_prem = next((x for x in prem_ok if x["spot"] == "DDR5_16G_SPOT"), None)
    dram_prem_high = [x for x in prem_ok if x["spot"] in ("DDR4_16G_SPOT", "DDR4_8G_SPOT")]
    commodity_tight = None if not prem_ok else any((x.get("current") or 0) >= 10 for x in prem_ok)
    hbm = {"pricing": hbm_pricing, "capacity": "TIGHT (보도)" if cap_news else NO_DATA, "lead_time": NO_DATA, "supplier_commentary": commentary, "anchors": hbm_rows,
           "transmission": [
               {"stage": "AI Demand", "status": "PARTIAL" if any("SERVER" in n["categories"] and n["sentiment"] > 0 for n in news) else "NO DATA", "evidence": "서버·AI 뉴스 감성"},
               {"stage": "Hyperscaler Capex", "status": "NO DATA", "evidence": "capex 공급원 없음(P2)"},
               {"stage": "GPU Demand", "status": "NO DATA", "evidence": "GPU 출하 공급원 없음"},
               {"stage": "HBM Demand", "status": "CONFIRMED" if hbm_pricing == "FIRM" else "PARTIAL" if hbm_pricing == "MIXED" else "NO DATA", "evidence": "HBM 계약가 앵커 상승" if hchg else "앵커 없음"},
               {"stage": "Memory Capacity Allocation", "status": "PARTIAL" if cap_news else "NO DATA", "evidence": f"HBM 증설 보도 {len(cap_news)}건" if cap_news else "보도 없음"},
               {"stage": "Commodity DRAM Supply", "status": "PARTIAL" if commodity_tight else "NOT CONFIRMED" if commodity_tight is False else "NO DATA",
                "evidence": "범용 DRAM 현물이 계약가보다 높다(타이트)" if commodity_tight else "프리미엄 없음" if commodity_tight is False else "비교 불가"},
               {"stage": "DDR5 / DDR4 Pricing", "status": _status_from_score(_avg([by_pid[i]["momentum"] for i in ("DDR5_16G_SPOT", "DDR4_16G_SPOT", "DDR4_8G_SPOT") if i in by_pid])),
                "evidence": "현물 모멘텀"},
           ],
           "note": "HBM 은 Spot Premium 을 만들지 않는다 — 공개 현물이 없다. 계약가 앵커(비정기·추정)와 보도만 쓴다."}

    # 8) 수출 나우캐스트
    export = export_nowcast(exports, as_of, cfg, memory_state=_avg([p["momentum"] for p in mom_ok]))

    # 9) 종목 · 지수
    equity = equity_confirmation(series_by_id, cfg, memory_score=_avg([p["momentum"] for p in mom_ok]))

    # 10) 국면 증거
    mem_score = _avg([p["momentum"] for p in mom_ok])
    prem_score = _wavg([(_clip((x["current"] or 0) / 50.0 * 100.0), x["weight"]) for x in prem_ok])
    if prem_ok and any(x["direction"] in ("EXPANDING", "COMPRESSING") for x in prem_ok):
        adj = sum(x["weight"] * (15 if x["direction"] == "EXPANDING" else -15 if x["direction"] == "COMPRESSING" else 0) for x in prem_ok) / max(1e-9, sum(x["weight"] for x in prem_ok))
        prem_score = _clip((prem_score or 0) + adj)
    contract_score = None if con_trend is None else _clip(con_trend / 5.0 * 100.0) * (0.5 if con_stale else 1.0)
    breadth_score = None if frac is None else round((frac - 0.5) * 200.0, 1)
    hbm_score = None if not hchg else _clip(_avg(hchg) / 20.0 * 100.0)
    export_score = export.get("score")
    equity_score = equity.get("score")
    supply_news = [n for n in news if set(n["categories"]) & {"SUPPLY_CUT", "INVENTORY", "PRICING", "CAPACITY"}]
    supply_score = None if not supply_news else _clip(sum(n["sentiment"] for n in supply_news) / len(supply_news) * 2)
    comps = {"memory_pricing": mem_score, "spot_premium": prem_score, "contract": contract_score, "premium_breadth": breadth_score, "hbm": hbm_score,
             "export": export_score, "eps_revision": None, "equity": equity_score, "supply_news": supply_score}
    weights = (cfg.get("regime") or {}).get("weights") or {}
    composite = _wavg([(v, float(weights.get(k, 1.0))) for k, v in comps.items() if v is not None])
    avail_w = sum(float(weights.get(k, 1.0)) for k, v in comps.items() if v is not None); total_w = sum(float(w) for w in weights.values()) or 1.0
    coverage = avail_w / total_w
    # 신뢰도: 증거 확보 비율 × 일관성(증거 부호 일치) × 이력 깊이(현물 관측 수)
    signs = [1 if v > 5 else -1 if v < -5 else 0 for v in comps.values() if v is not None]
    agree = (abs(sum(signs)) / len(signs)) if signs else 0.0
    depth = min(1.0, max((p["observations"] for p in products), default=0) / 20.0)
    confidence = round(100.0 * coverage * (0.5 + 0.5 * agree) * (0.6 + 0.4 * depth), 0) if composite is not None else 0
    rcfg = cfg.get("regime") or {}
    has_core = any(comps.get(k) is not None for k in rcfg.get("core") or [])
    if composite is not None and (coverage < float(rcfg.get("min_coverage", 0.0)) or not has_core):
        rstate, rlabel = "INSUFFICIENT_DATA", "INSUFFICIENT DATA"
        confidence = 0
    else:
        rstate = _state(composite, rcfg.get("states") or [])
        rlabel = next((s["label"] for s in rcfg.get("states") or [] if s["key"] == rstate), rstate or NO_DATA)
    prem_dir = "UNKNOWN" if not prem_ok else max(("EXPANDING", "STABLE", "COMPRESSING", "UNKNOWN"), key=lambda d: sum(x["weight"] for x in prem_ok if x["direction"] == d))
    regime = {"state": rstate or NO_DATA, "label": rlabel, "composite": composite, "confidence": confidence, "coverage": round(coverage, 2),
              "components": [{"key": k, "label": COMP_LABEL[k], "score": v, "weight": float(weights.get(k, 1.0)), "tone": _tone(v)} for k, v in comps.items()],
              "chips": [
                  {"key": "memory_pricing", "label": "Memory Pricing", "value": _state(mem_score, (cfg.get("momentum") or {}).get("states") or []) or NO_DATA},
                  {"key": "spot_premium", "label": "Spot Premium", "value": prem_dir if prem_ok else NO_DATA},
                  {"key": "contract", "label": "Contract", "value": con_state + (" · STALE" if con_stale else "")},
                  {"key": "hbm", "label": "HBM", "value": "TIGHT" if hbm_pricing == "FIRM" else hbm_pricing},
                  {"key": "export", "label": "Export Nowcast", "value": export.get("momentum") or NO_DATA},
                  {"key": "eps", "label": "EPS Revision", "value": NO_DATA},
                  {"key": "equity", "label": "Equity Confirm", "value": equity.get("status") or NO_DATA},
              ],
              "has_core": has_core, "min_coverage": float(rcfg.get("min_coverage", 0.0)),
              "note": "증거 점수(−100~+100)의 가중 평균. 없는 증거는 분모에서 뺀다 — 신뢰도는 확보 비율·증거 방향의 일치·현물 이력 깊이로 낮아진다. 확보 비율이 기준 미만이거나 메모리 가격 증거가 없으면 국면을 정하지 않는다. 점수는 증거의 크기다."}

    # 11) 전파 경로
    spot_status = _status_from_score(mem_score)
    prem_status = "CONFIRMED" if prem_ok and any((x["current"] or 0) >= 10 and x["comparability"] == "HIGH" for x in prem_ok) else "PARTIAL" if prem_ok else "NO DATA"
    inv_news = [n for n in news if "INVENTORY" in n["categories"]]
    contract_status = "NO DATA" if con_trend is None else ("PARTIAL" if con_stale and con_trend > 1 else "CONFIRMED" if con_trend > 1 else "NOT CONFIRMED")
    spot_to_contract = {"stages": [
        {"stage": "Spot Price", "status": spot_status, "evidence": _mom_evidence(mom_ok)},
        {"stage": "Spot Premium", "status": prem_status, "evidence": "; ".join(f"{x['spot_label']} {x['current']:+.0f}%{' (proxy)' if x.get('proxy') else ''}" for x in prem_ok) or "비교 가능한 계약가 없음"},
        {"stage": "Channel Inventory", "status": "WATCH" if inv_news else "NO DATA", "evidence": f"재고 보도 {len(inv_news)}건" if inv_news else "재고 데이터 없음"},
        {"stage": "Contract Negotiation", "status": "WATCH" if any("PRICING" in n["categories"] for n in news) else "NO DATA", "evidence": "가격 협상 보도" if any("PRICING" in n["categories"] for n in news) else "보도 없음"},
        {"stage": "Contract Price", "status": contract_status, "evidence": (f"평균 {con_trend:+.1f}% · 기준 {con_rows[0]['period'][:7]}" + (" · 오래됨" if con_stale else "")) if con_rows else "계약가 없음"},
        {"stage": "Memory ASP", "status": "NO DATA", "evidence": "기업 ASP 공급원 없음"},
        {"stage": "Revenue", "status": "PARTIAL" if export.get("momentum") in ("ACCELERATING", "STEADY") else "WATCH" if export.get("available") else "NO DATA", "evidence": "수출(달러) 증가를 매출 대리로" if export.get("available") else "없음"},
        {"stage": "EPS Revision", "status": "NO DATA", "evidence": "컨센서스 공급원 없음"},
    ]}
    price_to_export = {"stages": [
        {"stage": "Memory Spot", "status": spot_status, "evidence": _mom_evidence(mom_ok)},
        {"stage": "Contract Price", "status": contract_status, "evidence": spot_to_contract["stages"][4]["evidence"]},
        {"stage": "Memory ASP", "status": "NO DATA", "evidence": "기업 ASP 공급원 없음"},
        {"stage": "Export Unit Value", "status": "NO DATA", "evidence": "품목 단가 통계 공급원 없음"},
        {"stage": "Semiconductor Export", "status": "CONFIRMED" if (export.get("latest_yoy") or 0) > 10 else "NOT CONFIRMED" if export.get("available") else "NO DATA",
         "evidence": f"{export.get('latest_scope_label', '')} {export.get('latest_yoy'):+.0f}% YoY" if export.get("latest_yoy") is not None else "발표 없음"},
        {"stage": "Revenue", "status": "WATCH" if export.get("available") else "NO DATA", "evidence": "기업 실적 발표 전"},
        {"stage": "EPS", "status": "NO DATA", "evidence": "컨센서스 공급원 없음"},
    ]}

    # 12) 펀더멘털 확인 — 기업 데이터는 공급원이 없다. 계약가 추세만 ASP proxy 로
    fundamental = {"rows": [
        {"key": "dram_asp", "label": "DRAM ASP", "value": _arrow(con_trend, 1.0) if con_trend is not None else "?", "basis": f"PROXY — DRAM 계약가 {con_trend:+.1f}% ({con_rows[0]['period'][:7]})" if con_trend is not None else NO_DATA},
        {"key": "nand_asp", "label": "NAND ASP", "value": "?", "basis": "NO DATA — TLC 계약가 공급원 없음"},
        {"key": "inventory", "label": "Inventory Days", "value": "?", "basis": "NO DATA"},
        {"key": "utilization", "label": "Utilization", "value": "?", "basis": "NO DATA"},
        {"key": "eps", "label": "EPS Revision", "value": "?", "basis": "NO DATA — 컨센서스 공급원 없음"},
        {"key": "capex", "label": "Capex", "value": "?", "basis": "NO DATA"},
    ], "companies": [{"id": s["id"], "label": s["label"], "status": NO_DATA, "note": "실적·가이던스 데이터 공급원 없음 — 실적 발표 뒤 수기 입력(P2)"} for s in cfg.get("stocks", [])],
        "state": "PARTIAL (PROXY)" if con_trend is not None else NO_DATA}

    # 13) 종목 영향
    stock_impact = []
    for s in cfg.get("stocks", []):
        eq = next((e for e in equity.get("stocks", []) if e["id"] == s["id"]), None)
        pc = eq.get("confirmation") if eq else NO_DATA
        good = sum(1 for x in (mem_score, hbm_score, export_score) if x is not None and x > 10)
        overall = NO_DATA if mem_score is None and export_score is None else ("POSITIVE" if good >= 2 and pc != "DIVERGENCE" else "MIXED" if good >= 1 else "NEGATIVE")
        stock_impact.append({"id": s["id"], "label": s["label"], "memory_pricing": s["memory"], "hbm": s["hbm"], "export": s["export"], "eps_revision": NO_DATA,
                             "price_confirmation": pc, "overall": overall, "return_1m": eq.get("ret_1m") if eq else None})

    # 14) 다음에 볼 것 (≤5)
    wmn = what_matters_next(premiums=prem_ok, contract=con_rows, export=export, equity=equity, by_pid=by_pid)

    # 15) 데이터 품질
    dq = data_quality(cfg, products, con_rows, hbm_rows, export, equity, as_of)

    out = {"as_of": as_of.isoformat(), "version": cfg.get("version", ""), "regime": regime, "memory_prices": products, "spot_premium": premiums,
           "momentum": {"products": [{k: p[k] for k in ("id", "label", "family", "tier", "momentum", "momentum_basis", "momentum_state", "change_1w", "change_1m", "change_3m", "since_first", "since_first_from")} for p in products]},
           "breadth": breadth, "normalized": normalized, "dram_map": pmap(["DDR5", "DDR4"]), "nand_map": pmap(["NAND"]),
           "contract": {"rows": con_rows, "trend": con_state, "stale": con_stale},
           "memory_history": memory_history, "spot_to_contract": spot_to_contract, "hbm_supply": hbm, "export_nowcast": export, "price_to_export": price_to_export,
           "fundamental_confirmation": fundamental, "equity_confirmation": equity, "stock_impact": stock_impact, "news": news[: int((cfg.get("news") or {}).get("max_items", 8))],
           "what_matters_next": wmn, "data_quality": dq, "not_supported": list(cfg.get("not_supported") or [])}
    from ..ai.semi_read import attach_read
    attach_read(out, session_read, client=client)
    return out


COMP_LABEL = {"memory_pricing": "Memory Pricing", "spot_premium": "Spot Premium", "contract": "Contract Price", "premium_breadth": "Breadth", "hbm": "HBM",
              "export": "Export Nowcast", "eps_revision": "EPS Revision", "equity": "Equity", "supply_news": "Supply / Inventory News"}


def _avg(xs: Sequence[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return round(sum(v) / len(v), 1) if v else None


def _wavg(pairs: Sequence[tuple[float | None, float]]) -> float | None:
    p = [(v, w) for v, w in pairs if v is not None and w > 0]
    return round(sum(v * w for v, w in p) / sum(w for _, w in p), 1) if p else None


def _clip(v: float | None) -> float | None:
    return None if v is None else round(max(-100.0, min(100.0, v)), 1)


def _status_from_score(score: float | None) -> str:
    return "NO DATA" if score is None else "CONFIRMED" if score >= 25 else "PARTIAL" if score >= 5 else "WATCH" if score > -10 else "NOT CONFIRMED"


def _mom_evidence(mom: Sequence[Mapping]) -> str:
    if not mom:
        return "현물 이력 없음"
    parts = []
    for p in mom:
        if p.get("change_1m") is not None:
            parts.append(f"{p['label']} 1M {p['change_1m']:+.1f}%")
        elif p.get("since_first") is not None:
            parts.append(f"{p['label']} {p['since_first']:+.1f}% (since {str(p['since_first_from'])[5:]})")
    return " · ".join(parts[:3]) or "변화율 계산 불가"


# ── 뉴스 ──────────────────────────────────────────────────────────
def classify_news(events: Sequence[Mapping], cfg: Mapping) -> list[dict]:
    cats = (cfg.get("news") or {}).get("categories") or {}
    out = []
    for e in events:
        text = " ".join(str(e.get(k) or "") for k in ("event", "title", "reason"))
        hit = [c for c, spec in cats.items() if any(k.lower() in text.lower() for k in spec.get("kw") or [])]
        themes = set(e.get("themes") or [])
        fb = (cfg.get("news") or {}).get("fallback_category")
        if not hit and "semiconductor" in themes and fb in cats:
            hit = [fb]
        if not hit:
            continue
        sent = int(e.get("sentiment") or 0)
        spec = cats[hit[0]]
        out.append({"id": e.get("id"), "headline": e.get("event") or e.get("title"), "published_at": e.get("timestamp") or e.get("published_at"), "categories": hit,
                    "category": hit[0], "direction": "↑" if sent > 5 else "↓" if sent < -5 else "→", "sentiment": sent, "importance": int(e.get("impact_score") or 0),
                    "why": spec.get("why", ""), "transmission": spec.get("transmission", ""), "products": spec.get("products", []), "stocks": spec.get("stocks", []),
                    "source": e.get("source", ""), "url": e.get("url", "")})
    # 업황 분류(키워드)가 먼저, 그 안에서 중요도 · 최신 순
    fb = (cfg.get("news") or {}).get("fallback_category")
    return sorted(out, key=lambda n: (n["category"] == fb, -n["importance"], -(_dt(str(n["published_at"])) or datetime.min.replace(tzinfo=timezone.utc)).timestamp()))


# ── 수출 나우캐스트 ───────────────────────────────────────────────
def _scope_days(rel: Mapping) -> float:
    return float(rel.get("days") or 0)


def export_nowcast(exports: Mapping, as_of: datetime, cfg: Mapping, *, memory_state: float | None) -> dict:
    rels = list(exports.get("releases") or [])
    if not rels:
        return {"available": False, "note": "발표된 반도체 수출 자료가 없다"}
    cur_month = max(r["period"] for r in rels if r["scope"] in ("1-10", "1-20")) if any(r["scope"] in ("1-10", "1-20") for r in rels) else None
    by = {(r["period"], r["scope"]): r for r in rels}
    latest_full = max((r for r in rels if r["scope"] == "full"), key=lambda r: r["period"], default=None)
    ncfg = cfg.get("export_nowcast") or {}
    out: dict[str, Any] = {"available": True, "unit": "억 달러", "releases": rels}
    if cur_month is None or (cur_month, "full") in by:
        r = latest_full
        out.update({"month": r["period"], "latest_scope": "full", "latest_scope_label": f"{r['period']} 확정", "latest_yoy": r["semis_yoy"], "momentum": "N/A",
                    "nowcast": None, "confidence": 100, "confidence_label": "HIGH", "progress": [], "note": "이번 달 부분 자료가 아직 없다 — 지난달 확정치만"})
        out["score"] = _clip(r["semis_yoy"] / 2.0)
        return out
    y, m = int(cur_month[:4]), int(cur_month[5:7])
    prev_year = f"{y - 1}-{m:02d}"
    pm = date(y, m, 1) - timedelta(days=1); prev_month = f"{pm.year}-{pm.month:02d}"
    wd = (exports.get("working_days") or {}).get(cur_month) or {}
    total_days = float(wd.get("days") or 0) or None
    base = by.get((prev_year, "full"))
    # 월말 구간 배수 — ① 작년 같은 달 ② 직전 확정 달
    ratios = []
    for per in (prev_year, prev_month):
        f, p20 = by.get((per, "full")), by.get((per, "1-20"))
        if f and p20 and f["days"] and p20["days"] and f["days"] > p20["days"]:
            pace20 = p20["semis"] / p20["days"]; rest = (f["semis"] - p20["semis"]) / (f["days"] - p20["days"])
            ratios.append({"period": per, "ratio": round(rest / pace20, 3)})
        elif f and per == prev_year and base and prev_year:
            # 작년 같은 달 1~20일이 없으면 올해 1~20일 YoY 로 역산한 작년 1~20일을 쓴다
            cur20 = by.get((cur_month, "1-20"))
            if cur20 and cur20.get("days_prev"):
                p20v = cur20["semis"] / (1 + cur20["semis_yoy"] / 100.0)
                if f["days"] > cur20["days_prev"]:
                    pace20 = p20v / cur20["days_prev"]; rest = (f["semis"] - p20v) / (f["days"] - cur20["days_prev"])
                    ratios.append({"period": per, "ratio": round(rest / pace20, 3), "derived": True})
    rs = [r["ratio"] for r in ratios] or [1.0]
    mid_r, lo_r, hi_r = sum(rs) / len(rs), min(rs), max(rs)

    def project(rel: Mapping) -> dict | None:
        if not total_days:
            return None
        pace = rel["semis"] / rel["days"]
        days_to_20 = max(0.0, (by.get((cur_month, "1-20")) or {}).get("days", rel["days"]) - rel["days"]) if rel["scope"] == "1-10" else 0.0
        if rel["scope"] == "1-10" and (cur_month, "1-20") not in by:
            days_to_20 = max(0.0, 13.0 - rel["days"]) if total_days else 0.0
        rest_days = max(0.0, total_days - rel["days"] - days_to_20)
        vals = {k: rel["semis"] + pace * days_to_20 + pace * rest_days * r for k, r in (("mid", mid_r), ("low", lo_r), ("high", hi_r))}
        res = {k: round(v, 1) for k, v in vals.items()}
        if base:
            for k, v in vals.items():
                res[f"yoy_{k}"] = round((v / base["semis"] - 1) * 100, 1)
            res["daily_avg_yoy_mid"] = round(((vals["mid"] / total_days) / (base["semis"] / base["days"]) - 1) * 100, 1) if base.get("days") else None
        return res

    r20 = by.get((cur_month, "1-20")); r10 = by.get((cur_month, "1-10"))
    latest = r20 or r10
    now = project(latest)
    prev_now = project(r10) if r20 and r10 else None

    def daily_yoy(r):
        return None if not r or not r.get("days_prev") else round(((1 + r["semis_yoy"] / 100.0) * (r["days_prev"] / r["days"]) - 1) * 100, 1)

    progress = []
    for sc, r in (("1-10", r10), ("1-20", r20)):
        progress.append({"scope": sc, "label": "1~10D" if sc == "1-10" else "1~20D", "available": r is not None, "value": r["semis"] if r else None,
                         "yoy": r["semis_yoy"] if r else None, "daily_avg_yoy": daily_yoy(r), "days": r["days"] if r else None, "days_prev": r.get("days_prev") if r else None,
                         "source": r["source"] if r else None, "release_at": r["release_at"] if r else None})
    progress.append({"scope": "nowcast", "label": "Full Month Nowcast", "available": now is not None, "value": now["mid"] if now else None, "yoy": now.get("yoy_mid") if now else None,
                     "daily_avg_yoy": now.get("daily_avg_yoy_mid") if now else None, "days": total_days})
    progress.append({"scope": "actual", "label": "Actual", "available": False, "value": None, "yoy": None, "note": "Pending — 다음 달 1일 산업통상부 발표"})
    prev_full_yoy = by.get((prev_month, "full"), {}).get("semis_yoy")
    mpp = float(ncfg.get("momentum_pp", 10.0))
    nyoy = now.get("yoy_mid") if now else None
    momentum = None if nyoy is None or prev_full_yoy is None else ("ACCELERATING" if nyoy - prev_full_yoy > mpp else "DECELERATING" if nyoy - prev_full_yoy < -mpp else "STEADY")
    pace_drv = None
    if r10 and r20:
        a, b = daily_yoy(r10), daily_yoy(r20)
        pace_drv = None if a is None or b is None else ("POSITIVE" if b > a + 5 else "NEGATIVE" if b < a - 5 else "NEUTRAL")
    conf = int((ncfg.get("confidence") or {}).get("1-20" if r20 else "1-10" if r10 else "none", 0))
    if len(ratios) < 2:
        conf -= 10
    if not wd.get("official", False):
        conf -= 5
    out.update({
        "month": cur_month, "latest_scope": latest["scope"], "latest_scope_label": f"{cur_month[5:]}월 {'1~20일' if latest['scope'] == '1-20' else '1~10일'}",
        "latest_yoy": latest["semis_yoy"], "latest_daily_avg_yoy": daily_yoy(latest), "nowcast": now, "progress": progress,
        "previous": {"basis": "1~10일 자료로 같은 방식", "mid": prev_now["mid"], "yoy_mid": prev_now.get("yoy_mid")} if prev_now else None,
        "revision_pp": round(now["yoy_mid"] - prev_now["yoy_mid"], 1) if now and prev_now and now.get("yoy_mid") is not None and prev_now.get("yoy_mid") is not None else None,
        "prev_month": prev_month, "prev_month_yoy": prev_full_yoy, "momentum": momentum or NO_DATA,
        "drivers": [{"key": "memory_price", "label": "Memory Price", "value": "POSITIVE" if (memory_state or 0) > 10 else "NEGATIVE" if (memory_state or 0) < -10 else "NEUTRAL" if memory_state is not None else NO_DATA},
                    {"key": "pace", "label": "Export Pace", "value": pace_drv or NO_DATA, "note": "1~20일 일평균 YoY vs 1~10일"},
                    {"key": "fx", "label": "FX", "value": "NEUTRAL", "note": "달러 기준 통계 — 원화 환율은 금액에 직접 들어가지 않는다"},
                    {"key": "base", "label": "Base Effect", "value": ("LOW BASE" if base and base["semis_yoy"] < 0 else "NEUTRAL") if base else NO_DATA,
                     "note": f"작년 {prev_year[5:]}월 {base['semis']:.1f}억$ ({base['semis_yoy']:+.1f}%)" if base else ""}],
        "price_vs_volume": "PRICE-LED (정성)" if (memory_state or 0) > 10 else "MIXED (정성)" if memory_state is not None else NO_DATA,
        "price_vs_volume_note": "단가·물량 분해 공식 통계가 없다 — 메모리 가격 방향으로만 정성 판단(숫자 분해 안 함)",
        "ratios": ratios, "ratio_mid": round(mid_r, 3), "working_days": total_days, "working_days_basis": wd.get("basis", ""),
        "confidence": max(0, conf), "confidence_label": "HIGH" if conf >= 70 else "MEDIUM" if conf >= 45 else "LOW",
        "accuracy": {"rows": [], "note": "지난 나우캐스트 기록이 없다 — 이번 달부터 확정치와 비교해 쌓는다"},
        "base": base,
        "method": "1~20일(또는 1~10일) 누적 + 남은 조업일 × 1~20일 일평균 페이스 × 월말 배수. 월말 배수 = 작년 같은 달·직전 확정 달의 '21일~말일 일평균 / 1~20일 일평균' 평균(범위 = 최소~최대). 단순 선형 연장이 아니다.",
    })
    out["score"] = None if nyoy is None else _clip((nyoy / 3.0) + (15 if momentum == "ACCELERATING" else -15 if momentum == "DECELERATING" else 0))
    return out


# ── 주가 확인 ────────────────────────────────────────────────────
def _ret(series: Any, days: int) -> float | None:
    if series is None:
        return None
    ts = list(getattr(series, "timestamps", []) or []); vs = list(getattr(series, "values", []) or [])
    if len(ts) < 2:
        return None
    target = ts[-1] - timedelta(days=days)
    idx = [i for i, t in enumerate(ts) if t <= target]
    if not idx:
        return None
    b = vs[idx[-1]]
    return None if not b else round((vs[-1] / b - 1) * 100, 2)


def equity_confirmation(series_by_id: Mapping[str, Any], cfg: Mapping, *, memory_score: float | None) -> dict:
    flat = float(cfg.get("equity_flat_pct", 2.0))
    rows = []
    for s in cfg.get("stocks", []):
        sr = series_by_id.get(s["id"])
        r1d, r1w, r1m = _ret(sr, 1), _ret(sr, 7), _ret(sr, 30)
        b1m = _ret(series_by_id.get(s.get("bench", "")), 30)
        rel = None if r1m is None or b1m is None else round(r1m - b1m, 2)
        arrow = "?" if r1m is None else "↑" if r1m > flat else "↓" if r1m < -flat else "→"
        conf = NO_DATA if r1m is None or memory_score is None else ("CONFIRMED" if (r1m > flat) == (memory_score > 0) and abs(r1m) > flat else "DIVERGENCE" if abs(r1m) > flat else "NEUTRAL")
        rows.append({"id": s["id"], "label": s["label"], "ret_1d": r1d, "ret_1w": r1w, "ret_1m": r1m, "rel_1m": rel, "bench": s.get("bench"), "arrow": arrow, "confirmation": conf,
                     "last": (getattr(sr, "timestamps", None) or [None])[-1].isoformat() if sr is not None and getattr(sr, "timestamps", None) else None})
    idx = cfg.get("index") or {}
    isr = series_by_id.get(idx.get("id", "")) or series_by_id.get(idx.get("fallback", ""))
    index = {"id": idx.get("id"), "label": idx.get("label"), "ret_1d": _ret(isr, 1), "ret_1w": _ret(isr, 7), "ret_1m": _ret(isr, 30)}
    ok = [r for r in rows if r["confirmation"] != NO_DATA]
    nconf = sum(1 for r in ok if r["confirmation"] == "CONFIRMED"); ndiv = sum(1 for r in ok if r["confirmation"] == "DIVERGENCE")
    status = NO_DATA if not ok else ("BROAD CONFIRMATION" if nconf == len(ok) else "DIVERGENCE" if ndiv > len(ok) / 2 else "PARTIAL CONFIRMATION")
    if memory_score is None:
        read = "메모리 가격 방향을 정할 이력이 부족해 주가와 비교하지 않는다."
    elif status == "DIVERGENCE":
        read = ("가격 사이클은 개선되고 있으나 주가 확인은 약하다 — 기대가 선반영됐거나 다른 매크로 요인이 주가를 누르고 있을 수 있다."
                if memory_score > 0 else "가격 사이클은 약한데 주가는 버티고 있다 — 주가가 회복을 먼저 가정하고 있을 수 있다.")
    elif status == "BROAD CONFIRMATION":
        read = "메모리 가격 방향과 주요 메모리 주가가 같은 방향이다."
    else:
        read = "주가 확인은 종목마다 엇갈린다."
    m1 = [r["ret_1m"] for r in rows if r["ret_1m"] is not None]
    score = None if not m1 else _clip(sum(m1) / len(m1) * 5)
    return {"stocks": rows, "index": index, "status": status, "read": read, "score": score}


# ── 다음에 볼 것 · 데이터 품질 ───────────────────────────────────
def what_matters_next(*, premiums, contract, export, equity, by_pid) -> list[dict]:
    out = []
    d5 = next((p for p in premiums if p["spot"] == "DDR5_16G_SPOT"), None)
    d4 = next((p for p in premiums if p["spot"] == "DDR4_16G_SPOT"), None)
    if d4:
        out.append({"title": "DDR4 16Gb Spot Premium 유지 여부", "current": f"{d4['current']:+.0f}% (계약 {d4['contract_anchor_label']})",
                    "trigger": "프리미엄 10% 아래로 축소", "confirmation": "새 계약가 공개 뒤에도 프리미엄 10% 이상", "implication": "현물 강세가 계약가로 넘어갈 여지"})
    if d5:
        out.append({"title": "DDR5 Spot Premium (proxy)", "current": f"{d5['current']:+.0f}% · {d5['direction']}", "trigger": "현물 1W 하락 전환",
                    "confirmation": "DDR5 칩 계약가 공개 또는 모듈 계약가 상승", "implication": "서버·PC DDR5 가격 전이"})
    if contract:
        out.append({"title": "다음 DRAM 계약가", "current": f"{contract[0]['period'][:7]} 기준 · 공개 {contract[0]['age_days']}일 전", "trigger": "계약가 상승률 둔화(<+2%)",
                    "confirmation": "현물 프리미엄과 같은 방향의 계약가 상승", "implication": "ASP · 매출 전이 확인"})
    if export.get("available"):
        out.append({"title": "월간 반도체 수출 확정치", "current": f"{export.get('latest_scope_label', '')} {export.get('latest_yoy', 0):+.0f}% · 나우캐스트 {((export.get('nowcast') or {}).get('yoy_mid') or 0):+.0f}%",
                    "trigger": "확정치가 나우캐스트 범위 하단 아래", "confirmation": "확정치 YoY 가 직전 달 이상", "implication": "가격 강세의 수출 전이"})
    st = equity.get("stocks") or []
    if st:
        out.append({"title": "메모리주 상대강도", "current": " · ".join(f"{s['label'].split()[0]} 1M {s['ret_1m']:+.0f}%" for s in st if s.get("ret_1m") is not None) or "데이터 없음",
                    "trigger": "가격 개선 속 주가 1M 하락 지속", "confirmation": "SK hynix · Micron 동반 상대 강세", "implication": "주가가 사이클을 확인하는지"})
    return out[:5]


def data_quality(cfg, products, con_rows, hbm_rows, export, equity, as_of) -> list[dict]:
    src = cfg.get("data_quality_sources") or {}
    rows = []
    for p in products:
        if not p["available"]:
            rows.append({"item": p["label"], "tier": src.get("spot", {}).get("tier"), "source": src.get("spot", {}).get("source"), "frequency": "Daily" if p["family"] != "NAND" else "Weekly", "last": None, "status": "UNAVAILABLE", "observations": 0}); continue
        age = (as_of - (_dt(p["updated_at"]) or as_of)).days
        lim = 4 if p["family"] != "NAND" else 9
        rows.append({"item": p["label"], "tier": src.get("spot", {}).get("tier"), "source": src.get("spot", {}).get("source"), "frequency": "Daily" if p["family"] != "NAND" else "Weekly",
                     "last": p["updated_at"], "status": "FRESH" if age <= lim else "STALE", "observations": p["observations"],
                     "note": f"관측 {p['observations']}개 — 1M·3M·z-score 는 이력이 쌓여야 나온다" if p["observations"] < 20 else ""})
    for c in con_rows:
        rows.append({"item": c["label"] + " (계약)", "tier": src.get("contract", {}).get("tier"), "source": src.get("contract", {}).get("source"), "frequency": "Monthly",
                     "last": c["period"], "status": "STALE" if c["stale"] else "FRESH", "observations": 1})
    for h in hbm_rows:
        rows.append({"item": h["label"], "tier": src.get("hbm", {}).get("tier"), "source": h.get("source") or src.get("hbm", {}).get("source"), "frequency": "비정기",
                     "last": h.get("date"), "status": "FRESH" if h.get("available") else "UNAVAILABLE"})
    if export.get("available"):
        last = max(export.get("releases") or [], key=lambda r: r["release_at"], default=None)
        rows.append({"item": "한국 반도체 수출", "tier": src.get("export", {}).get("tier"), "source": src.get("export", {}).get("source"), "frequency": src.get("export", {}).get("frequency"),
                     "last": last["release_at"] if last else None, "status": "FRESH", "accuracy_note": (export.get("accuracy") or {}).get("note")})
    rows.append({"item": "EPS Revision", "tier": "UNAVAILABLE", "source": src.get("eps_revision", {}).get("source"), "frequency": "-", "last": None, "status": "UNAVAILABLE"})
    for s in equity.get("stocks") or []:
        rows.append({"item": s["label"] + " 주가", "tier": src.get("equity", {}).get("tier"), "source": src.get("equity", {}).get("source"), "frequency": "Daily", "last": s.get("last"),
                     "status": "FRESH" if s.get("last") else "UNAVAILABLE"})
    return rows
