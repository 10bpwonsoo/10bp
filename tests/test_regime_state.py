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


# ── same_day_v1 (2026-11-22 요청, 2026-11-20 Daily Snapshot~) — 그날 선택이 곧 공식 ─────────────
def _same_day_run(states, *, sources=None, initial="NEUTRAL", same_day_from="2026-11-03"):
    """첫 행 = 적용 직전 legacy 행. as_of 22:30 UTC = 다음 날 07:30 KST 라 행 i 의 snapshot_date 는 11/(3+i)."""
    cfg = {**CFG, "state_machine": {**CFG["state_machine"], "effective_from": "2026-11-01", "same_day_from": same_day_from}}
    rows = [_row(-5, initial, {}, start=datetime(2026, 10, 27, 22, 30, tzinfo=timezone.utc))]
    rows += [_row(i, s, {}, source=(sources or {}).get(i, "RECORDED")) for i, s in enumerate(states)]
    return RSM.run(rows, [TAX[initial]] * len(rows), cfg)[1:]


def test_same_day_official_follows_each_days_selection():
    """확인 일수 없이 그날 선택이 곧 공식 — 방향이 바뀌면 바로 바뀌고, 후보가 없으면(NEUTRAL) Neutral / Mixed."""
    d1, d2, d3, d4, d5 = _same_day_run(["GROWTH_SHOCK", "RISK_OFF", "RISK_OFF", "NEUTRAL", "NEUTRAL"])
    assert (d1.logic_version, d1.previous_official, d1.official, d1.change_kind) == (RSM.SAME_DAY, "neutral", "growth", "entry")
    assert d1.entry_confirmed and (d1.entry_streak, d1.entry_required, d1.exit_required) == (1, 1, 1) and d1.support == "NA"
    assert (d2.previous_official, d2.official, d2.change_kind, d2.exited_regime) == ("growth", "liquidity_stress", "entry", "growth")
    assert d3.official == "liquidity_stress" and not d3.changed and d3.entry_regime is None and d3.exit_streak == 0
    assert (d4.official, d4.change_kind, d4.exited_regime, d4.exit_confirmed) == ("neutral", "exit", "liquidity_stress", True)
    assert d5.official == "neutral" and not d5.changed


def test_same_day_starts_only_from_its_snapshot_date():
    """same_day_from 이전 Daily Snapshot 은 exit_entry_v2 그대로(진입 1/2) — 그날부터만 바로 공식이 된다."""
    d1, d2, d3 = _same_day_run(["GROWTH_SHOCK", "RISK_OFF", "RISK_OFF"], same_day_from="2026-11-05")
    assert (d1.logic_version, d1.official, d1.entry_regime, d1.entry_streak) == ("exit_entry_v2", "neutral", "growth", 1)
    assert (d2.logic_version, d2.official, d2.entry_regime, d2.entry_streak) == ("exit_entry_v2", "neutral", "liquidity_stress", 1)
    assert (d3.logic_version, d3.previous_official, d3.official) == (RSM.SAME_DAY, "neutral", "liquidity_stress")
    assert RSM.is_same_day({"same_day_from": "2026-11-20"}, "2026-11-20") and not RSM.is_same_day({"same_day_from": "2026-11-20"}, "2026-11-19")
    assert not RSM.is_same_day({}, "2026-11-25")   # 설정이 비면 exit_entry_v2 가 계속 쓰인다


def test_same_day_live_row_does_not_change_official():
    """장중(LIVE) 값은 공식을 바꾸지 않는다 — 다음 Daily Snapshot 의 선택이 정한다."""
    d1, d2, d3 = _same_day_run(["GROWTH_SHOCK", "RISK_OFF", "RISK_OFF"], sources={1: "LIVE"})
    assert d1.official == "growth"
    assert d2.official == "growth" and not d2.counted and not d2.changed and d2.candidate == "liquidity_stress"
    assert d3.official == "liquidity_stress" and d3.previous_official == "growth" and d3.changed


def test_same_day_texts_and_configured_start():
    """문구 — 진행 일수(1/2 · 2거래일)를 말하지 않는다. 운영 설정의 시작일은 2026-11-20 Daily Snapshot."""
    from types import SimpleNamespace

    from marketpulse.engines.cockpit import state_read
    from marketpulse.engines.regime_select import persistence_hint_v2
    assert CFG["state_machine"]["same_day_from"] == "2026-11-20"
    full = load_cockpit_config(None)
    st = SimpleNamespace(logic_version=RSM.SAME_DAY, counted=True, changed=True, change_kind="entry", official="growth", official_label="Growth", candidate="growth", candidate_label="Growth",
                         previous_official="neutral", previous_official_label="Neutral / Mixed", exited_label=None, exit_streak=0, entry_streak=1, exit_required=1, entry_required=1, entry_regime="growth", support="NA")
    t = state_read(full, st)
    assert "Neutral / Mixed" in t and "Growth" in t and "거래일" not in t and "/1" not in t
    st.change_kind = "exit"; st.official = "neutral"; st.official_label = "Neutral / Mixed"; st.previous_official = "growth"; st.previous_official_label = "Growth"; st.candidate = "neutral"
    assert "Growth" in state_read(full, st) and "Neutral / Mixed" in state_read(full, st)
    hint = persistence_hint_v2("Neutral / Mixed", {"rule_today": "same_day", "official": "neutral"})
    assert "오늘 선택이 곧 공식" in hint and "2일" not in hint
    assert "2일 연속" in persistence_hint_v2("Neutral / Mixed", {"official": "neutral"})   # 예전 규칙의 안내는 그대로


@pytest.mark.parametrize("snap,previous,official", [("2026-11-20", "neutral", "growth"), ("2026-11-21", "growth", "liquidity_stress")])
def test_stored_archives_from_1120_use_same_day_rule(snap, previous, official):
    """2026-11-22 정정 — 11/20 스냅샷부터 저장본의 공식 regime 은 그날 선택이다(11/20 Growth, 11/21 Liquidity Stress / Risk-Off)."""
    import json
    from pathlib import Path
    doc = json.loads((Path(__file__).resolve().parents[1] / "marketpulse" / "data" / "archive" / "2026" / "11" / f"{snap}.json").read_text(encoding="utf-8"))
    h = doc["cockpit"]["history"]; st = h["state"]
    assert h["logic_version"] == RSM.SAME_DAY and st["logic_version"] == RSM.SAME_DAY
    assert (st["previous_official"], st["official"], st["candidate"], st["changed"]) == (previous, official, official, True)
    assert h["current_regime"] == official and doc["cockpit"]["market_now"]["transition_status"] == "CHANGED"
    assert any("same_day_v1" in str(c.get("reason", "")) for c in doc["meta"].get("corrections") or [])


def test_stored_archive_before_1120_keeps_exit_entry_rule():
    """11/19 스냅샷(그 전 날짜)은 손대지 않았다 — exit_entry_v2 그대로."""
    import json
    from pathlib import Path
    doc = json.loads((Path(__file__).resolve().parents[1] / "marketpulse" / "data" / "archive" / "2026" / "11" / "2026-11-19.json").read_text(encoding="utf-8"))
    assert doc["cockpit"]["history"]["logic_version"] == "exit_entry_v2" and doc["cockpit"]["history"]["state"]["official"] == "neutral"
