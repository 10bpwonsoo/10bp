"""AI THEME VIEW (2026-11-12) — 필드 구조만 고정, 내용은 LLM. 검증 · 결측 · 저장/캐시 규칙."""
import json
from pathlib import Path

from marketpulse.ai import ai_theme_view as V

CAP = Path(__file__).resolve().parents[1] / "marketpulse" / "data" / "captures" / "2026-11-12-backfill"


def _ctx():
    ai = json.loads((CAP / "ai_regime.json").read_text(encoding="utf-8"))
    return V.build_context(ai, semi=json.loads((CAP / "semiconductor_cycle.json").read_text(encoding="utf-8")),
                           cockpit=json.loads((CAP / "cockpit.json").read_text(encoding="utf-8")))


GOOD = {"headline": "가격은 앞서고 펀더멘털은 아직 확인되지 않은 반등", "summary": "소프트웨어와 전력이 반등을 이끌었습니다. 다만 반도체 펀더멘털이 이를 확인하지 못했습니다.",
        "driver": "소프트웨어 · 전력", "strength": "상대강도 회복", "weak_point": "펀더멘털 미확인", "next_watch": "메모리 가격이 버티는지"}


def test_context_has_all_inputs_and_missing():
    c = _ctx()
    for k in ("ai_trade_regime", "status_strip", "ai_vs_nasdaq", "drivers", "breadth", "narrative", "macro", "ai_specific_stress", "fundamental_confirmation",
              "semiconductor_confirmation", "transmission_chain", "ai_sentiment_greed_fear", "ai_news", "korea_ai_semis_stocks", "semiconductor_cycle", "market_regime", "ai_regime_read"):
        assert c.get(k) not in (None, "", []), k
    assert any("EPS" in m for m in c["missing"])  # 결측은 알려 주고 결론에 쓰지 않게 한다


def test_check_passes_and_rejects():
    c = _ctx()
    assert V.check(GOOD, c) == []
    assert any("headline" in p for p in V.check({**GOOD, "headline": "가" * 41}, c))
    assert any("summary 문장 수" in p for p in V.check({**GOOD, "summary": "한 문장만 있습니다."}, c))
    assert any("직접 추천" in p for p in V.check({**GOOD, "next_watch": "매수 시점 확인"}, c))
    assert any("컨텍스트에 없는 숫자" in p for p in V.check({**GOOD, "summary": GOOD["summary"] + " 바스켓이 77.7% 올랐습니다."}, c))
    assert any("READ" in p for p in V.check({**GOOD, "summary": GOOD["summary"] + " " + c["ai_regime_read"].split(". ")[0].rstrip(".") + "."}, c))


def test_no_rule_fallback_when_llm_and_session_missing():
    v = V.write(_ctx(), client=None, session_read=None)
    assert v["status"] == "unavailable" and v["headline"] == "" and v["summary"] == ""


def test_session_is_used_only_when_valid():
    c = _ctx()
    assert V.write(c, session_read=GOOD)["source"] == "session"
    assert V.write(c, session_read={**GOOD, "summary": ""})["status"] == "unavailable"


def test_live_cache_reuses_view_for_same_fingerprint():
    calls = []

    class Fake:
        enabled = True

        def interpret(self, **kw):
            calls.append(1)
            return GOOD

    ai = json.loads((CAP / "ai_regime.json").read_text(encoding="utf-8"))
    V._LIVE.clear()
    a = V.live_view(ai, client=Fake()); b = V.live_view({**ai, "as_of": "2026-11-12T01:00:00Z"}, client=Fake())
    assert a["status"] == "ok" and a == b and len(calls) == 1  # 같은 판정이면 다시 부르지 않는다
    V.live_view({**ai, "regime": "broad_ai_selloff"}, client=Fake())
    assert len(calls) == 2


def test_stored_view_on_archive():
    p = Path(__file__).resolve().parents[1] / "marketpulse" / "data" / "archive" / "2026" / "11" / "2026-11-12.json"
    tv = json.loads(p.read_text(encoding="utf-8"))["ai_regime"].get("theme_view")
    assert tv and tv["status"] == "ok" and tv["source"] in ("llm", "session") and tv["headline"]
