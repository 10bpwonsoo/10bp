"""금리 탭 MARKET READ(2026-10-13) — LLM 해석의 컨텍스트 · 검증 · 폴백. 네트워크 없이 가짜 클라이언트로 돈다."""
from __future__ import annotations


import pytest

from marketpulse.ai.client import LLMFailure
from marketpulse.ai.rates_read import (
    SCHEMA, SYSTEM_PROMPT, apply_read, attach_market_read, build_context, check_output, generate_market_read, normalize_output, number_check, validate_read,
)
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.rates_regime import build_rates_regime
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.engines.normalize import build_snapshot

from tests.conftest import AS_OF


@pytest.fixture(scope="module")
def world():
    settings = Settings(data_mode="MOCK", scenario="inflation_shock", llm_enabled=False)
    r = run_pipeline_detailed(settings, as_of=AS_OF)
    ins = get_instruments().instruments
    market = build_snapshot(ins, r.series_by_id, mode=r.snapshot.mode, as_of=AS_OF, zscore_window=settings.zscore_window, correlations=False)
    regime = build_rates_regime(market, r.snapshot.themes, {i.id: i for i in ins})
    kinds = {i.id: i.series_kind for i in ins}
    ctx = build_context(regime, market, r.series_by_id, news=r.snapshot.events, instrument_kinds=kinds, as_of=AS_OF)
    return {"regime": regime, "market": market, "series": r.series_by_id, "events": r.snapshot.events, "kinds": kinds, "ctx": ctx}


class FakeClient:
    """interpret() 응답을 차례로 돌려준다. 호출 기록을 남긴다."""

    def __init__(self, *responses, enabled: bool = True, last_error: str | None = None):
        self.responses = list(responses)
        self.enabled = enabled
        self.last_error = last_error
        self.calls: list[dict] = []

    def interpret(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


def _good(ctx) -> dict:
    lvl = next(r for r in ctx["cross_asset"] if r["id"] == "SPX")
    return {"read": f"장기물이 이끈 금리 상승은 기대인플레가 같이 오른 쪽이라 물가 경로 재평가에 더 가깝다. 주식은 S&P 500 기준 {abs(lvl['chg_1d']):.1f}% 움직여 밸류에이션 부담이 확인되는 중이다. "
                    "위험자산에는 선별적인 환경으로 읽힌다.",
            "move_quality": "inflation_shock", "themes": ["inflation", "fed"], "regime_fit": "consistent", "data_caveat": ""}


class TestContext:
    def test_sections_and_status(self, world):
        ctx = world["ctx"]
        assert set(ctx) >= {"rates", "regime_model", "macro", "cross_asset", "headlines", "data_status", "displayed_elsewhere"}
        ids = [r["id"] for r in ctx["rates"]["tenors"]]
        assert ids == ["US2Y", "US5Y", "US10Y", "US30Y"]
        for r in ctx["rates"]["tenors"] + ctx["cross_asset"]:
            assert r["status"] in ("OK", "STALE", "MISSING")
            if r["status"] == "MISSING":
                assert "chg_1d" not in r or r["chg_1d"] is None  # 결측은 0 이 아니다
        assert set(ctx["rates"]["curve"]) == {"2s10s", "5s30s"}
        # 기간 프리미엄은 엔진 점수 proxy 로만, 그렇다고 적혀 있다
        assert "직접 추정치가 아니다" in ctx["rates"]["term_premium_proxy"]["note"]
        # 화면에 이미 보이는 숫자 — 10년물 수준
        assert round(world["regime"].rate_move.level, 2) in ctx["displayed_elsewhere"]["numbers"]

    def test_mock_has_no_policy_file(self, world):
        assert world["regime"].events is None and "note" in world["ctx"]["macro"]

    def test_level_series_change_in_bp(self, world):
        r = next(x for x in world["ctx"]["rates"]["tenors"] if x["id"] == "US10Y")
        assert r["chg_unit"] == "bp"
        spx = next(x for x in world["ctx"]["cross_asset"] if x["id"] == "SPX")
        assert spx["chg_unit"] == "%"


class TestValidate:
    def test_good_read_passes(self, world):
        out = normalize_output(_good(world["ctx"]))
        assert check_output(out, world["ctx"]) == []

    @pytest.mark.parametrize("text,needle", [
        ("금리가 내렸다.", "문장 수"),
        ("금리 상승은 물가 쪽에 가깝다. 지금은 매수 기회로 읽힌다.", "직접 추천"),
        ("금리 상승은 물가 쪽에 가깝다. 상승 확률이 높다.", "직접 추천"),
        ("금리 하락의 주된 원인은 기간 프리미엄입니다. 시장을 계속 모니터링해야 합니다.", "상투 문구"),
        ("금리 상승은 물가 때문입니다. 위험자산에는 부담이다.", "인과 단정"),
        ("10년물이 987.65bp 움직였다. 위험자산에는 부담이다.", "컨텍스트에 없는 숫자"),
        ("금리는 1, 2, 3, 4 단계로 움직였다. 위험자산에는 부담이다.", "숫자 4개"),
    ])
    def test_rejects(self, world, text, needle):
        assert any(needle in p for p in validate_read(text, world["ctx"])), validate_read(text, world["ctx"])

    def test_tenor_names_and_dates_are_not_numbers(self, world):
        n, invented, _ = number_check("10년물과 2s10s, 30Y, S&P 500 은 숫자로 세지 않는다.", world["ctx"])
        assert n == 0 and invented == []

    def test_displayed_level_repeat_rejected(self, world):
        lvl = round(world["regime"].rate_move.level, 2)
        probs = validate_read(f"10년물이 {lvl:.2f}% 에 있다. 위험자산에는 부담이다.", world["ctx"])
        assert any("이미 보이는 숫자" in p for p in probs)

    def test_rounding_allowed(self, world):
        lvl = world["regime"].rate_move.level
        _n, invented, _ = number_check(f"10년물은 {lvl:.1f}% 부근이다.", world["ctx"])
        assert invented == []


class TestGenerate:
    def test_ok_first_try(self, world):
        c = FakeClient(_good(world["ctx"]))
        out, warns, reason = generate_market_read(c, world["ctx"])
        assert out and not warns and reason == ""
        kw = c.calls[0]
        assert kw["schema"] is SCHEMA and kw["system"] is SYSTEM_PROMPT and kw["effort"] == "high"
        assert "MARKET READ" in kw["user"] and '"cross_asset"' in kw["user"]

    def test_invalid_then_retry_ok(self, world):
        bad = {**_good(world["ctx"]), "read": "금리 상승은 물가 때문입니다. 지금은 매수할 때다."}
        c = FakeClient(bad, _good(world["ctx"]))
        out, warns, reason = generate_market_read(c, world["ctx"])
        assert out is not None and len(c.calls) == 2 and warns and "이전 답안" in c.calls[1]["user"]

    def test_invalid_twice_falls_back(self, world):
        bad = {**_good(world["ctx"]), "read": "금리 상승 확률이 높다."}
        c = FakeClient(bad, bad)
        out, warns, reason = generate_market_read(c, world["ctx"])
        assert out is None and len(warns) == 2 and "검증" in reason

    def test_api_failure_reason_without_secrets(self, world):
        c = FakeClient(LLMFailure("400: credit balance is too low", "api"), last_error="API 400: Your credit balance is too low")
        out, _w, reason = generate_market_read(c, world["ctx"])
        assert out is None and "크레딧 부족" in reason and "400" not in reason


class TestAttach:
    def test_llm_ok_sets_meta_and_keeps_rule(self, world):
        r0 = world["regime"]
        r, ctx = attach_market_read(r0, client=FakeClient(_good(world["ctx"])), market=world["market"], series=world["series"], news=world["events"],
                                    instrument_kinds=world["kinds"], as_of=AS_OF)
        m = r.top.market_read_meta
        assert m.source == "llm" and m.status == "ok" and m.generator == "api" and m.themes == ["inflation", "fed"] and m.themes_ko == ["물가", "Fed 경로"]
        assert m.rule_read == r0.top.market_read and r.top.market_read != r0.top.market_read
        # 정량 값은 그대로 — 해석만 붙는다
        assert r.model_dump(exclude={"top"}) == r0.model_dump(exclude={"top"}) and ctx

    def test_disabled_client_falls_back_to_rule(self, world):
        r0 = world["regime"]
        r, _ = attach_market_read(r0, client=FakeClient(enabled=False), market=world["market"], series=world["series"], instrument_kinds=world["kinds"], as_of=AS_OF)
        m = r.top.market_read_meta
        assert m.source == "rule" and m.status == "fallback" and r.top.market_read == r0.top.market_read and "비활성" in m.reason

    def test_session_read_used_only_if_valid(self, world):
        r0 = world["regime"]
        fail = LLMFailure("x", "api")
        r, _ = attach_market_read(r0, client=FakeClient(fail), market=world["market"], series=world["series"], instrument_kinds=world["kinds"], as_of=AS_OF,
                                  session_read=_good(world["ctx"]))
        m = r.top.market_read_meta
        assert m.source == "llm" and m.generator == "session" and "API 호출 실패" in m.reason
        r2, _ = attach_market_read(r0, client=FakeClient(fail), market=world["market"], series=world["series"], instrument_kinds=world["kinds"], as_of=AS_OF,
                                   session_read={**_good(world["ctx"]), "read": "매수."})
        assert r2.top.market_read_meta.source == "rule" and any("세션 생성본 검증 실패" in w for w in r2.top.market_read_meta.warnings)

    def test_apply_read_idempotent_rule(self, world):
        r1 = apply_read(world["regime"], out=None, status="pending", reason="생성 중")
        r2 = apply_read(r1, out=None, status="fallback", reason="x")
        assert r2.top.market_read_meta.rule_read == world["regime"].top.market_read == r2.top.market_read


class TestApi:
    def test_mock_market_read_is_rule_skipped(self, client):
        body = client.get("/api/v1/rates-regime?scenario=inflation_shock").json()
        m = body["top"]["market_read_meta"]
        assert m["source"] == "rule" and m["status"] == "skipped" and body["top"]["market_read"] == m["rule_read"]


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from marketpulse.api.deps import get_investment_service, get_rates_regime_service, get_scenario_check_service, get_service, get_state_history_service
    from marketpulse.api.main import create_app
    for svc in (get_service(), get_state_history_service(), get_investment_service(), get_scenario_check_service(), get_rates_regime_service()):
        svc.clear()
    with TestClient(create_app()) as c:
        yield c
