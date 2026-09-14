"""
LLM 계층 테스트 (설계서 STEP 7.3 / 요구 14, 15-7).

네트워크를 쓰지 않는다. 고정 픽스처와 가짜 클라이언트로만 검증한다.
현재 환경에서는 마켓데이터 API 도 Anthropic API 도 실제 호출이 불가능하고,
가능하더라도 테스트가 외부 서비스에 의존하면 안 된다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from marketpulse.ai.client import (
    CIRCUIT_FAILURE_THRESHOLD,
    LLMClient,
    LLMFailure,
    build_client,
    reset_client_cache,
)
from marketpulse.ai.event_extractor import build_schema, extract_events as llm_extract
from marketpulse.ai.summarizer import (
    build_facts,
    extract_numbers,
    summarize,
    verify_numbers,
)
from marketpulse.ai.validation import validate_event
from marketpulse.config.settings import Settings
from marketpulse.engines.orchestrator import run_pipeline
from marketpulse.models.common import DataMeta, DataMode, utcnow
from marketpulse.models.news import RawNewsItem


@pytest.fixture(autouse=True)
def _clean_client_cache():
    reset_client_cache()
    yield
    reset_client_cache()


def _item(item_id: str = "n1", title: str = "유가 급등", as_of=None) -> RawNewsItem:
    when = as_of or datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)
    return RawNewsItem(
        id=item_id,
        title=title,
        body="본문",
        published_at=when,
        publisher="Test Wire",
        meta=DataMeta(source="t", mode=DataMode.MOCK, retrieved_at=utcnow(), as_of=when),
    )


class FakeClient(LLMClient):
    """네트워크 없이 응답을 주는 대역. 실패 시나리오도 흉내 낸다."""

    def __init__(self, responses, *, enabled: bool = True):
        super().__init__(enabled=enabled, model="fake-model")
        self._responses = list(responses)
        self.calls: list[dict] = []

    def structured(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            return LLMFailure("응답 없음", "api")
        return self._responses.pop(0)


# ──────────────────────────────────────────────────────────
# 요구 15-7 — LLM 이 죽어도 정량 대시보드는 동작한다
# ──────────────────────────────────────────────────────────
class TestAutoEnable:
    """키가 있으면 켜지고, 없으면 꺼진다. 명시 설정이 있으면 그것이 이긴다."""

    def test_key_turns_llm_on(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("MARKETPULSE_LLM_ENABLED", raising=False)
        assert Settings().llm_enabled is True

    def test_no_key_leaves_it_off(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("MARKETPULSE_LLM_ENABLED", raising=False)
        assert Settings().llm_enabled is False

    def test_explicit_setting_wins(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("MARKETPULSE_LLM_ENABLED", "false")
        assert Settings().llm_enabled is False


class TestGracefulDegradation:
    def test_disabled_pipeline_is_complete(self):
        snap = run_pipeline(Settings(scenario="inflation_shock", llm_enabled=False))
        assert snap.data_health.llm_status == "disabled"
        assert snap.market_state.primary_label.value == "INFLATION_SHOCK"
        assert snap.themes and snap.events and snap.impact_maps
        assert snap.market_state.narrative
        assert snap.market_state.narrative_source == "template"

    def test_enabled_without_credentials_still_works(self, monkeypatch):
        """
        키 없이 LLM 을 켜도 화면 전체가 동작해야 한다. 설계서 STEP 6.4 의
        완료 기준이다.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        snap = run_pipeline(Settings(scenario="inflation_shock", llm_enabled=True))
        assert snap.market_state.primary_label.value == "INFLATION_SHOCK"
        assert snap.themes and snap.events and snap.impact_maps
        assert all(e.extractor == "rule" for e in snap.events)
        assert snap.market_state.narrative_source == "template"
        assert snap.data_health.llm_status in ("failed", "degraded")

    def test_failure_reason_stays_visible(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        settings = Settings(scenario="baseline", llm_enabled=True)
        first = run_pipeline(settings)
        second = run_pipeline(settings, history=[first])
        # 첫 틱 이후 경고가 새로 생기지 않아도 이유는 남아야 한다
        assert any("LLM" in w for w in second.data_health.warnings)

    def test_quant_output_identical_with_llm_off_or_broken(self, monkeypatch):
        """LLM 유무가 정량 결과를 바꾸면 안 된다."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        off = run_pipeline(Settings(scenario="inflation_shock", llm_enabled=False))
        broken = run_pipeline(Settings(scenario="inflation_shock", llm_enabled=True))
        assert off.market_state.primary_label == broken.market_state.primary_label
        assert [t.theme_score for t in off.themes] == [
            t.theme_score for t in broken.themes
        ]


# ──────────────────────────────────────────────────────────
# 서킷 브레이커
# ──────────────────────────────────────────────────────────
class TestCircuitBreaker:
    def test_disabled_client_never_calls(self):
        c = LLMClient(enabled=False)
        assert c.structured(system="s", user="u", schema={}).kind == "disabled"
        assert c.status == "disabled"

    def test_opens_after_consecutive_failures(self):
        c = LLMClient(enabled=True)
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            c._circuit.record_failure()
        assert not c.available()
        assert c.status == "degraded"

    def test_success_resets(self):
        c = LLMClient(enabled=True)
        c._circuit.record_failure()
        c._circuit.record_success()
        assert c.available()
        assert c.status == "ok"

    def test_permanent_failure_never_reopens(self):
        c = LLMClient(enabled=True)
        c._circuit.record_failure(permanent=True)
        assert not c.available()
        assert c.status == "failed"

    def test_client_is_cached_so_circuit_survives_ticks(self):
        settings = Settings(llm_enabled=True)
        assert build_client(settings) is build_client(settings)


# ──────────────────────────────────────────────────────────
# 요구 14 — 구조화 출력 검증
# ──────────────────────────────────────────────────────────
class TestValidation:
    def _validate(self, raw, themes_by_id, instruments_by_id):
        return validate_event(
            raw,
            _item(),
            known_themes=themes_by_id,
            known_instruments=instruments_by_id,
            model="fake-model",
        )

    @pytest.fixture
    def themes_by_id(self, themes):
        return {t.id: t for t in themes}

    def test_out_of_range_values_are_clamped_and_recorded(
        self, themes_by_id, instruments_by_id
    ):
        event, report = self._validate(
            {"event": "x", "sentiment": 150, "impact_score": -20},
            themes_by_id,
            instruments_by_id,
        )
        assert event.sentiment == 100
        assert event.impact_score == 0
        # 조용히 고치지 않는다. 고쳤다는 사실이 남아야 한다.
        assert any("sentiment" in c for c in report.clamped_fields)
        assert any("impact_score" in c for c in report.clamped_fields)

    def test_unknown_theme_dropped(self, themes_by_id, instruments_by_id):
        event, report = self._validate(
            {"event": "x", "themes": ["oil", "quantum_computing"]},
            themes_by_id,
            instruments_by_id,
        )
        assert event.themes == ["oil"]
        assert any("quantum_computing" in e for e in report.errors)

    def test_theme_name_normalised(self, themes_by_id, instruments_by_id):
        event, _ = self._validate(
            {"event": "x", "themes": ["Geopolitical Risk"]},
            themes_by_id,
            instruments_by_id,
        )
        assert event.themes == ["geopolitical_risk"]

    def test_unknown_instrument_id_cleared_label_kept(
        self, themes_by_id, instruments_by_id
    ):
        """레지스트리에 없는 대상도 화면에는 보여야 한다."""
        event, report = self._validate(
            {
                "event": "x",
                "affected_assets": [
                    {"instrument_id": "FAKE99", "label": "가상종목", "direction": "up"}
                ],
            },
            themes_by_id,
            instruments_by_id,
        )
        asset = event.affected_assets[0]
        assert asset.instrument_id is None
        assert asset.label == "가상종목"
        assert any("FAKE99" in e for e in report.errors)

    def test_invalid_enum_falls_back(self, themes_by_id, instruments_by_id):
        event, report = self._validate(
            {"event": "x", "time_horizon": "forever"}, themes_by_id, instruments_by_id
        )
        assert event.time_horizon == "short"
        assert any("time_horizon" in e for e in report.errors)

    def test_provenance_recorded(self, themes_by_id, instruments_by_id):
        event, _ = self._validate({"event": "x"}, themes_by_id, instruments_by_id)
        assert event.extractor == "llm"
        assert event.extractor_model == "fake-model"

    def test_corrections_lower_confidence(self, themes_by_id, instruments_by_id):
        clean, _ = self._validate({"event": "x"}, themes_by_id, instruments_by_id)
        messy, _ = self._validate(
            {"event": "x", "sentiment": 900, "impact_score": -50, "time_horizon": "??"},
            themes_by_id,
            instruments_by_id,
        )
        assert messy.confidence < clean.confidence

    def test_unrecoverable_payload_returns_none(self, themes_by_id, instruments_by_id):
        raw = {"event": ""}
        item = _item(title="   ")
        event, report = validate_event(
            raw, item, known_themes=themes_by_id, known_instruments=instruments_by_id
        )
        assert event is None
        assert report.schema_ok is False


class TestExtractorSchema:
    def test_themes_are_an_enum(self, themes):
        schema = build_schema([t.id for t in themes])
        enum = schema["properties"]["events"]["items"]["properties"]["themes"]["items"]["enum"]
        assert set(enum) == {t.id for t in themes}

    def test_no_additional_properties(self, themes):
        schema = build_schema([t.id for t in themes])
        assert schema["additionalProperties"] is False
        assert schema["properties"]["events"]["items"]["additionalProperties"] is False


class TestExtractorFallback:
    def test_llm_result_is_used(self, themes, instruments_by_id):
        client = FakeClient(
            [
                {
                    "events": [
                        {
                            "source_id": "n1",
                            "event": "유가 급등",
                            "event_type": "geopolitical",
                            "themes": ["oil"],
                            "theme_sentiment": {"oil": 70},
                            "sentiment": 40,
                            "impact_score": 80,
                            "novelty_score": 60,
                            "time_horizon": "short",
                            "affected_assets": [],
                            "entities": [],
                            "reason": "테스트",
                        }
                    ]
                }
            ]
        )
        events, warnings = llm_extract(
            [_item()], client, {t.id: t for t in themes}, instruments_by_id
        )
        assert len(events) == 1
        assert events[0].extractor == "llm"
        assert events[0].themes == ["oil"]
        assert warnings == []

    def test_failure_falls_back_to_rules(self, themes, instruments_by_id):
        client = FakeClient([LLMFailure("타임아웃", "timeout")])
        events, warnings = llm_extract(
            [_item()], client, {t.id: t for t in themes}, instruments_by_id
        )
        assert len(events) == 1
        assert events[0].extractor == "rule"
        assert any("룰 추출기" in w for w in warnings)

    def test_partial_response_is_filled_with_rules(self, themes, instruments_by_id):
        """10건 중 1건만 오면 나머지 9건이 사라지면 안 된다."""
        items = [_item(f"n{i}") for i in range(3)]
        client = FakeClient(
            [
                {
                    "events": [
                        {
                            "source_id": "n0",
                            "event": "하나만",
                            "event_type": "macro",
                            "themes": [],
                            "theme_sentiment": {},
                            "sentiment": 0,
                            "impact_score": 10,
                            "novelty_score": 50,
                            "time_horizon": "short",
                            "affected_assets": [],
                            "entities": [],
                            "reason": "",
                        }
                    ]
                }
            ]
        )
        events, warnings = llm_extract(
            items, client, {t.id: t for t in themes}, instruments_by_id
        )
        assert len(events) == 3
        assert {e.extractor for e in events} == {"llm", "rule"}
        assert any("룰 추출기로 처리" in w for w in warnings)

    def test_unknown_source_id_is_discarded(self, themes, instruments_by_id):
        client = FakeClient([{"events": [{"source_id": "nope", "event": "x"}]}])
        events, warnings = llm_extract(
            [_item()], client, {t.id: t for t in themes}, instruments_by_id
        )
        assert events[0].extractor == "rule"
        assert any("source_id" in w for w in warnings)

    def test_unavailable_client_skips_the_call(self, themes, instruments_by_id):
        client = FakeClient([], enabled=False)
        events, _ = llm_extract(
            [_item()], client, {t.id: t for t in themes}, instruments_by_id
        )
        assert client.calls == []
        assert events[0].extractor == "rule"


# ──────────────────────────────────────────────────────────
# 요약 — 숫자 검증
# ──────────────────────────────────────────────────────────
class TestNumberVerification:
    def test_extracts_and_normalises(self):
        assert extract_numbers("+2.10σ 와 1,200 과 70%") == {"2.1", "1200", "70"}

    def test_quoted_numbers_pass(self):
        facts = "신뢰도: 70%\n  - 브렌트 원유 +2.10σ"
        assert verify_numbers("신뢰도 70% 이고 브렌트가 2.1σ 올랐다", facts) == []

    def test_invented_numbers_caught(self):
        facts = "신뢰도: 70%"
        assert verify_numbers("VIX 가 18.4 까지 올랐다", facts) == ["18.4"]

    def test_text_without_numbers_passes(self):
        assert verify_numbers("유가가 강하게 올랐다", "아무 사실") == []


class TestSummarizer:
    @pytest.fixture
    def snapshot(self):
        return run_pipeline(Settings(scenario="inflation_shock", llm_enabled=False))

    def test_facts_contain_the_judgement(self, snapshot):
        facts = build_facts(
            snapshot.market_state, snapshot.themes, snapshot.divergences
        )
        assert "INFLATION_SHOCK" in facts
        assert "신뢰도" in facts

    def test_llm_summary_used_when_grounded(self, snapshot):
        facts = build_facts(snapshot.market_state, snapshot.themes, snapshot.divergences)
        grounded = "물가 충격이 우세하다. 유가가 크게 올랐다."
        client = FakeClient([{"summary": grounded, "watch": "수급을 확인하라."}])
        text, source, warnings = summarize(
            snapshot.market_state,
            snapshot.themes,
            snapshot.divergences,
            client,
            fallback="템플릿",
        )
        assert source == "llm"
        assert grounded in text
        assert warnings == []
        assert facts  # 사실이 실제로 구성되었다

    def test_invented_number_reverts_to_template(self, snapshot):
        """
        지어낸 숫자가 화면에 오르는 것보다 덜 매끄러운 문장이 낫다.
        운용자는 그 숫자를 믿고 판단한다.
        """
        client = FakeClient(
            [{"summary": "VIX 가 987.65 까지 급등했다.", "watch": ""}]
        )
        text, source, warnings = summarize(
            snapshot.market_state,
            snapshot.themes,
            snapshot.divergences,
            client,
            fallback="템플릿 문장",
        )
        assert source == "template"
        assert text == "템플릿 문장"
        assert any("987.65" in w for w in warnings)

    def test_failure_reverts_to_template(self, snapshot):
        client = FakeClient([LLMFailure("한도 초과", "rate_limit")])
        text, source, warnings = summarize(
            snapshot.market_state,
            snapshot.themes,
            snapshot.divergences,
            client,
            fallback="템플릿 문장",
        )
        assert (text, source) == ("템플릿 문장", "template")
        assert any("rate_limit" in w for w in warnings)

    def test_disabled_client_skips_the_call(self, snapshot):
        client = FakeClient([], enabled=False)
        text, source, _ = summarize(
            snapshot.market_state,
            snapshot.themes,
            snapshot.divergences,
            client,
            fallback="템플릿 문장",
        )
        assert client.calls == []
        assert (text, source) == ("템플릿 문장", "template")

    def test_no_fallback_reports_none(self, snapshot):
        client = FakeClient([LLMFailure("x", "api")])
        text, source, _ = summarize(
            snapshot.market_state,
            snapshot.themes,
            snapshot.divergences,
            client,
            fallback=None,
        )
        assert text is None and source == "none"
