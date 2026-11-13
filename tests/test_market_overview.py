"""MARKET OVERVIEW (2026-11-12, 11/13 상태 요약 추가) — 기존 섹션만 읽는 LLM 종합: 구조 고정 · 검증 · 결측 · 지난 일정 금지 · 매매 지시 금지 · 저장/캐시."""
import json
from pathlib import Path

from marketpulse.ai import market_overview as MO

ROOT = Path(__file__).resolve().parents[1]
DOC = json.loads((ROOT / "marketpulse/data/archive/2026/11/2026-11-13.json").read_text(encoding="utf-8"))
SESSION = {k: v for k, v in json.loads((ROOT / "marketpulse/data/captures/2026-11-13-backfill/market_overview_session.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}


def test_context_reads_existing_sections_only():
    c = MO.build_context(DOC)
    assert c["snapshot_date"] == "2026-11-13"
    assert c["market_regime"]["official"] == "NEUTRAL / MIXED" and c["market_regime"]["candidate"] == "Policy Driven"
    assert c["rates"]["regime"] and c["oil"]["regime"] and c["ai_theme"]["regime"] and c["semiconductor_cycle"]["regime"]
    assert all(u["date"] >= "2026-11-13" for u in c["upcoming_events"])  # 지난 일정은 catalyst 후보가 아니다
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
    bad = json.loads(json.dumps(SESSION)); bad["state_summary"] = "정책 주도 전환 시도가 이어지고 있지만 미국과 한국 주식 확인은 아직 제한적인 상태입니다."
    assert any("state_summary" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["regime_read"] = "공식은 중립입니다. 후보는 정책 주도입니다. 주식 확인은 부분적입니다."
    assert any("regime_read" in p for p in MO.check(bad, c))


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
    tick = json.loads(json.dumps(DOC)); tick["snapshot"]["as_of"] = "2026-11-12T23:00:00Z"
    b = MO.live_overview(tick, client=Fake())
    assert a["status"] == "ok" and b["view"] == a["view"] and len(calls) == 1
    moved = json.loads(json.dumps(DOC)); moved["cockpit"]["market_now"]["state"]["candidate_label"] = "Neutral / Mixed"
    MO.live_overview(moved, client=Fake())
    assert len(calls) == 2


def test_archive_section_stored():
    mo = DOC.get("market_overview")
    assert mo and mo["status"] == "ok" and mo["source"] in ("llm", "session") and mo["view"]["headline"]
    assert mo["as_of"] == DOC["snapshot"]["as_of"]


def test_equity_terms_words_from_existing_signals():
    """EQUITY MARKET 재구성(2026-11-13) — 기존 neutral_equity 신호값을 단어로만 옮긴다. 없는 신호는 UNAVAILABLE."""
    t = MO.build_context(DOC)["equity_terms"]
    assert t["us"]["trend"] == "POSITIVE" and t["us"]["breadth"] == "UNAVAILABLE" and t["us"]["style"][0] == "LARGE > SMALL"
    assert t["korea"]["trend"] == "NEUTRAL" and t["korea"]["breadth"] == "WEAK" and t["korea"]["participation_pct"] == 31
    assert t["us"]["confirmation"] == "PARTIAL" and t["korea"]["confirmation"] == "PARTIAL"
    assert MO._breadth_ratio_word(0.7) == "BROAD" and MO._breadth_ratio_word(0.4) == "NARROW" and MO._breadth_z_word(None) == "UNAVAILABLE"
    assert MO._rel_word(0.1, "SMALL", "LARGE") == "SMALL ≈ LARGE" and MO._rel_word(-0.6, "SMALL", "LARGE") == "LARGE > SMALL"


def test_korea_sector_moves_from_representative_stocks():
    ks = MO.korea_sector_moves(DOC["investment"])
    assert ks and ks[0]["avg_ret_5d_pct"] >= ks[-1]["avg_ret_5d_pct"]
    assert {"Semiconductor", "Shipbuilding"} <= {k["sector"] for k in ks}
    assert sum(k["stocks"] for k in ks) == 36
    assert MO.korea_sector_moves(None) == []


def test_equity_view_structure_checked():
    c = MO.build_context(DOC)
    assert SESSION["equity_view"]["us"]["leadership"] and SESSION["equity_view"]["global_read"]
    bad = json.loads(json.dumps(SESSION)); bad["equity_view"]["korea"]["leadership"] = ["Biotech"]
    assert any("leadership" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["equity_view"]["us"]["headline"] = "반도체가 이끄는 대형 성장주 중심의 반등이 이어지지만 소형주는 소외되고 있다"
    assert any("us.headline" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["equity_view"]["divergence_label"] = "MIXED"
    assert any("divergence_label" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["equity_view"]["global_read"] = "미국과 한국 모두 반등입니다."
    assert any("global_read" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["equity_view"]["korea"] = "한 줄 문자열"
    assert any("korea" in p for p in MO.check(bad, c))


def test_cross_asset_state_words_and_rates_directions():
    """RATES · CROSS-ASSET 재구성(2026-11-13) — z 와 bp 를 단어로만 옮긴다(계산 없음). Credit 은 스프레드라 내려가면 IMPROVING."""
    c = MO.build_context(DOC)
    st = {r["asset"]: r["state"] for r in c["cross_asset"]}
    assert st == {"Equity": "STRONG", "Rates": "RISING", "Credit": "IMPROVING", "Volatility": "CALMING", "USD": "STRONG", "Oil": "NEUTRAL", "Gold": "STABLE"}
    assert c["rates"]["real_yield_direction"] == "RISING" and c["rates"]["breakeven_direction"] == "FALLING"
    assert MO.ca_state("CREDIT", 2.0) == "STRESSED" and MO.ca_state("VOLATILITY", 0.7) == "RISING" and MO.ca_state("OIL", None) == "UNAVAILABLE"
    assert MO.bp_dir(0.4) == "FLAT" and MO.bp_dir(None) is None


def test_rates_and_cross_asset_view_structure_checked():
    c = MO.build_context(DOC)
    assert SESSION["rates_view"]["equity_impact"] in MO.EQUITY_IMPACT and SESSION["cross_asset_view"]["support"]
    bad = json.loads(json.dumps(SESSION)); bad["rates_view"] = "금리 상승은 성장주에 부담이다"
    assert any("객체" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["rates_view"]["equity_impact"] = "BEARISH"
    assert any("equity_impact" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["rates_view"]["headline"] = "연준 정책 경로 재평가가 실질금리와 단기금리를 함께 끌어올리면서 성장주 밸류에이션 부담이 커지고 있다"
    assert any("rates_view.headline" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["cross_asset_view"]["support"] = ["Credit", "Bitcoin"]
    assert any("Bitcoin" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["cross_asset_view"]["risk"] = ["Rates", "Credit"]
    assert any("같은 자산" in p for p in MO.check(bad, c))
    bad = json.loads(json.dumps(SESSION)); bad["cross_asset_view"]["support"] = []; bad["cross_asset_view"]["risk"] = ["Rates"]
    assert any("합쳐 2~5개" in p for p in MO.check(bad, c))
