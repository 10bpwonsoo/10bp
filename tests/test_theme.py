"""ThemeEngine 테스트 (설계서 STEP 5.7)."""

from __future__ import annotations

import pytest

from marketpulse.adapters.market.mock import MockMarketAdapter
from marketpulse.adapters.news.mock import MockNewsAdapter
from marketpulse.ai.rule_extractor import extract_events
from marketpulse.config.settings import MOCK_DIR
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.scoring import load_scoring
from marketpulse.engines.theme import (
    compute_theme_states,
    cross_sectional_news_volume,
)
from marketpulse.models.common import DataMode
from marketpulse.models.theme import Confirmation, DataQualityBand


def _states(scenario, instruments, themes, instruments_by_id, as_of, **kwargs):
    series = MockMarketAdapter(MOCK_DIR, scenario).fetch_series(
        instruments, bars=180, as_of=as_of
    )
    snap = build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)
    events = extract_events(
        MockNewsAdapter(MOCK_DIR, scenario).fetch_news(as_of=as_of), as_of=as_of
    )
    return compute_theme_states(themes, snap, events, instruments_by_id, **kwargs)


@pytest.fixture
def quiet(instruments, themes, instruments_by_id, as_of):
    return _states("baseline", instruments, themes, instruments_by_id, as_of)


@pytest.fixture
def shock(instruments, themes, instruments_by_id, as_of):
    return _states("inflation_shock", instruments, themes, instruments_by_id, as_of)


class TestShape:
    def test_every_theme_scored(self, quiet, themes):
        assert {t.theme_id for t in quiet} == {t.id for t in themes}

    def test_sorted_by_score(self, quiet):
        scores = [t.theme_score for t in quiet]
        assert scores == sorted(scores, reverse=True)

    def test_scores_bounded(self, shock):
        assert all(-100.0 <= t.theme_score <= 100.0 for t in shock)

    def test_reproducible(self, instruments, themes, instruments_by_id, as_of):
        a = _states("inflation_shock", instruments, themes, instruments_by_id, as_of)
        b = _states("inflation_shock", instruments, themes, instruments_by_id, as_of)
        assert [t.breakdown.inputs_hash for t in a] == [
            t.breakdown.inputs_hash for t in b
        ]
        assert [t.theme_score for t in a] == [t.theme_score for t in b]


class TestWeighting:
    def test_not_a_simple_average(self):
        """요구 5 가 단순 평균을 금지한다. 구성요소 가중치가 서로 달라야 한다."""
        weights = load_scoring()["theme"]["weights"]
        assert len(set(weights.values())) > 1

    def test_price_carries_most_weight(self):
        """
        가격은 유일하게 조작할 수 없는 실제 체결 정보다. 뉴스는 후행하거나
        과장될 수 있다. 시장이 뉴스를 검증하지, 그 반대가 아니다.
        """
        w = load_scoring()["theme"]["weights"]
        assert w["price_momentum"] == max(w.values())
        assert w["price_momentum"] > w["news_sentiment"]

    def test_volatility_weight_is_negative(self):
        """테마 변동성 급등은 건전성이 아니라 불안정성이다."""
        assert load_scoring()["theme"]["weights"]["volatility"] < 0

    def test_breakdown_matches_components(self, shock):
        for t in shock:
            keys = {c.key for c in t.breakdown.contributions}
            assert keys | set(t.breakdown.missing_inputs) == set(
                load_scoring()["theme"]["weights"]
            )


class TestScenarioBehaviour:
    def test_inflation_shock_rotates_leadership(self, shock):
        """
        물가 충격이면 에너지·물가 테마가 위로, 성장 테마가 아래로 가야 한다.
        이 회전이 안 일어나면 테마 점수가 시장을 반영하지 못하는 것이다.
        """
        by_id = {t.theme_id: t for t in shock}
        assert by_id["inflation"].theme_score > 30
        assert by_id["oil"].theme_score > 30
        assert by_id["ai"].theme_score < -30
        assert by_id["semiconductor"].theme_score < -30

    def test_baseline_favours_ai_complex(self, quiet):
        by_id = {t.theme_id: t for t in quiet}
        assert by_id["ai"].theme_score > 0
        assert by_id["semiconductor"].price_momentum > 0

    def test_price_and_news_measure_different_things(self, shock):
        """
        news_sentiment 는 내러티브의 톤이고 price_momentum 은 시장이 실제로
        한 일이다. 둘이 다를 수 있어야 P2 의 divergence 가 성립한다.
        """
        by_id = {t.theme_id: t for t in shock}
        semi = by_id["semiconductor"]
        assert semi.news_sentiment != semi.price_momentum


class TestConfirmation:
    def test_agreeing_signals_read_high(self, quiet):
        by_id = {t.theme_id: t for t in quiet}
        ai = by_id["ai"]
        assert ai.price_momentum > 0 and ai.flow_momentum > 0
        assert ai.cross_asset_confirmation in (Confirmation.HIGH, Confirmation.MEDIUM)

    def test_insufficient_signals_do_not_claim_confirmation(self, quiet):
        """유효 신호가 2개 미만이면 확인했다고 말하지 않는다."""
        weak = [t for t in quiet if t.confirmation_score == 0.0]
        assert all(t.cross_asset_confirmation is Confirmation.LOW for t in weak)


class TestConfidence:
    def test_more_news_raises_confidence(self, shock):
        """기사 1건으로 만든 점수와 5건으로 만든 점수는 확신도가 다르다."""
        with_news = [t for t in shock if len(t.supporting_events) >= 3]
        without = [t for t in shock if not t.supporting_events]
        assert with_news and without
        assert max(t.confidence for t in with_news) > min(
            t.confidence for t in without
        )

    def test_stability_excluded_without_history(self, quiet):
        for t in quiet:
            assert "stability" in (t.confidence_breakdown.missing_inputs or [])

    def test_stability_included_with_history(
        self, instruments, themes, instruments_by_id, as_of
    ):
        history = {t.id: [10.0, 11.0, 9.5] for t in themes}
        states = _states(
            "baseline", instruments, themes, instruments_by_id, as_of, history=history
        )
        assert all(
            "stability" not in (t.confidence_breakdown.missing_inputs or [])
            for t in states
        )

    def test_volatile_history_lowers_confidence(
        self, instruments, themes, instruments_by_id, as_of
    ):
        steady = _states(
            "baseline", instruments, themes, instruments_by_id, as_of,
            history={t.id: [10.0, 10.2, 9.9] for t in themes},
        )
        jumpy = _states(
            "baseline", instruments, themes, instruments_by_id, as_of,
            history={t.id: [-60.0, 55.0, -40.0] for t in themes},
        )
        assert steady[0].confidence > jumpy[0].confidence


class TestChange:
    def test_last_change_uses_previous(
        self, instruments, themes, instruments_by_id, as_of
    ):
        first = _states("baseline", instruments, themes, instruments_by_id, as_of)
        assert all(t.last_change == 0.0 for t in first)

        previous = {t.theme_id: t.model_copy(update={"theme_score": 0.0}) for t in first}
        second = _states(
            "baseline", instruments, themes, instruments_by_id, as_of, previous=previous
        )
        by_id = {t.theme_id: t for t in second}
        for t in first:
            assert by_id[t.theme_id].last_change == pytest.approx(t.theme_score)


class TestNewsVolume:
    def test_cross_sectional_standardisation(self):
        out = cross_sectional_news_volume({"a": 10, "b": 0, "c": 0, "d": 0})
        assert out["a"] > 0 and out["b"] < 0

    def test_flat_counts_are_neutral(self):
        out = cross_sectional_news_volume({"a": 3, "b": 3})
        assert out == {"a": 0.0, "b": 0.0}

    def test_single_theme_is_unknown(self):
        assert cross_sectional_news_volume({"a": 5}) == {"a": None}


class TestDataQuality:
    def test_quality_reported(self, shock):
        assert all(isinstance(t.data_quality, DataQualityBand) for t in shock)

    def test_missing_instruments_degrade_quality(
        self, instruments, themes, instruments_by_id, as_of
    ):
        series = MockMarketAdapter(MOCK_DIR, "baseline").fetch_series(
            instruments, bars=180, as_of=as_of
        )
        stripped = {k: v for k, v in series.items() if k not in {"SOXX", "NDX", "XLK"}}
        snap = build_snapshot(instruments, stripped, mode=DataMode.MOCK, as_of=as_of)
        states = compute_theme_states(themes, snap, [], instruments_by_id)
        ai = next(t for t in states if t.theme_id == "ai")
        assert ai.data_quality is not DataQualityBand.OK


class TestMissingIsNotZero:
    """
    측정되지 않은 것과 측정해서 중립인 것은 다르다.
    둘을 0.0 으로 뭉개면 뉴스가 없는 테마와 뉴스가 팽팽한 테마를 구분할 수 없다.
    """

    def test_absent_components_are_none(self, quiet):
        no_news = [t for t in quiet if not t.supporting_events]
        assert no_news
        assert all(t.news_sentiment is None for t in no_news)

    def test_absent_flow_is_none_not_zero(self, quiet):
        by_id = {t.theme_id: t for t in quiet}
        assert by_id["oil"].flow_momentum is None, "Oil 테마에는 수급 자산이 없다"
        assert by_id["ai"].flow_momentum is not None, "AI 테마에는 수급 자산이 있다"

    def test_measured_components_are_present(self, shock):
        by_id = {t.theme_id: t for t in shock}
        assert by_id["oil"].news_sentiment is not None
        assert by_id["oil"].price_momentum is not None

    def test_news_gap_does_not_mask_market_data_gap(self, quiet):
        """
        뉴스가 없어서 빠진 것과 시장 데이터가 없어서 빠진 것은 품질 등급이
        달라야 한다. 전자는 가격만으로도 유효한 점수다.
        """
        by_id = {t.theme_id: t for t in quiet}
        news_only_gap = by_id["defense"]
        assert not news_only_gap.supporting_events
        assert news_only_gap.data_quality is DataQualityBand.OK

    def test_real_data_gap_still_degrades(
        self, instruments, themes, instruments_by_id, as_of
    ):
        """구조적 부재는 봐주되 진짜 결손은 봐주지 않는다."""
        series = MockMarketAdapter(MOCK_DIR, "baseline").fetch_series(
            instruments, bars=180, as_of=as_of
        )
        stripped = {k: v for k, v in series.items() if k not in {"ITA", "VIX"}}
        snap = build_snapshot(instruments, stripped, mode=DataMode.MOCK, as_of=as_of)
        states = compute_theme_states(themes, snap, [], instruments_by_id)
        defense = next(t for t in states if t.theme_id == "defense")
        assert defense.data_quality is not DataQualityBand.OK
