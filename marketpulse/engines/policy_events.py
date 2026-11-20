"""
금리 탭 POLICY & MACRO EVENTS 엔진 (2026-10-12).

EVENT → SURPRISE → RATES REACTION 을 한 줄로 잇고, 그 이벤트가 지금 금리 regime 을 지지(SUPPORTED)·도전(CHALLENGED)·중립(NEUTRAL)
중 어느 쪽으로 작용했는지 붙인다.

- 결정·실제치·컨센서스·일정: data/policy_events/*.json — 출처가 확인된 수기 파일. as_of 이하의 가장 최근 파일을 쓴다. 없으면 None.
- 놀람: 실제 − 컨센서스를 config/policy_events.yaml 의 문턱으로 판정한다(HOT/COOL/INLINE/MIXED, STRONG/WEAK).
- 금리 반응: 발표일 미국채 2Y·10Y 일간 종가 − 직전 거래일 종가. 날짜·계열이 없으면 None — 만들지 않는다.
- regime 연결: 놀람이 기대하는 금리 방향이 지금 10Y 방향과 반대면 CHALLENGED, 같고 그 경로의 driver 가 지배 driver 면 SUPPORTED, 나머지 NEUTRAL.
  미국 금리 regime 대상이 아닌 중앙은행(ECB·BOJ·BOK)은 판정하지 않는다(None).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo
from functools import lru_cache
from pathlib import Path
from typing import Mapping

import yaml

from ..config.settings import CONFIG_DIR
from ..models.market import MarketSeries
from ..models.policy_events import (
    EventSource, MacroMeasure, MacroRelease, PolicyDecision, PolicyMacroEvents, RateReaction, RecentItem, RegimeImpact, RegimeLink, UpcomingEvent,
)
from ..models.rates_regime import RatesRegime
from .korean import fix_particles

PKG_DIR = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=4)
def _load(config_dir: Path | None) -> dict:
    return yaml.safe_load(((config_dir or CONFIG_DIR) / "policy_events.yaml").read_text(encoding="utf-8")) or {}


def load_policy_events_config(config_dir: Path | None = None) -> dict:
    return _load(config_dir)


def load_events_file(as_of: date | datetime, *, data_dir: Path | None = None, config_dir: Path | None = None) -> dict | None:
    """
    as_of 이하 날짜의 가장 최근 수기 파일. 없으면 None — 화면은 '확인된 이벤트 없음' 을 그린다.
    파일 이름은 수기 확인한 날의 한국 날짜다. 시각(datetime)을 주면 한국 날짜로 바꿔 고른다 — 한국 오전(= UTC 전날)에 만든 파일을
    UTC 날짜로 찾으면 하루 전 파일을 읽는다(2026-10-15). 파일 안의 발표·일정은 build_policy_events 가 as_of 로 다시 거른다.
    """
    if isinstance(as_of, datetime):
        as_of = as_of.astimezone(ZoneInfo(str(load_policy_events_config(config_dir).get("file_timezone", "Asia/Seoul")))).date() if as_of.tzinfo else as_of.date()
    cfg = load_policy_events_config(config_dir)
    d = data_dir or (PKG_DIR / str(cfg.get("data_dir", "data/policy_events")))
    if not d.exists():
        return None
    cands = sorted(p for p in d.glob("*.json") if p.stem <= as_of.isoformat())
    if not cands:
        return None
    return json.loads(cands[-1].read_text(encoding="utf-8"))


def _d(v: str | None) -> date | None:
    return None if not v else date.fromisoformat(str(v)[:10])


def _arrow(bp: float | None, cfg: Mapping) -> str:
    if bp is None:
        return "–"
    strong, mild = float(cfg.get("strong_bp", 8)), float(cfg.get("mild_bp", 3))
    if abs(bp) >= strong:
        return "↑↑" if bp > 0 else "↓↓"
    if abs(bp) >= mild:
        return "↑" if bp > 0 else "↓"
    return "→"


def rate_reaction(day: date, series: Mapping[str, MarketSeries], cfg: Mapping) -> RateReaction:
    """발표일 종가 − 직전 거래일 종가(bp). 그날 봉이 없으면 None."""
    rc = cfg.get("reaction") or {}
    out: dict[str, float | None] = {}
    for leg, iid in (rc.get("series") or {"us2y": "US2Y", "us10y": "US10Y"}).items():
        s = series.get(iid)
        val = None
        if s is not None and s.values:
            idx = [i for i, t in enumerate(s.timestamps) if t.date() == day]
            if idx and idx[0] > 0:
                i = idx[0]
                val = round((s.values[i] - s.values[i - 1]) * 100.0, 1)
        out[leg] = val
    return RateReaction(date=day, us2y_bp=out.get("us2y"), us10y_bp=out.get("us10y"), us2y_arrow=_arrow(out.get("us2y"), rc), us10y_arrow=_arrow(out.get("us10y"), rc),
                        note=str(rc.get("note", "")))


def fmt_value(v: float | None, unit: str) -> str:
    """% 는 소수 한 자리(3.0%), k 는 정수(29k). 없으면 –."""
    if v is None:
        return "–"
    return f"{v:.0f}k" if unit == "k" else f"{v:.1f}{unit}"


def _surprise(key: str, measures: list[MacroMeasure], cfg: Mapping) -> tuple[str, str, list[MacroMeasure]]:
    spec = (cfg.get("surprise") or {}).get(key)
    if not spec:
        return "N/A", "판정 규칙 없음", measures
    votes: list[int] = []; basis: list[str] = []; out: list[MacroMeasure] = []
    rule = {j["key"]: j for j in spec.get("judge", [])}
    for m in measures:
        j = rule.get(m.key)
        if j is None or m.actual is None or m.consensus is None:
            out.append(m); continue
        diff = round(m.actual - m.consensus, 3)
        step = float(j.get("step", 0.1))
        if abs(diff) >= step - 1e-9:
            v = int(j.get("sign", 1)) * (1 if diff > 0 else -1)
            votes.append(v)
            basis.append(f"{m.label} {fmt_value(m.actual, m.unit)} vs {fmt_value(m.consensus, m.unit)}")
        out.append(m.model_copy(update={"diff": diff, "judged": True}))
    if not any(m.judged for m in out):
        return "N/A", "실제치·컨센서스가 확인되지 않았다", out
    up, down = any(v > 0 for v in votes), any(v < 0 for v in votes)
    label = "MIXED" if up and down else (str(spec["up"]) if up else (str(spec["down"]) if down else "INLINE"))
    return label, (" · ".join(basis) if basis else "모든 항목이 컨센서스와 같다"), out


def _read(surprise: str, exp_dir: int, rx: RateReaction, cfg: Mapping) -> str:
    rd = cfg.get("read") or {}; sko = (cfg.get("surprise_ko") or {}).get(surprise, surprise)
    lead_map = cfg.get("lead_ko") or {}; mild = float((cfg.get("reaction") or {}).get("mild_bp", 3))
    a, b = rx.us2y_bp, rx.us10y_bp
    if a is None and b is None:
        return fix_particles(str(rd.get("missing", "")).format(surprise_ko=sko))
    legs = [v for v in (a, b) if v is not None]
    big = max(legs, key=abs)
    if abs(big) < mild:
        return fix_particles(str(rd.get("muted", "")).format(surprise_ko=sko))
    act = 1 if big > 0 else -1
    if a is not None and b is not None and abs(abs(a) - abs(b)) < mild:
        lead = lead_map.get("both", "금리")
    else:
        lead = lead_map.get("front" if (a is not None and (b is None or abs(a) > abs(b))) else "long", "금리")
    rx_ko = "상승" if act > 0 else "하락"
    key = "neutral" if exp_dir == 0 else ("matched" if act == exp_dir else "opposite")
    return fix_particles(str(rd.get(key, "")).format(surprise_ko=sko, lead_ko=lead, rx_ko=rx_ko))


def _impact(label: str, exp_dir: int, channel_driver: str, regime: RatesRegime, name: str, cfg: Mapping, *, policy: bool = False) -> RegimeImpact:
    ir = cfg.get("impact_reason") or {}
    drivers = {d.id: d for d in regime.drivers}
    dom = drivers.get(regime.dominant)
    primary_ko = dom.label_ko if dom else regime.dominant
    channel_ko = drivers[channel_driver].label_ko if channel_driver in drivers else channel_driver
    rate_dir = {"up": 1, "down": -1}.get(regime.rate_move.direction, 0)
    dir_ko = {"up": "상승", "down": "하락", "flat": "보합"}.get(regime.rate_move.direction, "")
    sko = (cfg.get("surprise_ko") or {}).get(label, label)
    fmt = dict(name=name, primary_ko=primary_ko, channel_ko=channel_ko, surprise_ko=sko, dir_ko=dir_ko)
    if exp_dir == 0:
        return RegimeImpact(impact="NEUTRAL", reason=fix_particles(str(ir.get("NEUTRAL_INLINE", "")).format(**fmt)))
    if rate_dir != 0 and exp_dir != rate_dir:
        return RegimeImpact(impact="CHALLENGED", reason=fix_particles(str(ir.get("CHALLENGED_POLICY" if policy else "CHALLENGED", "")).format(**fmt)))
    if rate_dir != 0 and channel_driver == regime.dominant:
        return RegimeImpact(impact="SUPPORTED", reason=fix_particles(str(ir.get("SUPPORTED", "")).format(**fmt)))
    return RegimeImpact(impact="NEUTRAL", reason=fix_particles(str(ir.get("NEUTRAL", "")).format(**fmt)))


def _rx_text(rx: RateReaction | None) -> str:
    if rx is None or (rx.us2y_bp is None and rx.us10y_bp is None):
        return ""
    return f"2Y {rx.us2y_arrow} · 10Y {rx.us10y_arrow}"


def _bp(v: float | None) -> str:
    return "–" if v is None else f"{v:+.0f}bp"


def build_policy_events(data: Mapping | None, series: Mapping[str, MarketSeries], regime: RatesRegime, *, as_of: datetime,
                        config_dir: Path | None = None) -> PolicyMacroEvents | None:
    if not data:
        return None
    cfg = load_policy_events_config(config_dir)
    today = as_of.date()
    imp = cfg.get("importance") or {}
    ch = cfg.get("channel") or {}
    us_banks = set(cfg.get("us_banks", ["FED"]))
    missing: list[str] = []

    # ── 중앙은행 ─────────────────────────────────────────
    policy: list[PolicyDecision] = []
    for p in data.get("policy", []):
        day = _d(p["date"])
        if day is None or day > today:
            continue
        decision = str(p["decision"]).upper()
        tone = str(p.get("guidance") or "").upper() or str((cfg.get("tone_by_decision") or {}).get(decision, "NEUTRAL"))
        bp = p.get("change_bp")
        dlabel = str((cfg.get("decision_label") or {}).get(decision, decision)) + (f" {'+' if decision == 'HIKE' else '−'}{int(bp)}bp" if bp and decision != "HOLD" else "")
        pc = ch.get("policy") or {}
        path = (pc.get(tone) or {}); exp_dir = int(path.get("dir", 0))
        is_us = p["bank"] in us_banks
        rx = rate_reaction(day, series, cfg) if is_us else None
        chain = [f"{p['name'].split(' / ')[0]} {dlabel}", f"{tone} → {path.get('path', '')}"]
        if rx is not None and (rx.us2y_bp is not None or rx.us10y_bp is not None):
            chain += [f"2Y {_bp(rx.us2y_bp)}", f"10Y {_bp(rx.us10y_bp)}"]
        reg = _impact(tone, exp_dir, str(pc.get("driver", "fed_policy")), regime, p["name"], cfg, policy=True) if is_us else RegimeImpact(impact=None, reason=str((cfg.get("impact_reason") or {}).get("NOT_US", "")))
        if not p.get("vote"):
            missing.append(f"{p['bank']} 표결")
        policy.append(PolicyDecision(bank=p["bank"], name=p["name"], date=day, decision=decision, decision_label=dlabel, previous_rate=str(p.get("previous_rate", "")),  # type: ignore[arg-type]
                                     current_rate=str(p.get("current_rate", "")), rate_label=str(p.get("rate_label", "")), vote=str(p.get("vote", "")), tone=tone,  # type: ignore[arg-type]
                                     tone_basis=str(p.get("guidance_basis", "")), line=str(p.get("line", "")), statement=str(p.get("statement", "")), chair=str(p.get("chair", "")),
                                     projections=str(p.get("projections", "")), market_path=str(p.get("market_path", "")), next_meeting=_d(p.get("next_meeting")),
                                     next_meeting_start=_d(p.get("next_meeting_start")), implication=str(p.get("implication", "")), age_days=(today - day).days,
                                     chain=chain, reaction=rx, regime=reg, sources=[EventSource(**s) for s in p.get("sources", [])]))

    # ── 매크로 발표 ──────────────────────────────────────
    releases: list[MacroRelease] = []
    for r in data.get("releases", []):
        day = _d(r["date"])
        if day is None or day > today:
            continue
        ms = [MacroMeasure(key=m["key"], label=m["label"], unit=str(m.get("unit", "%")), actual=m.get("actual"), consensus=m.get("consensus"), prior=m.get("prior"), note=str(m.get("note", "")))
              for m in r.get("measures", [])]
        for m in ms:
            if m.actual is None:
                missing.append(f"{r['name']} {m.label}")
        label, basis, ms = _surprise(r["key"], ms, cfg)
        cspec = ch.get(r["key"]) or {}
        path = cspec.get(label) or {}; exp_dir = int(path.get("dir", 0))
        rx = rate_reaction(day, series, cfg)
        chain = [f"{r['name'].replace('Nonfarm Payrolls', 'NFP').replace('US ', '')} {label}", path.get("path", "")]
        if rx.us2y_bp is not None or rx.us10y_bp is not None:
            chain += [f"2Y {_bp(rx.us2y_bp)}", f"10Y {_bp(rx.us10y_bp)}"]
        reg = _impact(label, exp_dir, str(cspec.get("driver", "inflation_repricing")), regime, r["name"], cfg)
        releases.append(MacroRelease(key=r["key"], name=r["name"], period=str(r.get("period", "")), date=day, importance=str(imp.get(r["key"], "MED")),  # type: ignore[arg-type]
                                     measures=ms, surprise=label, surprise_basis=basis, consensus_source=str(r.get("consensus_source", "")),  # type: ignore[arg-type]
                                     chain=[c for c in chain if c], reaction=rx, read=_read(label, exp_dir, rx, cfg), regime=reg, age_days=(today - day).days,
                                     note=str(r.get("note", "")), sources=[EventSource(**s) for s in r.get("sources", [])]))
    releases.sort(key=lambda x: x.date, reverse=True)

    # ── RECENT — 최근 창 안의 발표·결정. 영향도(HIGH 먼저) → 최근 순 ─────
    win = int(cfg.get("recent_window_days", 45))
    recent: list[RecentItem] = []
    for x in releases:
        if x.age_days <= win:
            recent.append(RecentItem(kind="release", key=x.key, date=x.date, title=x.name.replace("Nonfarm Payrolls", "NFP").replace("US ", ""), label=x.surprise,
                                     reaction_text=_rx_text(x.reaction), impact=x.regime.impact, importance=x.importance))
    for p in policy:
        if p.age_days <= win:
            recent.append(RecentItem(kind="policy", key=p.bank, date=p.date, title="FOMC" if p.bank == "FED" else p.bank, label=f"{p.tone} {p.decision}",
                                     reaction_text=_rx_text(p.reaction), impact=p.regime.impact, importance=str(imp.get(p.bank, "MED"))))  # type: ignore[arg-type]
    rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    recent.sort(key=lambda x: (rank.get(x.importance, 3), -x.date.toordinal()))

    # ── UPCOMING — 오늘 이후 일정, 날짜순. 발표 시각(release_utc)이 적힌 오늘 일정은 그 시각 전까지 남긴다(2026-10-14) ──
    upcoming: list[UpcomingEvent] = []
    for u in data.get("upcoming", []):
        day = _d(u["date"])
        rel = datetime.fromisoformat(str(u["release_utc"]).replace("Z", "+00:00")) if u.get("release_utc") else None
        if day is None or day < today or (day == today and (rel is None or rel <= as_of)):
            continue
        upcoming.append(UpcomingEvent(date=day, date_start=_d(u.get("date_start")), importance=str(imp.get(u["kind"], "MED")), kind=u["kind"], name=u["name"],  # type: ignore[arg-type]
                                      note=str(u.get("note", "")), days_ahead=(day - today).days, sources=[EventSource(**s) for s in u.get("sources", [])], release_utc=rel))
    upcoming.sort(key=lambda x: x.date)

    # ── 현재 regime 과의 연결 — 최근 물가 지표 ──────────
    link = None
    lk = [x for x in releases if x.key in set(cfg.get("link_keys", ["us_cpi"])) and x.regime.impact is not None]
    if lk:
        x = lk[0]
        dom = next((d for d in regime.drivers if d.id == regime.dominant), None)
        counts: dict[str, int] = {"SUPPORTED": 0, "CHALLENGED": 0, "NEUTRAL": 0}
        for it in recent:
            if it.impact is not None:
                counts[it.impact] += 1
        link = RegimeLink(current_driver=dom.label if dom else regime.dominant, current_driver_ko=dom.label_ko if dom else regime.dominant,
                          direction_ko={"up": "상승", "down": "하락", "flat": "보합"}.get(regime.rate_move.direction, ""), latest_key=x.key,
                          latest_label=f"Latest {x.name.replace('US ', '')}", latest_surprise=x.surprise, impact=x.regime.impact,  # type: ignore[arg-type]
                          sentence=x.regime.reason, counts=counts)

    note = (f"{data.get('collected', '')} 수기 확인 파일 기준. " + str(data.get("note", ""))).strip()
    return PolicyMacroEvents(as_of=as_of, collected=_d(data.get("collected")) or today, policy=policy, releases=releases, recent=recent,
                             recent_default=int(cfg.get("recent_default", 5)), upcoming=upcoming, upcoming_default=int(cfg.get("upcoming_default", 5)),
                             link=link, note=note, missing=sorted(set(missing)))
