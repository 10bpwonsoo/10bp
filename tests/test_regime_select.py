"""
MARKET REGIME v2 — 주식 투자자 관점의 regime 선택(2026-11-04). 요청서 31 의 case A–J.

자격(require) · 후보 · 미국/한국/Global 주식 확인 · 데이터 없음 EXCLUDED · LLM 출력 검증 · 정량 대체 선택을 실제 규칙(state_rules.yaml)
위에서 본다. LLM 이 어떤 regime 을 고를지는 LLM 의 몫이라 여기서는 (1) 그 판단에 필요한 증거가 컨텍스트에 정확히 들어가는지,
(2) 자격 없는 선택 · 금지어를 막는지, (3) LLM 이 없을 때 같은 증거로 하는 정량 선택이 요청서의 기대와 맞는지를 확인한다.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from marketpulse.config.registry import get_instruments
from marketpulse.engines import regime_select as R
from marketpulse.engines.market_state import evaluate_hypotheses
from marketpulse.models.common import ScoreBreakdown
from marketpulse.models.state import FactorScore, StateLabel

BY_ID = get_instruments().by_id()
FACTORS0 = {"Growth": 0.0, "Inflation": 0.0, "Rates": 0.0, "USD": 0.0, "Liquidity": 0.0, "RiskAppetite": 0.0, "Credit": 0.0, "Volatility": 0.0, "China": 0.0}


class FakeMarket:
    def __init__(self, z1: dict, z5: dict | None = None):
        self.z1, self.z5, self.features = z1, (z5 or {}), {k: None for k in z1}
        self.coverage = 0.9

    def z(self, iid, horizon="1d"):
        return (self.z1 if horizon == "1d" else self.z5).get(iid)


def kr_stocks(up: float, n: int = 30, big_up: bool = False) -> dict:
    """n 개 대표 종목. up = 상승 종목 비율. big_up=True 면 삼성전자 · SK하이닉스만 크게 오른다."""
    secs = ["auto", "chemicals", "steel", "electrical", "shipbuilding", "financials", "battery", "internet", "healthcare", "utilities", "defense", "energy"]
    out = {}
    k_up = int(round(up * n))
    for i in range(n):
        z = 1.2 if i < k_up else -1.2
        out[f"S{i}"] = {"z_1d": z, "z_5d": z / 2, "ret_1d": 1.5 if z > 0 else -1.5, "sector": secs[i % len(secs)]}
    if big_up:
        out["SAMSUNG"] = {"z_1d": 2.5, "z_5d": 1.0, "ret_1d": 4.0, "sector": "semiconductor"}
        out["SKHYNIX"] = {"z_1d": 2.5, "z_5d": 1.0, "ret_1d": 5.0, "sector": "semiconductor"}
    return out


def ctx_for(factors: dict, z1: dict, kr: dict, z_extra: dict | None = None):
    f = {**FACTORS0, **factors}
    fs = {k: FactorScore(factor=k, score=v, breakdown=ScoreBreakdown.build(value=v, method="test", contributions=[])) for k, v in f.items()}
    z = {**z1, **(z_extra or {})}
    market = FakeMarket(z, {k: v / 2 for k, v in z.items()})
    hyps = evaluate_hypotheses(fs, market)  # type: ignore[arg-type]
    ms = SimpleNamespace(factors=fs, hypotheses=hyps, primary_label=StateLabel.NEUTRAL)
    inp = R.EquityInputs(z, market.z5, kr)
    return R.build_context(ms, market, BY_ID, inp, official="NEUTRAL")


def cand(ctx, label):
    return next((c for c in ctx["candidates"] if c["label"] == label), None)


US_UP = {"SPX": 1.6, "NDX": 1.8, "RUT": 2.0, "CYC_DEF": 1.2, "SOXX": 1.6, "VIX": -1.5, "US_HY_OAS": -1.0, "XLU": 0.2, "XLF": 1.5, "XLY": 1.6, "XLE": 0.5, "XLK": 1.7}
US_DOWN = {"SPX": -1.6, "NDX": -1.8, "RUT": -2.2, "CYC_DEF": -1.2, "SOXX": -1.8, "VIX": 2.0, "US_HY_OAS": 1.5, "XLU": 0.6, "XLF": -2.4, "XLY": -2.0, "XLE": -1.0, "XLK": -1.9}
KR_UP = {"KOSPI": 1.5, "KOSDAQ": 1.9}
KR_DOWN = {"KOSPI": -1.5, "KOSDAQ": -2.2}


def test_A_broad_risk_on_high_confidence():
    ctx = ctx_for({"RiskAppetite": 1.2, "Volatility": -0.5, "Growth": 0.4, "Credit": -0.4}, {**US_UP, **KR_UP}, kr_stocks(0.85))
    c = cand(ctx, "RISK_ON")
    assert c is not None and c["equity"]["us"]["status"] in ("STRONG", "CONFIRMED") and c["equity"]["kr"]["status"] in ("STRONG", "CONFIRMED")
    q = R.quant_select(ctx)
    assert q["selected_regime"] == "RISK_ON" and q["regime_confidence"] >= 65


def test_B_risk_on_with_weak_breadth_and_vix_up_is_lower():
    a = ctx_for({"RiskAppetite": 1.2, "Volatility": -0.5, "Growth": 0.4, "Credit": -0.4}, {**US_UP, **KR_UP}, kr_stocks(0.85))
    weak_us = {**US_UP, "RUT": -1.2, "VIX": 1.2, "CYC_DEF": -0.5}
    b = ctx_for({"RiskAppetite": 1.2, "Volatility": 0.6}, {**weak_us, "KOSPI": 0.8, "KOSDAQ": -1.0}, kr_stocks(0.25))
    ca, cb = cand(a, "RISK_ON"), cand(b, "RISK_ON")
    assert cb is not None, "Trigger 는 그대로 넘었으니 후보다"
    assert cb["equity"]["global"]["score"] < ca["equity"]["global"]["score"] and cb["quant_confidence"] < ca["quant_confidence"]
    assert R.quant_select(b)["selected_regime"] in ("RISK_ON", "NEUTRAL")


def test_C_liquidity_and_risk_off_both_candidates_stress_spread_to_banks():
    z = {**US_DOWN, **KR_DOWN, "MOVE": 2.5}
    kr = kr_stocks(0.15); kr.update({"KB": {"z_1d": -3.0, "z_5d": -1.5, "ret_1d": -6.0, "sector": "financials"}, "SHINHAN": {"z_1d": -3.0, "z_5d": -1.5, "ret_1d": -6.0, "sector": "financials"}})
    ctx = ctx_for({"RiskAppetite": -1.2, "Liquidity": -1.8, "Credit": 1.6, "Volatility": 1.4}, z, kr)
    ls, ro = cand(ctx, "LIQUIDITY_STRESS"), cand(ctx, "RISK_OFF")
    assert ls is not None and ro is not None, "둘 다 자격이 있다 — 하나를 고정 우선순위로 고르지 않는다"
    assert ls["equity"]["global"]["status"] in ("STRONG", "CONFIRMED") and ls["support_ratio"] >= 0.6
    assert {c["label"] for c in ctx["candidates"]} >= {"LIQUIDITY_STRESS", "RISK_OFF"}  # LLM 이 둘을 함께 받는다


def test_D_broad_weakness_with_mild_credit_favours_risk_off():
    ctx = ctx_for({"RiskAppetite": -1.5, "Liquidity": -1.1, "Credit": 0.3, "Volatility": 1.4, "USD": 0.6}, {**US_DOWN, **KR_DOWN, "XLF": -1.4, "MOVE": 0.4}, kr_stocks(0.15))
    ls, ro = cand(ctx, "LIQUIDITY_STRESS"), cand(ctx, "RISK_OFF")
    assert ls is not None and ro is not None
    assert ls["support_ratio"] < ro["support_ratio"], "신용 확인이 약하다 — Liquidity 보조 조건이 덜 찬다"
    assert ro["quant_confidence"] > ls["quant_confidence"]


def test_E_inflation_shock_confirmed_by_growth_weakness():
    # 유가도 올라 GEOPOLITICAL 자격도 생기지만 방산 · 항공 · 금으로 번지지 않는다 — 물가 · 금리가 주식 valuation 을 누르는 날
    z = {**US_DOWN, "NDX": -2.2, "SPX": -1.0, "XLE": 1.5, "SOXX": -2.0, "BRENT": 2.0, "WTI": 2.0, "BE10Y": 1.8, "US10Y": 1.5, "ITA": -1.0, "JETS": -0.9, "GOLD": 0.0, **KR_DOWN}
    kr = kr_stocks(0.3); kr.update({"LG_ENSOL": {"z_1d": -2.8, "z_5d": -1.0, "ret_1d": -5.0, "sector": "battery"}, "SOIL": {"z_1d": 1.8, "z_5d": 1.0, "ret_1d": 3.0, "sector": "energy"}})
    ctx = ctx_for({"Inflation": 1.3, "Rates": 1.0, "RiskAppetite": -0.6, "Growth": -0.2, "Volatility": 0.6}, z, kr)
    c = cand(ctx, "INFLATION_SHOCK")
    assert c is not None and c["equity"]["global"]["status"] in ("STRONG", "CONFIRMED")
    geo = cand(ctx, "GEOPOLITICAL_RISK")
    assert geo is not None and geo["quant_confidence"] < c["quant_confidence"], "유가만 오른 지정학 후보는 확산 확인이 약하다"
    assert R.quant_select(ctx)["selected_regime"] == "INFLATION_SHOCK"


def test_F_inflation_trigger_but_equities_strong_is_contradicted_and_low_confidence():
    e = ctx_for({"Inflation": 1.3, "Rates": 1.0, "RiskAppetite": -0.6, "Volatility": 0.6}, {**US_DOWN, "NDX": -2.2, "XLE": 1.5, **KR_DOWN}, kr_stocks(0.3))
    f = ctx_for({"Inflation": 1.3, "Rates": 0.3}, {**US_UP, "XLE": -0.5, **KR_UP}, kr_stocks(0.85))
    cf = cand(f, "INFLATION_SHOCK")
    assert cf is not None and cf["equity"]["global"]["status"] == "CONTRADICTED"
    assert cf["quant_confidence"] < cand(e, "INFLATION_SHOCK")["quant_confidence"]
    q = R.quant_select(f)
    assert q["selected_regime"] != "INFLATION_SHOCK" or q["regime_confidence"] < 50


def test_G_growth_shock_with_cyclical_weakness():
    z = {**US_DOWN, "SPX": -1.2, "XLU": 1.0, "US10Y": -1.6, **KR_DOWN}
    kr = kr_stocks(0.2)
    for i, s in enumerate(("auto", "chemicals", "steel", "electrical")):
        kr[f"C{i}"] = {"z_1d": -3.0, "z_5d": -1.5, "ret_1d": -4.0, "sector": s}
    ctx = ctx_for({"Growth": -1.4, "RiskAppetite": -0.6, "Rates": -0.5, "China": -0.4, "Volatility": 0.6}, z, kr)
    c = cand(ctx, "GROWTH_SHOCK")
    assert c is not None and c["equity"]["global"]["status"] in ("STRONG", "CONFIRMED")
    sel = R.quant_select(ctx)["selected_regime"]
    assert sel in {x["label"] for x in ctx["candidates"]}
    assert cand(ctx, "GROWTH_SHOCK")["quant_confidence"] >= 55


def test_H_missing_korea_flow_and_breadth_are_excluded_not_penalised():
    base = {"RiskAppetite": 1.2, "Volatility": -0.5, "Growth": 0.4, "Credit": -0.4}
    with_flow = ctx_for({**base, "KoreaFlow": 0.5}, {**US_UP, **KR_UP}, kr_stocks(0.85))
    no_flow = ctx_for(base, {**US_UP, **KR_UP}, kr_stocks(0.85))
    a, b = cand(with_flow, "RISK_ON"), cand(no_flow, "RISK_ON")
    flow = next(s for s in b["support"] if "KoreaFlow" in s["expr"])
    assert flow["passed"] is None, "데이터 없음 = 평가 안 함(None) — 실패가 아니다"
    assert b["support_ratio"] == pytest.approx(a["support_ratio"]) or b["support_ratio"] >= a["support_ratio"] - 1e-9
    # 주식 신호: 없는 breadth 는 EXCLUDED, 점수에서 빠진다(나머지 평균 그대로)
    sig = {s["key"]: s for s in b["equity"]["kr"]["signals"]}
    assert sig["breadth_kospi"]["state"] == "EXCLUDED" and sig["breadth_kospi"]["score"] is None
    assert "KOSPI 상승종목 비율" in no_flow["excluded"]


def test_I_kospi_up_on_two_megacaps_with_weak_breadth_is_not_broad_risk_on():
    kr = kr_stocks(0.2, big_up=True)
    ctx = ctx_for({"RiskAppetite": 1.0}, {**US_UP, "KOSPI": 1.4, "KOSDAQ": -1.0}, kr)
    k = cand(ctx, "RISK_ON")["equity"]["kr"]
    assert k["status"] not in ("STRONG", "CONFIRMED"), k
    sig = {s["key"]: s for s in k["signals"]}
    assert sig["broad_kr"]["score"] < 0 and sig["breadth_kr"]["score"] < 0


def test_J_us_strong_korea_weak_is_mixed_globally():
    ctx = ctx_for({"RiskAppetite": 1.2, "Volatility": -0.5}, {**US_UP, **KR_DOWN}, kr_stocks(0.15))
    e = cand(ctx, "RISK_ON")["equity"]
    assert e["us"]["status"] in ("STRONG", "CONFIRMED") and e["kr"]["status"] == "CONTRADICTED" and e["global"]["status"] == "MIXED"


def test_no_eligible_candidate_selects_neutral_and_never_invents_regime():
    ctx = ctx_for({"RiskAppetite": 0.4, "Growth": -0.6}, {**US_UP, **KR_DOWN}, kr_stocks(0.3))
    assert ctx["candidates"] == []
    q = R.quant_select(ctx)
    assert q["selected_regime"] == "NEUTRAL" and q["selection_status"] == "NO_ELIGIBLE"
    good = {"selected_regime": "NEUTRAL", "regime_confidence": 55, "selection_status": "NO_ELIGIBLE", "primary_reason": "어느 Trigger 도 넘지 않았다.",
            "alternative_candidates": [], "us_equity_confirmation": "PARTIAL", "korea_equity_confirmation": "PARTIAL", "global_equity_confirmation": "PARTIAL",
            "persistence_assessment": "공식 regime 유지", "data_coverage": 80, "selection_rationale": "후보가 없다.",
            "commentary": "어느 regime 도 주요 Trigger 를 넘지 않았다. 미국은 강하지만 한국이 약해 하나의 환경으로 정하기 어렵다."}
    assert R.check_output(good, ctx) == []
    bad = {**good, "selected_regime": "RISK_ON"}
    assert any("자격 없는" in p for p in R.check_output(bad, ctx))
    banned = {**good, "commentary": "지금은 매수 구간이다. 위험선호가 강하다."}
    assert any("금지어" in p for p in R.check_output(banned, ctx))


def test_llm_path_validates_then_falls_back_to_quant():
    ctx = ctx_for({"RiskAppetite": 1.2, "Volatility": -0.5, "Growth": 0.4, "Credit": -0.4}, {**US_UP, **KR_UP}, kr_stocks(0.85))

    class Stub:
        enabled = True
        def __init__(self, out): self.out = out
        def interpret(self, **_k): return self.out

    ok = {"selected_regime": "RISK-ON", "regime_confidence": 81, "selection_status": "CONFIRMED", "primary_reason": "미국과 한국 주식이 함께 강하다.",
          "alternative_candidates": [], "us_equity_confirmation": "STRONG", "korea_equity_confirmation": "STRONG", "global_equity_confirmation": "STRONG",
          "persistence_assessment": "전환 후보 1/2", "data_coverage": 0, "selection_rationale": "광범위한 강세.",
          "commentary": "미국과 한국에서 지수와 대표 종목이 함께 올랐다. 변동성과 신용 부담도 줄었다."}
    s = R.select_regime(ctx, client=Stub(ok))
    assert s.source == "llm" and s.selected_regime == "RISK_ON" and s.regime_confidence == 81
    assert s.data_coverage == ctx["data_coverage"], "coverage 는 엔진 값"
    s2 = R.select_regime(ctx, client=Stub({**ok, "selected_regime": "GROWTH_SHOCK"}))
    assert s2.source == "quant" and s2.selected_regime in ("RISK_ON", "NEUTRAL") and s2.warnings
    s3 = R.select_regime(ctx, session_read=ok)
    assert s3.source == "session"
