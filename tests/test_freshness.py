"""데이터 신선도를 거래일로 센다 — 금요일 봉을 월요일 아침에 '3일 전' 이라 부르지 않는다."""
from datetime import datetime, timezone

from marketpulse.config.settings import Settings
from marketpulse.engines.calendar import trading_days_between
from marketpulse.engines.orchestrator import run_pipeline


def _d(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


class TestTradingDaysBetween:
    def test_same_day_is_zero(self):
        assert trading_days_between(_d(2026, 9, 29, 0), _d(2026, 9, 29, 23)) == 0

    def test_friday_bar_seen_on_monday_is_one(self):
        # 9/25(금) 봉을 9/29(화) 에 보면 월·화 = 2, 9/28(월) 에 보면 1
        assert trading_days_between(_d(2026, 9, 25), _d(2026, 9, 28)) == 1
        assert trading_days_between(_d(2026, 9, 25), _d(2026, 9, 29)) == 2

    def test_weekend_only_gap_is_zero(self):
        # 금요일 봉을 일요일에 보면 거래일은 아직 지나지 않았다
        assert trading_days_between(_d(2026, 9, 25), _d(2026, 9, 27)) == 0

    def test_reversed_is_zero(self):
        assert trading_days_between(_d(2026, 9, 29), _d(2026, 9, 25)) == 0

    def test_two_full_weeks(self):
        assert trading_days_between(_d(2026, 9, 14), _d(2026, 9, 28)) == 10


class TestHealthFields:
    def test_pipeline_health_carries_trading_day_freshness(self):
        snap = run_pipeline(Settings(data_mode="MOCK", llm_enabled=False), as_of=_d(2026, 9, 29, 1))
        h = snap.data_health
        assert h.max_freshness_trading_days >= 0
        assert isinstance(h.oldest_instruments, list) and len(h.oldest_instruments) <= 8
        assert h.freshness_note
        if h.max_freshness_trading_days == 0:
            assert not h.oldest_instruments
        else:
            assert h.oldest_instruments and "상한" in h.freshness_note
