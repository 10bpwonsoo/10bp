"""반도체 사이클 CYCLE READ (2026-11-24) — 국면 판정의 설명 레이어. 판정 · 점수 · 가중치는 건드리지 않는다."""
import copy
import json
import re
from pathlib import Path

import pytest

from marketpulse.ai import semi_cycle_read as CR
from marketpulse.engines.semiconductor_cycle import load_config

ROOT = Path(__file__).resolve().parents[1]
CAP = ROOT / "marketpulse" / "data" / "captures" / "2026-11-24-backfill"


@pytest.fixture()
def cyc():
    d = json.loads((CAP / "semiconductor_cycle.json").read_text(encoding="utf-8"))
    d.pop("cycle_read", None)
    return d


@pytest.fixture()
def session():
    return json.loads((CAP / "semiconductor_cycle_read_session.json").read_text(encoding="utf-8"))


def _check(out, cyc):
    cfg = load_config()
    return CR.check_output(CR.normalize_output(out), CR.build_context(cyc, cfg["regime"]), cfg["cycle_read"])


def test_context_sides_follow_the_engine_scores_and_carry_the_definitions(cyc):
    ctx = CR.build_context(cyc, load_config()["regime"])
    side = {f["key"]: f["side"] for f in ctx["factors"]}
    for c in cyc["regime"]["components"]:
        want = "no_data" if c["score"] is None else "support" if c["score"] >= 10 else "constraint" if c["score"] <= -10 else "neutral"
        assert side[c["key"]] == want
    assert side["equity"] == "constraint" and side["eps_revision"] == "no_data"
    # Equity Confirm(현물과 같은 방향인가) 과 Equity 점수(주가 방향 · 크기)는 다른 개념 — 정의와 현물 방향을 함께 넘긴다
    assert ctx["equity_confirm"]["status"] == "BROAD CONFIRMATION" and ctx["equity_confirm"]["memory_price_direction"] == "down"
    assert "같은지" in ctx["equity_confirm"]["definition"] and "조짐" in ctx["turning_point"]["definition"]
    assert ctx["path"]["previous_state"] == "Upswing" and ctx["regime"]["thresholds"][0] == {"state": "STRONG UPSWING", "composite_min": 55}


def test_session_read_passes_and_is_attached_without_touching_the_verdict(cyc, session):
    before = copy.deepcopy(cyc)
    out = CR.attach_cycle_read(cyc, session)
    cr = out["cycle_read"]
    assert cr["status"] == "ok" and cr["source"] == "llm" and cr["generator"] == "session"
    assert 2 <= len(CR.split_sentences(cr["read"])) <= 3 and cr["verdict"]
    assert [r["label"] for r in cr["support"]] == ["HBM", "Spot Premium", "Export Nowcast", "Contract Price"]
    assert {r["key"] for r in cr["constraint"]} == {"equity", "memory_pricing", "premium_breadth", "supply_news"}
    assert {k: v for k, v in out.items() if k != "cycle_read"} == before  # 국면 · composite · 신뢰도 · 점수 · 가중치 · MARKET READ 는 그대로
    assert not re.search(r"확률|매수|매도|전망", json.dumps(cr, ensure_ascii=False))


def test_validator_rejects_wrong_side_numbers_and_forbidden_words(cyc, session):
    assert _check(session, cyc) == []
    bad = copy.deepcopy(session); bad["support"].append({"key": "equity", "note": "주가 확인"})  # 주가 점수는 제약인데 지지에 넣었다(5개이기도 하다)
    assert any("넣을 수 없는 증거: equity" in p for p in _check(bad, cyc))
    bad = copy.deepcopy(session); bad["read"] += " 점수는 100, 94, 69 입니다."
    probs = _check(bad, cyc)
    assert any("문장 수" in p for p in probs) and any("숫자" in p for p in probs)
    bad = copy.deepcopy(session); bad["read"] = bad["read"].replace("신뢰도는 44 에", "신뢰도는 57 에")
    assert any("컨텍스트에 없는 숫자: 57" in p for p in _check(bad, cyc))
    bad = copy.deepcopy(session); bad["verdict"] = "반도체 매수 구간"
    assert any("매수" in p for p in _check(bad, cyc))
    bad = copy.deepcopy(session); bad["constraint"] = bad["constraint"][:1]
    assert any("constraint 1개" in p for p in _check(bad, cyc))
    bad = copy.deepcopy(session); bad["support"][0]["note"] = "HBM 점수 100"
    assert any("숫자를 쓰지 않는다" in p for p in _check(bad, cyc))


def test_no_llm_and_no_session_leaves_it_empty_not_a_template(cyc, session):
    out = CR.attach_cycle_read(copy.deepcopy(cyc), None)
    assert out["cycle_read"]["status"] == "unavailable" and out["cycle_read"]["read"] == "" and out["cycle_read"]["support"] == []
    broken = copy.deepcopy(session); broken["read"] = "한 문장뿐입니다."
    cr = CR.attach_cycle_read(copy.deepcopy(cyc), broken)["cycle_read"]
    assert cr["status"] == "unavailable" and any("세션 생성본 검증 실패" in w for w in cr["warnings"])
    nothing = copy.deepcopy(cyc); nothing["regime"]["composite"] = None
    assert CR.attach_cycle_read(nothing, session)["cycle_read"]["status"] == "unavailable"


def test_screen_scale_matches_the_engine_thresholds():
    """화면의 composite 구간 설명(frontend semiExplain.ts)은 config 의 regime.states 와 같아야 한다."""
    ts = (ROOT / "frontend" / "src" / "components" / "semiExplain.ts").read_text(encoding="utf-8")
    block = ts.split("export const REGIME_SCALE", 1)[1].split("];", 1)[0]
    got = [(m.group(1), float(m.group(2))) for m in re.finditer(r'key:\s*"([A-Z_]+)",\s*min:\s*(-?[\d.]+)', block)]
    want = [(s["key"], float(s["min"])) for s in load_config()["regime"]["states"] if s["min"] > -1000]
    assert got == want
