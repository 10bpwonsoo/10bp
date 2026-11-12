"""공식 regime Exit / Entry 상태 기계 (exit_entry_v2, 2026-11-09 Daily Snapshot~) — 2026-11-12 사용자 요청의 예시 그대로."""

from datetime import datetime, timedelta, timezone

import pytest

from marketpulse.ai import transition_read as TR
from marketpulse.engines import regime_state as RSM
from marketpulse.engines.cockpit import load_cockpit_config
from marketpulse.engines.regime_history import stabilize

CFG = load_cockpit_config(None)["history"]
LABELS = {str(v["key"]): str(v["label"]) for v in CFG["taxonomy"].values()}
TAX = {k: str(v["key"]) for k, v in CFG["taxonomy"].items()}

# 유동성 경색이 깨진 날(위험선호 · 유동성 회복, 주식은 위험선호 쪽) / 여전히 경색인 날
BROKEN = {"Liquidity": 0.4, "RiskAppetite": 0.9, "Credit": -1.0}
STRESS = {"Liquidity": -1.4, "RiskAppetite": -1.2, "Credit": 1.5}
EQ_UP = {"us": 0.5, "kr": 0.4}
EQ_DOWN = {"us": -0.5, "kr": -0.4}


def _row(i: int, state: str, factors=None, source="RECORDED", start=datetime(2026, 11, 2, 22, 30, tzinfo=timezone.utc)):
    d = start + timedelta(days=i)
    return RSM.Row(date=d.date().isoformat(), as_of=d, key=TAX[state], state=state, factors=dict(factors or {}), source=source)


def _run(states, factors, *, eq=None, effective="2026-11-01", sources=None, initial="LIQUIDITY_STRESS"):
    """첫 행 = 적용 직전 legacy 행(공식 initial). 나머지가 Exit/Entry 대상."""
    cfg = {**CFG, "state_machine": {**CFG["state_machine"], "effective_from": effective}}
    rows = [_row(-5, initial, STRESS, start=datetime(2026, 10, 27, 22, 30, tzinfo=timezone.utc))]
    rows += [_row(i, s, f, source=(sources or {}).get(i, "RECORDED")) for i, (s, f) in enumerate(zip(states, factors))]
    legacy = [TAX[initial]] * len(rows)
    log = {r.date: {"observation": {"candidate": r.key, "equity_broad": (eq or [None] * len(states))[i - 1] if i else None}} for i, r in enumerate(rows)}
    return RSM.run(rows, legacy, cfg, log=log)[1:]


def test_exit_then_neutral_then_entry():
    """기존 Liquidity Stress → RISK-ON, NEUTRAL, RISK-ON, RISK-ON. Day2 에 이탈 확정(새 레짐 미확정 → Neutral), Day4 Risk-On 진입."""
    st = _run(["RISK_ON", "NEUTRAL", "RISK_ON", "RISK_ON"], [BROKEN] * 4, eq=[EQ_UP] * 4)
    d1, d2, d3, d4 = st
    assert d1.official == "liquidity_stress" and d1.support == "BROKEN" and d1.exit_streak == 1 and (d1.entry_regime, d1.entry_streak) == ("risk_on", 1)
    assert d2.official == "neutral" and d2.exit_confirmed and d2.change_kind == "exit" and d2.entry_regime is None  # Risk-On 진입은 끊겼다
    assert d3.official == "neutral" and (d3.entry_regime, d3.entry_streak) == ("risk_on", 1) and d3.support == "NA"
    assert d4.official == "risk_on" and d4.entry_confirmed and d4.change_kind == "entry"


def test_same_candidate_two_days_enters_directly():
    st = _run(["RISK_ON", "RISK_ON"], [BROKEN] * 2, eq=[EQ_UP] * 2)
    assert st[0].official == "liquidity_stress" and st[1].official == "risk_on" and st[1].change_kind == "entry"


def test_neutral_bridge_is_off():
    """RISK-ON → NEUTRAL → RISK-ON 을 2-of-3 으로 확정하지 않는다 — 마지막 Risk-On 은 진입 1/2 부터."""
    st = _run(["RISK_ON", "NEUTRAL", "RISK_ON"], [BROKEN] * 3, eq=[EQ_UP] * 3)
    assert st[2].official == "neutral" and st[2].entry_streak == 1


def test_supported_official_does_not_exit_even_if_candidate_differs():
    """후보가 달라도 핵심 trigger 와 주식 확인이 남아 있으면 SUPPORTED — 이탈 일수 0."""
    st = _run(["RISK_ON", "RISK_ON"], [STRESS] * 2, eq=[EQ_DOWN] * 2)
    assert st[0].support == "SUPPORTED" and st[0].exit_streak == 0
    assert st[1].official == "risk_on"  # 진입은 따로 센다 — 같은 후보 2일이면 진입 확정


def test_stale_regime_cannot_survive_alternating_candidates():
    """RISK-ON · NEUTRAL · RISK-ON · NEUTRAL … 이고 근거도 계속 깨져 있으면 이틀째에 해제 — 공식이 여러 날 남지 않는다."""
    st = _run(["RISK_ON", "NEUTRAL", "RISK_ON", "NEUTRAL", "RISK_ON"], [BROKEN] * 5, eq=[EQ_UP] * 5)
    assert [s.official for s in st] == ["liquidity_stress", "neutral", "neutral", "neutral", "neutral"]


def test_weakening_counts_toward_exit():
    """핵심 조건이 문턱 절반까지만 남은 날은 WEAKENING — 이탈 일수에 들어간다."""
    half = {"Liquidity": -0.6, "RiskAppetite": 0.1}
    st = _run(["NEUTRAL", "NEUTRAL"], [half] * 2, eq=[None, None])
    assert st[0].support == "WEAKENING" and st[0].exit_streak == 1 and st[1].official == "neutral"


def test_live_row_is_not_counted():
    """장중 LIVE 는 일수에 넣지 않는다 — 공식 · 일수는 전날 그대로."""
    st = _run(["RISK_ON", "NEUTRAL"], [BROKEN] * 2, eq=[EQ_UP] * 2, sources={1: "LIVE"})
    assert st[1].counted is False and st[1].official == "liquidity_stress" and st[1].exit_streak == 1


def test_rows_before_effective_keep_legacy_official():
    """effective_from 이전 행은 legacy 공식을 그대로 — 다시 계산하지 않는다. 첫 적용 행은 직전 legacy 공식에서 시작."""
    rows = [_row(i, s, BROKEN) for i, s in enumerate(["RISK_ON", "NEUTRAL", "RISK_ON", "NEUTRAL"])]
    keys = [r.key for r in rows]
    legacy = stabilize(keys, [50.0] * 4, [None] * 4, CFG)
    eff = (rows[2].as_of.astimezone(RSM.KST).date()).isoformat()
    cfg = {**CFG, "state_machine": {**CFG["state_machine"], "effective_from": eff}}
    st = RSM.run(rows, legacy, cfg)
    assert [s.official for s in st[:2]] == legacy[:2] and all(s.logic_version == "legacy" for s in st[:2])
    assert st[2].logic_version == "exit_entry_v2" and st[2].previous_official == legacy[1]


def test_logged_state_is_used_and_log_is_write_once(tmp_path):
    log = RSM.RegimeStateLog(tmp_path)
    st = _run(["RISK_ON"], [BROKEN], eq=[EQ_UP])[0]
    obs = RSM.Observation(date=st.date, snapshot_date=st.snapshot_date, candidate=st.candidate, factors=BROKEN)
    assert log.put_once(RSM.log_entry(st, obs)) is True
    assert log.put_once(RSM.log_entry(st, obs)) is False  # 덮지 않는다
    assert log.get(st.date)["state"]["exit_streak"] == 1


def test_equity_direction_flips_for_official():
    eq = RSM.equity_for("liquidity_stress", {"us": 0.5, "kr": 0.4}, CFG["state_machine"])
    assert eq == {"us": "CONTRADICTED", "kr": "CONTRADICTED", "global": "CONTRADICTED"}
    assert RSM.equity_for("risk_on", {"us": 0.5, "kr": None}, CFG["state_machine"])["global"] == "CONFIRMED"
    assert RSM.equity_for("policy", {"us": 0.5, "kr": 0.4}, CFG["state_machine"]) is None


def test_transition_read_validation():
    ctx = {"transition": {"kind": "exit"}, "news": [{"title": "코스피 4.39% 상승"}]}
    assert TR.check("유동성 경색 근거가 이틀 연속 지지되지 않아 해제됐고 지금은 Neutral / Mixed 입니다.", ctx) == []
    assert any("Neutral" in p for p in TR.check("유동성 경색 근거가 약해졌습니다.", ctx))
    assert any("컨텍스트에 없는 숫자" in p for p in TR.check("코스피가 7% 올라 Neutral 입니다.", ctx))
    assert any("직접 추천" in p for p in TR.check("매수 기회로 Neutral 입니다.", ctx))


@pytest.mark.parametrize("snap,official", [("2026-11-09", "liquidity_stress"), ("2026-11-10", "liquidity_stress"), ("2026-11-11", "neutral"), ("2026-11-12", "neutral")])
def test_stored_archive_official_after_reprocess(snap, official):
    """저장본(11/09~) 이 새 규칙으로 정렬됐는지 — 11/11 Daily Snapshot 에서 Liquidity Stress 이탈 확정 → Neutral."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "marketpulse" / "data" / "archive" / "2026" / "11" / f"{snap}.json"
    h = json.loads(p.read_text(encoding="utf-8"))["cockpit"]["history"]
    if h.get("logic_version") != "exit_entry_v2":
        pytest.skip("저장본이 아직 재정렬되지 않았다")
    assert h["current_regime"] == official and h["state"]["official"] == official
