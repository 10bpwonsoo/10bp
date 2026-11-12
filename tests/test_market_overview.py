"""MARKET OVERVIEW (2026-11-12) — 기존 섹션만 읽는 LLM 종합: 구조 고정 · 검증 · 결측 · 지난 일정 금지 · 매매 지시 금지 · 저장/캐시."""
import json
from pathlib import Path

from marketpulse.ai import market_overview as MO

ROOT = Path(__file__).resolve().parents[1]
DOC = json.loads((ROOT / "marketpulse/data/archive/2026/11/2026-11-12.json").read_text(encoding="utf-8"))
SESSION = {k: v for k, v in json.loads((ROOT / "marketpulse/data/captures/2026-11-12-backfill/market_overview_session.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}


def test_context_reads_existing_sections_only():
    c = MO.build_context(DOC)
    assert c["snapshot_date"] == "2026-11-12"
    assert c["market_regime"]["official"] == "NEUTRAL / MIXED" and c["market_regime"]["candidate"] == "Risk-On"
    assert c["rates"]["regime"] and c["oil"]["regime"] and c["ai_theme"]["regime"] and c["semiconductor_cycle"]["regime"]
    assert all(u["date"] >= "2026-11-12" for u in c["upcoming_events"])  # 지난 일정은 catalyst 후보가 아니다
    assert any("EXCLUDED" in m or "없음" in m for m in c["missing"])


def test_missing_sections_become_missing_not_zero():
    c = MO.build_context({"snapshot": DOC["snapshot"], "cockpit": DOC["cockpit"]})
    assert "rates_regime 섹션 없음" in c["missing"] and c["semiconductor_cycle"] is None


def test_check_accepts_session_and_rejects_bad_output():
    c = MO.build_context(DOC)
    assert MO.check(SESSION, c) == []
    bad = json.loads(json.dumps(SESSION))
    bad["portfolio_implication"]["equity_stance"] = "반도체 매수"
    assert any("금지어" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["catalysts"][0]["date"] = "2026-11-10"; bad["catalysts"][0]["event"] = "CPI"
    assert any("upcoming_events" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["sector_view"]["positive"] = ["Biotech"]
    assert any("sector_names" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["market_view"] = SESSION["market_view"] + " 지수는 77.7% 올랐습니다."
    assert any("컨텍스트에 없는 숫자" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["labels"]["equity"] = "Great"
    assert any("labels.equity" in p for p in MO.check(bad, c))


def test_no_rule_fallback():
    r = MO.write(MO.build_context(DOC), client=None, session_read=None)
    assert r["status"] == "unavailable" and r["view"] is None


def test_live_cache_only_on_meaningful_change():
    calls = []

    class Fake:
        enabled = True

        def interpret(self, **kw):
            calls.append(1)
            return SESSION

    MO._LIVE.clear()
    a = MO.live_overview(DOC, client=Fake())
    tick = json.loads(json.dumps(DOC)); tick["snapshot"]["as_of"] = "2026-11-11T23:00:00Z"
    b = MO.live_overview(tick, client=Fake())
    assert a["status"] == "ok" and b["view"] == a["view"] and len(calls) == 1
    moved = json.loads(json.dumps(DOC)); moved["cockpit"]["market_now"]["state"]["candidate_label"] = "Neutral / Mixed"
    MO.live_overview(moved, client=Fake())
    assert len(calls) == 2


def test_archive_section_stored():
    mo = DOC.get("market_overview")
    assert mo and mo["status"] == "ok" and mo["source"] in ("llm", "session") and mo["view"]["headline"]
    assert mo["as_of"] == DOC["snapshot"]["as_of"]
