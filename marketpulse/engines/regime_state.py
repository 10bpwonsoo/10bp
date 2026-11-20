"""
공식 regime 의 Exit / Entry 상태 기계 (2026-11-12 요청, 2026-11-09 Daily Snapshot 부터 적용).

예전 규칙(stabilize)은 "새 regime 이 2거래일 연속이어야 바뀐다" 하나뿐이라, 새 후보가 날마다 바뀌면 이미 깨진 공식 regime 이
여러 날 남았다(11/02~11/11 Liquidity Stress). 여기서는 두 질문을 따로 본다.

  EXIT  — 지금 공식 regime 이 그날 데이터로 아직 지지되는가(SUPPORTED · WEAKENING · BROKEN). 지지되지 않는 날(WEAKENING · BROKEN)이
          exit_days 거래일 이어지면 공식 regime 을 해제한다.
  ENTRY — 공식과 다른 방향성 후보가 서로 다른 거래일 entry_days 일 연속 선택되면 그 후보가 공식이 된다.

해제됐는데 새 후보가 아직 확정되지 않았으면 공식은 NEUTRAL / MIXED 다(오류가 아니라 정상 중간 상태). Neutral bridge(2-of-3)는 쓰지 않는다.

날짜 원칙
- effective_from(KST Daily Snapshot 날짜) 이전 행의 공식 regime 은 예전 규칙 그대로(legacy) — 다시 계산하지 않는다.
- 첫 적용 행의 시작 상태 = 그 직전 행의 legacy 공식 regime. 그 앞의 저장값은 읽기만 한다.
- 행은 시장 날짜마다 하나다(같은 날 장중 값은 세지 않는다). LIVE 행(장중)은 일수에 넣지 않는다 — 공식은 전날 그대로, 후보만 'LIVE CANDIDATE'.
- 날짜 i 의 상태는 i 까지의 관측만 본다(look-ahead 없음). 저장된 상태(regime_state 로그)가 있으면 그것을 쓴다 — 뒤에 날이 붙어도 바뀌지 않는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

KST = timezone(timedelta(hours=9))
NEUTRAL = "neutral"
LEGACY = "legacy"

_EXPR = re.compile(r"^\s*(abs\()?\s*([A-Za-z_]+)\s*\)?\s*(>=|<=)\s*([+-]?\d+(?:\.\d+)?)\s*$")


def snapshot_date_of(as_of: datetime | None) -> date | None:
    """행의 as_of(UTC) → 그 판정이 나온 KST Daily Snapshot 날짜."""
    if as_of is None:
        return None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return as_of.astimezone(KST).date()


@dataclass
class Observation:
    """하루치 판정 재료 — 그 Daily Snapshot cutoff 에 이미 있던 값만."""

    date: str                                  # 행(시장) 날짜
    snapshot_date: str                         # KST Daily Snapshot 날짜
    candidate: str                             # 그날 선택된 후보의 taxonomy key
    candidate_state: str = ""                  # StateLabel(RISK_ON …)
    raw_signal: str | None = None              # 정량 raw StateLabel(selection.quant_label) — 없으면 None
    factors: Mapping[str, float | None] = field(default_factory=dict)
    equity_broad: Mapping[str, float | None] | None = None   # 위험선호 기준 주식 점수 {us, kr} (−1…+1). 없으면 None
    counted: bool = True                       # LIVE(장중) 이면 False


@dataclass
class State:
    logic_version: str
    snapshot_date: str
    date: str
    official: str
    previous_official: str | None
    candidate: str
    candidate_state: str = ""
    raw_signal: str | None = None
    support: str = "NA"
    support_reasons: list[str] = field(default_factory=list)
    equity: dict[str, str] | None = None
    exit_streak: int = 0
    exit_required: int = 2
    exit_confirmed: bool = False
    exited_regime: str | None = None
    entry_regime: str | None = None
    entry_streak: int = 0
    entry_required: int = 2
    entry_confirmed: bool = False
    changed: bool = False
    change_kind: str | None = None             # exit · entry · legacy
    counted: bool = True

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "State":
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: d[k] for k in keys if k in d})


# ── 설정 ─────────────────────────────────────────────────
def sm_config(history_cfg: Mapping) -> dict:
    return dict((history_cfg or {}).get("state_machine") or {})


def effective_from(smcfg: Mapping) -> date | None:
    v = smcfg.get("effective_from")
    return date.fromisoformat(str(v)) if v else None


def _cond(expr: str, factors: Mapping[str, float | None], near_ratio: float) -> tuple[bool | None, bool | None, str]:
    """(충족, 문턱의 near_ratio 까지는 와 있음, 설명). factor 가 없으면 (None, None)."""
    m = _EXPR.match(expr)
    if not m:
        return None, None, expr
    is_abs, name, op, thr = bool(m.group(1)), m.group(2), m.group(3), float(m.group(4))
    v = factors.get(name)
    if v is None:
        return None, None, f"{name} 결측"
    x = abs(v) if is_abs else float(v)
    ok = x >= thr if op == ">=" else x <= thr
    near = x >= thr * near_ratio if op == ">=" else x <= thr * near_ratio
    shown = f"|{name}|" if is_abs else name
    return ok, near, f"{shown} {op.replace('>=', '≥').replace('<=', '≤')} {thr:+.1f} {'충족' if ok else '미충족'}(지금 {x:+.2f})"


def _status(score: float | None, smcfg: Mapping) -> str:
    s = smcfg.get("equity_status") or {}
    if score is None:
        return "UNAVAILABLE"
    if score >= float(s.get("strong", 0.6)):
        return "STRONG"
    if score >= float(s.get("confirmed", 0.25)):
        return "CONFIRMED"
    if score <= float(s.get("contradicted", -0.25)):
        return "CONTRADICTED"
    return "PARTIAL"


def equity_for(official: str, broad: Mapping[str, float | None] | None, smcfg: Mapping) -> dict[str, str] | None:
    """위험선호 기준 주식 점수를 공식 regime 이 기대하는 방향으로 돌려 US · KOREA · GLOBAL 상태로. 방향 기대가 없거나 점수가 없으면 None."""
    sign = int((smcfg.get("equity_direction") or {}).get(official, 0))
    if not broad or sign == 0:
        return None
    us = broad.get("us"); kr = broad.get("kr")
    have = [x for x in (us, kr) if x is not None]
    if not have:
        return None
    g = sign * sum(have) / len(have)
    out = {"us": _status(None if us is None else sign * us, smcfg), "kr": _status(None if kr is None else sign * kr, smcfg), "global": _status(g, smcfg)}
    if len(have) == 2 and {"STRONG", "CONFIRMED"} & {out["us"], out["kr"]} and "CONTRADICTED" in {out["us"], out["kr"]}:
        out["global"] = "MIXED"
    elif len(have) == 1 and out["global"] == "STRONG":
        out["global"] = "CONFIRMED"
    return out


def support(official: str, obs: Observation, smcfg: Mapping, labels: Mapping[str, str]) -> tuple[str, list[str], dict[str, str] | None]:
    """공식 regime 이 그날 데이터로 지지되는가 — (SUPPORTED · WEAKENING · BROKEN · NA, 이유, 주식 확인)."""
    if official == NEUTRAL:
        return "NA", ["Neutral / Mixed 는 해제할 방향이 없다 — 새 후보의 진입 확인만 본다"], None
    eq = equity_for(official, obs.equity_broad, smcfg)
    name = labels.get(official, official)
    if obs.candidate == official:
        return "SUPPORTED", [f"오늘 선택된 후보도 {name}"], eq
    near_ratio = float(smcfg.get("near_ratio", 0.5))
    exprs = [str(x) for x in ((smcfg.get("core") or {}).get(official) or [])]
    oks: list[bool | None] = []; nears: list[bool | None] = []; why: list[str] = []
    for e in exprs:
        ok, near, txt = _cond(e, obs.factors, near_ratio)
        oks.append(ok); nears.append(near); why.append(txt)
    core_ok = any(x is True for x in oks)
    core_near = any(x is True for x in nears)
    g = (eq or {}).get("global")
    eq_ok = g in ("STRONG", "CONFIRMED")
    eq_against = g == "CONTRADICTED"
    reasons = [f"핵심 조건: {' · '.join(why) if why else '정의 없음'}"]
    if eq is not None:
        reasons.append(f"주식 확인({name} 기준): US {eq['us']} · KOREA {eq['kr']} · GLOBAL {eq['global']}")
    else:
        reasons.append("주식 확인: 그날 주식 판독이 없어 핵심 조건으로만 본다")
    reasons.append(f"오늘 후보는 {labels.get(obs.candidate, obs.candidate)}")
    if core_ok and not eq_against and (eq_ok or eq is None):
        return "SUPPORTED", reasons, eq
    if core_ok or eq_ok or (core_near and not eq_against):
        return "WEAKENING", reasons, eq
    return "BROKEN", reasons, eq


def step(prev: State, obs: Observation, smcfg: Mapping, labels: Mapping[str, str]) -> State:
    """전날 상태 + 오늘 관측 → 오늘 상태. 출구(exit)와 진입(entry) 일수는 따로 센다."""
    need_entry = int(smcfg.get("entry_days", 2)); need_exit = int(smcfg.get("exit_days", 2))
    official = prev.official
    sup, reasons, eq = support(official, obs, smcfg, labels)
    st = State(logic_version=str(smcfg.get("logic_version", "exit_entry_v2")), snapshot_date=obs.snapshot_date, date=obs.date, official=official,
               previous_official=official, candidate=obs.candidate, candidate_state=obs.candidate_state, raw_signal=obs.raw_signal, support=sup,
               support_reasons=reasons, equity=eq, exit_required=need_exit, entry_required=need_entry, counted=obs.counted)
    if not obs.counted:
        # 장중 LIVE — 일수에 넣지 않는다. 공식 · 일수는 전날 그대로, 후보만 보인다
        st.exit_streak, st.entry_regime, st.entry_streak = prev.exit_streak, prev.entry_regime, prev.entry_streak
        return st
    # ENTRY — 공식과 다른 방향성 후보가 연속으로 선택된 거래일 수(Neutral 후보는 진입 후보가 아니다)
    if obs.candidate != NEUTRAL and obs.candidate != official:
        st.entry_regime = obs.candidate
        st.entry_streak = prev.entry_streak + 1 if (prev.entry_regime == obs.candidate and prev.candidate == obs.candidate) else 1
    # EXIT — 공식 regime 이 지지되지 않은 거래일 수(SUPPORTED 면 0 으로)
    if official != NEUTRAL:
        st.exit_streak = 0 if sup == "SUPPORTED" else prev.exit_streak + 1
    if st.entry_regime is not None and st.entry_streak >= need_entry:
        st.official = st.entry_regime; st.entry_confirmed = True; st.changed = True; st.change_kind = "entry"
        st.exited_regime = official if official != NEUTRAL else None
    elif official != NEUTRAL and st.exit_streak >= need_exit:
        st.official = NEUTRAL; st.exit_confirmed = True; st.changed = True; st.change_kind = "exit"; st.exited_regime = official
    return st


# ── 저장 로그(쓰기 한 번) ─────────────────────────────────
class RegimeStateLog:
    """marketpulse/data/regime_state/<행 날짜>.json — Daily Snapshot 이 그날 상태를 한 번 쓴다. 이미 있으면 덮지 않는다.
    고칠 일이 생기면 replace(..., reason) 로만 — 이전 파일은 superseded/ 에 남긴다."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _p(self, d: str) -> Path:
        return self.root / f"{d}.json"

    def get(self, d: str) -> dict | None:
        p = self._p(d)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def all(self) -> dict[str, dict]:
        if not self.root.exists():
            return {}
        return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.root.glob("*.json"))}

    def put_once(self, entry: Mapping[str, Any]) -> bool:
        p = self._p(str(entry["date"]))
        if p.exists():
            return False
        self.root.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
        return True

    def replace(self, entry: Mapping[str, Any], *, reason: str) -> Path | None:
        p = self._p(str(entry["date"]))
        old = None
        if p.exists():
            sup = self.root / "superseded"; sup.mkdir(parents=True, exist_ok=True)
            old = sup / f"{p.stem}.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
            old.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        e = dict(entry); e.setdefault("corrections", []); e["corrections"] = list(e["corrections"]) + [{"reason": reason, "at": datetime.now(timezone.utc).isoformat(), "previous": str(old) if old else None}]
        self.root.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        return old


def log_entry(state: State, obs: Observation, *, written_at: datetime | None = None, transition_comment: Mapping[str, Any] | None = None) -> dict:
    return {"date": obs.date, "snapshot_date": obs.snapshot_date, "logic_version": state.logic_version,
            "observation": {"candidate": obs.candidate, "candidate_state": obs.candidate_state, "raw_signal": obs.raw_signal,
                            "factors": dict(obs.factors), "equity_broad": dict(obs.equity_broad) if obs.equity_broad else None},
            "state": state.as_dict(), "transition_comment": dict(transition_comment) if transition_comment else None,
            "written_at": (written_at or datetime.now(timezone.utc)).isoformat()}


def broad_equity_from_selection(sel: Any) -> dict[str, float | None] | None:
    """REGIME v2 선택의 neutral_equity(위험선호 기준 주식 판독) → {us, kr} 점수. 없으면 None."""
    if sel is None:
        return None
    ne = sel.get("neutral_equity") if isinstance(sel, Mapping) else getattr(sel, "neutral_equity", None)
    if ne is None:
        return None
    g = (lambda m: (ne.get(m) or {}).get("score")) if isinstance(ne, Mapping) else (lambda m: getattr(getattr(ne, m, None), "score", None))
    us, kr = g("us"), g("kr")
    return None if us is None and kr is None else {"us": us, "kr": kr}


# ── 전체 sequence ────────────────────────────────────────
@dataclass
class Row:
    date: str
    as_of: datetime | None
    key: str
    state: str
    factors: Mapping[str, float | None]
    source: str = "RECORDED"


def run(rows: Sequence[Row], legacy: Sequence[str], history_cfg: Mapping, *, log: Mapping[str, Mapping] | None = None,
        today: Observation | None = None) -> list[State]:
    """행마다 State. effective_from 이전은 legacy 공식 그대로, 그 뒤는 Exit/Entry. log 에 그날 상태가 있으면(같은 후보일 때) 그대로 쓴다."""
    smcfg = sm_config(history_cfg)
    eff = effective_from(smcfg)
    labels = {str(v["key"]): str(v["label"]) for v in ((history_cfg or {}).get("taxonomy") or {}).values()}
    log = log or {}
    out: list[State] = []
    prev: State | None = None
    for i, r in enumerate(rows):
        sd = snapshot_date_of(r.as_of)
        if eff is None or sd is None or sd < eff:
            st = State(logic_version=LEGACY, snapshot_date="" if sd is None else sd.isoformat(), date=r.date, official=legacy[i],
                       previous_official=legacy[i - 1] if i else None, candidate=r.key, candidate_state=r.state, support="NA",
                       changed=bool(i and legacy[i] != legacy[i - 1]), change_kind="legacy" if (i and legacy[i] != legacy[i - 1]) else None)
            out.append(st); prev = st
            continue
        if prev is None or prev.logic_version == LEGACY:
            # 첫 적용 행 — 직전 저장 행의 공식 regime 을 시작 상태로(그 앞은 읽기만)
            start = prev.official if prev is not None else r.key
            prev = State(logic_version=str(smcfg.get("logic_version", "exit_entry_v2")), snapshot_date="", date="", official=start, previous_official=None, candidate=start)
        logged = log.get(r.date)
        ls = (logged or {}).get("state")
        if ls and (logged.get("observation") or {}).get("candidate") == r.key and r.source != "LIVE":
            st = State.from_dict(ls)
        else:
            if today is not None and today.date == r.date:
                obs = today
            else:
                lo = (logged or {}).get("observation") or {}
                obs = Observation(date=r.date, snapshot_date=sd.isoformat(), candidate=r.key, candidate_state=r.state,
                                  raw_signal=lo.get("raw_signal"), factors=dict(r.factors), equity_broad=lo.get("equity_broad"))
            obs.counted = r.source != "LIVE"
            st = step(prev, obs, smcfg, labels)
        out.append(st)
        prev = st if st.counted else prev  # 장중 값은 다음 날 상태에 이어지지 않는다
    return out


def raw_signal_run(states: Sequence[State]) -> int:
    """오늘까지 같은 정량 raw 신호가 이어진 Daily Snapshot 수(관측이 있는 날만, 장중 제외)."""
    xs = [s.raw_signal for s in states if s.counted]
    if not xs or xs[-1] is None:
        return 0
    n = 0
    for x in reversed(xs):
        if x != xs[-1]:
            break
        n += 1
    return n


def iter_dates(states: Iterable[State]) -> list[str]:
    return [s.date for s in states]
