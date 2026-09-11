"""AlertEngine 테스트 (설계서 STEP 5.9 / 요구 9)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from marketpulse.config.settings import Settings
from marketpulse.engines.alert import carry_forward, severity_of
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.engines.scoring import load_scoring
from marketpulse.models.alert import AlertState, AlertType


def _ticks(scenario: str, n: int = 3):
    s = Settings(scenario=scenario)
    results = [run_pipeline_detailed(s)]
    for _ in range(n - 1):
        prev = results[-1]
        results.append(
            run_pipeline_detailed(
                s,
                history=[r.snapshot for r in results],
                pending_divergences=prev.pending,
            )
        )
    return results


@pytest.fixture(scope="module")
def ai_run():
    return _ticks("ai_divergence", 3)


class TestSeverity:
    @pytest.fixture
    def cfg(self):
        return load_scoring()["alert"]

    def test_grows_with_delta(self, cfg):
        a = severity_of(0.5, AlertType.PRICE_ZSCORE_SPIKE, cfg)
        b = severity_of(3.0, AlertType.PRICE_ZSCORE_SPIKE, cfg)
        assert b > a

    def test_type_weight_applied(self, cfg):
        """변화의 종류마다 중요도가 다르다."""
        state = severity_of(2.0, AlertType.STATE_CHANGE, cfg)
        quality = severity_of(2.0, AlertType.DATA_QUALITY, cfg)
        assert state > quality

    def test_every_type_has_a_weight(self, cfg):
        for t in AlertType:
            assert t.value in cfg["type_weights"], t.value


class TestChangeBased:
    def test_first_tick_has_no_change_alerts(self):
        """
        비교할 직전 틱이 없으면 '변화' 를 말할 수 없다. 수준 기반
        알림(가격 급변)만 나온다.
        """
        first = run_pipeline_detailed(Settings(scenario="ai_divergence"))
        change_types = {
            AlertType.STATE_CHANGE,
            AlertType.THEME_SENTIMENT_SPIKE,
            AlertType.FLOW_REVERSAL,
            AlertType.NEWS_VOLUME_SPIKE,
        }
        assert not [a for a in first.snapshot.alerts if a.type in change_types]

    def test_every_alert_carries_a_baseline(self, ai_run):
        """
        요구 9. 값만 있고 기준선이 없는 알림은 스키마가 만들지 못하게 막는다.
        """
        for r in ai_run:
            for a in r.snapshot.alerts:
                assert a.trigger.metric
                assert a.trigger.delta == pytest.approx(
                    a.trigger.current - a.trigger.baseline, abs=1e-6
                )

    def test_divergence_opens_an_alert(self, ai_run):
        second = ai_run[1]
        assert second.snapshot.divergences
        assert any(
            a.type is AlertType.DIVERGENCE_OPENED for a in second.snapshot.alerts
        )

    def test_price_spike_alert_from_z(self):
        """가격 급변은 z 자체가 이미 과거 대비 변화량이라 수준으로 본다."""
        run = run_pipeline_detailed(Settings(scenario="inflation_shock"))
        spikes = [
            a for a in run.snapshot.alerts if a.type is AlertType.PRICE_ZSCORE_SPIKE
        ]
        assert spikes
        assert all(abs(a.trigger.current) >= a.trigger.threshold for a in spikes)


class TestDeduplication:
    """
    기존 코드에는 중복 억제가 전혀 없었다. 같은 알림이 매 주기 반복되면
    아무도 알림을 보지 않게 된다.
    """

    def test_keys_are_unique_within_a_tick(self, ai_run):
        for r in ai_run:
            keys = [a.dedupe_key for a in r.snapshot.alerts]
            assert len(keys) == len(set(keys))

    def test_repeat_increments_instead_of_duplicating(self, ai_run, instruments_by_id):
        """같은 조건이 다시 참이면 새 알림이 아니라 발화 횟수만 올라간다."""
        from marketpulse.engines.alert import build_alerts

        snap = ai_run[1].snapshot
        base = dict(
            state=snap.market_state,
            themes=snap.themes,
            divergences=snap.divergences,
            health=snap.data_health,
        )
        # 직전에 divergence 가 없었다고 두면 DIVERGENCE_OPENED 가 다시 발생한다
        from marketpulse.adapters.market.mock import MockMarketAdapter
        from marketpulse.config.settings import MOCK_DIR
        from marketpulse.engines.normalize import build_snapshot
        from marketpulse.models.common import DataMode

        instruments = list(instruments_by_id.values())
        series = MockMarketAdapter(MOCK_DIR, "ai_divergence").fetch_series(
            instruments, bars=180, as_of=snap.as_of
        )
        market = build_snapshot(
            instruments, series, mode=DataMode.MOCK, as_of=snap.as_of
        )

        first = build_alerts(
            base["state"], base["themes"], base["divergences"], market,
            base["health"], instruments_by_id,
        )
        again = build_alerts(
            base["state"], base["themes"], base["divergences"], market,
            base["health"], instruments_by_id, previous_alerts=first,
        )
        assert len(again) == len(first)
        assert all(a.fire_count == 2 for a in again)
        assert all(a.state is AlertState.ONGOING for a in again)

    def test_repeat_keeps_first_fired_at(self, ai_run, instruments_by_id):
        from marketpulse.adapters.market.mock import MockMarketAdapter
        from marketpulse.config.settings import MOCK_DIR
        from marketpulse.engines.alert import build_alerts
        from marketpulse.engines.normalize import build_snapshot
        from marketpulse.models.common import DataMode

        snap = ai_run[1].snapshot
        instruments = list(instruments_by_id.values())
        market = build_snapshot(
            instruments,
            MockMarketAdapter(MOCK_DIR, "ai_divergence").fetch_series(
                instruments, bars=180, as_of=snap.as_of
            ),
            mode=DataMode.MOCK,
            as_of=snap.as_of,
        )
        first = build_alerts(
            snap.market_state, snap.themes, snap.divergences, market,
            snap.data_health, instruments_by_id,
        )
        again = build_alerts(
            snap.market_state, snap.themes, snap.divergences, market,
            snap.data_health, instruments_by_id, previous_alerts=first,
        )
        by_key = {a.dedupe_key: a for a in first}
        for a in again:
            assert a.first_fired_at == by_key[a.dedupe_key].first_fired_at


class TestTimelineRetention:
    """
    알림은 '지금 참인 것' 의 목록이 아니라 '최근에 일어난 일' 의 기록이다.
    괴리 발생 같은 사건은 다음 틱에 조건이 재생성되지 않는데, 그때마다
    화면에서 사라지면 타임라인이 성립하지 않는다.
    """

    def test_event_stays_in_timeline_after_condition_clears(self, ai_run):
        second, third = ai_run[1].snapshot, ai_run[2].snapshot
        opened = {
            a.dedupe_key
            for a in second.alerts
            if a.type is AlertType.DIVERGENCE_OPENED
        }
        assert opened
        assert opened <= {a.dedupe_key for a in third.alerts}

    def test_persisting_condition_stays_ongoing(self, ai_run):
        """
        괴리가 4틱째 이어지고 있는데 알림이 "해소" 로 찍히면 화면이
        거짓말을 한다. 재생성되지 않았다고 해서 해소된 것은 아니다.
        """
        third = ai_run[2].snapshot
        assert third.divergences
        live_ids = {d.id for d in third.divergences}
        carried = [
            a
            for a in third.alerts
            if a.type is AlertType.DIVERGENCE_OPENED and a.subject in live_ids
        ]
        assert carried
        assert all(a.state is not AlertState.RESOLVED for a in carried)

    def test_vanished_condition_is_resolved(self, ai_run):
        live = ai_run[1].snapshot.alerts
        assert live
        carried = carry_forward(
            [], live, ai_run[1].snapshot.as_of, live_subjects=set()
        )
        assert carried
        assert all(a.state is AlertState.RESOLVED for a in carried)

    def test_dropped_after_retention_window(self, ai_run):
        live = ai_run[1].snapshot.alerts
        assert live
        long_after = ai_run[1].snapshot.as_of + timedelta(hours=5)
        assert carry_forward([], live, long_after) == []

    def test_still_live_alerts_are_not_carried(self, ai_run):
        live = ai_run[1].snapshot.alerts
        assert carry_forward(live, live, ai_run[1].snapshot.as_of) == []


class TestOrdering:
    def test_sorted_by_severity(self, ai_run):
        for r in ai_run:
            sev = [
                a.severity for a in r.snapshot.alerts if a.state is not AlertState.RESOLVED
            ]
            assert sev == sorted(sev, reverse=True)
