"""데이터 계약 테스트 (설계서 STEP 4)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from marketpulse.config.registry import get_instruments, get_themes
from marketpulse.models.common import (
    DataMeta,
    DataMode,
    ScoreBreakdown,
    ScoreContribution,
    arrow_for,
    direction_for,
    utcnow,
)
from marketpulse.models.market import InstrumentRegistry
from marketpulse.models.news import NewsEvent
from marketpulse.models.theme import ThemeInstrument


def _contrib(key: str, z: float, w: float) -> ScoreContribution:
    return ScoreContribution(key=key, normalized=z, weight=w, contribution=z * w)


class TestScoreBreakdown:
    def test_hash_is_deterministic(self):
        a = ScoreBreakdown.hash_inputs({"BRENT": 2.1, "VIX": 1.3})
        b = ScoreBreakdown.hash_inputs({"VIX": 1.3, "BRENT": 2.1})
        assert a == b, "키 순서가 해시를 바꾸면 안 된다"

    def test_hash_changes_with_input(self):
        a = ScoreBreakdown.hash_inputs({"BRENT": 2.1})
        b = ScoreBreakdown.hash_inputs({"BRENT": 2.2})
        assert a != b

    def test_missing_is_not_zero(self):
        """결측과 0 은 다른 해시여야 한다. 0 으로 채우면 거짓 정보가 된다."""
        missing = ScoreBreakdown.hash_inputs({"BRENT": None})
        zero = ScoreBreakdown.hash_inputs({"BRENT": 0.0})
        assert missing != zero

    def test_build_records_contributions_and_missing(self):
        b = ScoreBreakdown.build(
            value=0.9,
            method="weighted_z_tanh_v1",
            contributions=[_contrib("BRENT", 2.1, 0.35), _contrib("WTI", 1.8, 0.25)],
            missing_inputs=["COPPER"],
        )
        assert [c.key for c in b.contributions] == ["BRENT", "WTI"]
        assert b.missing_inputs == ["COPPER"]
        assert b.inputs_hash

    def test_same_inputs_same_hash(self):
        args = dict(
            value=1.0,
            method="m",
            contributions=[_contrib("A", 1.0, 0.5)],
            missing_inputs=["B"],
        )
        assert ScoreBreakdown.build(**args).inputs_hash == ScoreBreakdown.build(**args).inputs_hash


class TestDataMeta:
    def test_freshness_and_staleness(self):
        now = utcnow()
        m = DataMeta(
            source="x", mode=DataMode.LIVE, retrieved_at=now,
            as_of=now - timedelta(minutes=10),
        )
        assert m.freshness_sec == pytest.approx(600, abs=2)
        assert m.is_stale, "LIVE 에서 10분 지연은 stale 이다"

    def test_delayed_tolerates_delay(self):
        now = utcnow()
        m = DataMeta(
            source="x", mode=DataMode.DELAYED, retrieved_at=now,
            as_of=now - timedelta(minutes=18),
        )
        assert not m.is_stale, "DELAYED 는 15~20분 지연을 정상으로 본다"

    def test_negative_freshness_clamped(self):
        now = utcnow()
        m = DataMeta(
            source="x", mode=DataMode.MOCK, retrieved_at=now,
            as_of=now + timedelta(minutes=5),
        )
        assert m.freshness_sec == 0

    def test_computed_fields_round_trip(self):
        """직렬화 후 다시 읽어들여도 실패하지 않아야 한다 (P2 storage)."""
        now = utcnow()
        m = DataMeta(source="x", mode=DataMode.MOCK, retrieved_at=now, as_of=now)
        assert DataMeta.model_validate(m.model_dump(mode="json")) == m


class TestArrows:
    @pytest.mark.parametrize(
        "z,expected", [(2.0, "↑↑"), (1.0, "↑"), (0.0, "→"), (-1.0, "↓"), (-2.0, "↓↓")]
    )
    def test_arrow(self, z, expected):
        assert arrow_for(z) == expected

    def test_deadband(self):
        assert direction_for(0.3) == "flat"
        assert direction_for(0.9) == "up"
        assert direction_for(-0.9) == "down"


class TestRegistries:
    def test_instruments_load(self, instruments):
        assert len(instruments) >= 40
        classes = {i.asset_class.value for i in instruments}
        # 요구 3 이 명시한 6개 카테고리가 모두 있어야 한다
        for required in ("equity", "rate", "fx", "commodity", "volatility", "flow", "breadth"):
            assert required in classes, f"{required} 자산군이 비어 있다"

    def test_rates_are_level_series(self, instruments_by_id):
        """금리를 로그수익률로 다루면 안 된다."""
        for iid in ("US2Y", "US10Y", "KR10Y", "BE10Y"):
            assert instruments_by_id[iid].series_kind == "level"
            assert instruments_by_id[iid].unit == "percent"

    def test_vix_is_not_risk_on(self, instruments_by_id):
        assert instruments_by_id["VIX"].higher_is_risk_on is False
        assert instruments_by_id["SPX"].higher_is_risk_on is True

    def test_duplicate_instrument_id_rejected(self):
        with pytest.raises(ValidationError):
            InstrumentRegistry.model_validate(
                {
                    "instruments": [
                        {"id": "X", "name": "a", "asset_class": "equity", "unit": "index"},
                        {"id": "X", "name": "b", "asset_class": "equity", "unit": "index"},
                    ]
                }
            )

    def test_themes_load_and_reference_real_instruments(self, themes, instruments_by_id):
        assert len(themes) >= 12, "요구 5 가 제시한 테마 수를 충족해야 한다"
        for t in themes:
            assert t.keywords, f"{t.id}: RuleExtractor 가 쓸 키워드가 없다"
            for ti in t.instruments:
                assert ti.instrument_id in instruments_by_id, (
                    f"{t.id} -> {ti.instrument_id} 가 레지스트리에 없다"
                )

    def test_theme_direction_must_be_signed(self):
        with pytest.raises(ValidationError):
            ThemeInstrument(instrument_id="X", direction=0)

    def test_inflation_theme_marks_growth_equity_inverse(self, themes):
        """인플레 테마에서 성장주는 역방향이어야 한다."""
        inflation = next(t for t in themes if t.id == "inflation")
        ndx = next(ti for ti in inflation.instruments if ti.instrument_id == "NDX")
        assert ndx.direction == -1


class TestNewsEvent:
    def test_sentiment_range_enforced(self):
        with pytest.raises(ValidationError):
            NewsEvent(id="e", event="x", sentiment=150, timestamp=utcnow())

    def test_extractor_provenance_defaults_to_rule(self):
        """LLM 산출과 룰 산출이 구분되어야 한다 (요구 15-11)."""
        e = NewsEvent(id="e", event="x", timestamp=utcnow())
        assert e.extractor == "rule"
        assert e.validation.schema_ok is True


class TestCollectionSafety:
    """
    upbit_trading/test_sql_load.py 가 절대 수집되지 않아야 한다.

    그 파일은 import 만으로 DB 를 만들고 외부 API 를 호출한다. 루트
    conftest.py 의 collect_ignore_glob 이 제거되면 이 테스트가 깨진다.
    """

    def test_upbit_trading_is_excluded(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        conftest = (root / "conftest.py").read_text(encoding="utf-8")
        assert "upbit_trading/*" in conftest, (
            "루트 conftest 의 collect_ignore_glob 에서 upbit_trading 이 빠졌다. "
            "test_sql_load.py 가 수집되면 실제 DB 를 생성하고 외부 API 를 호출한다."
        )

    def test_dangerous_script_still_looks_dangerous(self):
        """원본이 안전해졌다면 이 가드를 재검토하라는 신호로 둔다."""
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "upbit_trading" / "test_sql_load.py"
        if not path.exists():
            return
        body = path.read_text(encoding="utf-8", errors="replace")
        assert "CREATE DATABASE" in body
