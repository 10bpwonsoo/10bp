"""저장소 테스트 (설계서 STEP 6.3)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from marketpulse.config.settings import Settings
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.models.snapshot import IntelligenceSnapshot
from marketpulse.scheduler.runner import loop, run_once, stream_key
from marketpulse.storage.sqlite_repo import SqliteSnapshotRepository

KEY = "MOCK:ai_divergence"


@pytest.fixture
def repo():
    r = SqliteSnapshotRepository(":memory:")
    yield r
    r.close()


@pytest.fixture
def result():
    return run_pipeline_detailed(Settings(scenario="ai_divergence"))


class TestRoundTrip:
    def test_save_and_read(self, repo, result):
        repo.save(KEY, result.snapshot, result.pending)
        rows = repo.recent(KEY)
        assert len(rows) == 1
        assert isinstance(rows[0], IntelligenceSnapshot)
        assert rows[0].as_of == result.snapshot.as_of

    def test_full_payload_survives(self, repo, result):
        repo.save(KEY, result.snapshot, result.pending)
        back = repo.recent(KEY)[0]
        assert back.model_dump(mode="json") == result.snapshot.model_dump(mode="json")

    def test_pending_survives(self, repo, result):
        """미확정 후보를 잃으면 프로세스 재시작 때 지속 기간이 끊긴다."""
        assert result.pending
        repo.save(KEY, result.snapshot, result.pending)
        back = repo.latest_pending(KEY)
        assert {d.id for d in back} == {d.id for d in result.pending}

    def test_empty_when_unknown_stream(self, repo):
        assert repo.recent("MOCK:nope") == []
        assert repo.latest_pending("MOCK:nope") == []


class TestOrdering:
    def _write(self, repo, result, n: int):
        base = result.snapshot
        for i in range(n):
            repo.save(
                KEY,
                base.model_copy(update={"as_of": base.as_of + timedelta(minutes=i)}),
            )

    def test_returned_oldest_first(self, repo, result):
        """엔진은 시간순을 기대한다."""
        self._write(repo, result, 5)
        rows = repo.recent(KEY, limit=5)
        assert [r.as_of for r in rows] == sorted(r.as_of for r in rows)

    def test_limit_takes_most_recent(self, repo, result):
        self._write(repo, result, 5)
        rows = repo.recent(KEY, limit=2)
        assert len(rows) == 2
        assert rows[-1].as_of == result.snapshot.as_of + timedelta(minutes=4)

    def test_latest_pending_is_from_newest_row(self, repo, result):
        repo.save(KEY, result.snapshot, result.pending)
        repo.save(
            KEY,
            result.snapshot.model_copy(
                update={"as_of": result.snapshot.as_of + timedelta(minutes=1)}
            ),
            [],
        )
        assert repo.latest_pending(KEY) == []


class TestIdempotence:
    def test_same_as_of_overwrites(self, repo, result):
        """재실행이 중복 행을 만들면 히스토리가 오염된다."""
        repo.save(KEY, result.snapshot, result.pending)
        repo.save(KEY, result.snapshot, [])
        assert len(repo.recent(KEY)) == 1
        assert repo.latest_pending(KEY) == []

    def test_streams_are_isolated(self, repo, result):
        repo.save(KEY, result.snapshot)
        repo.save("MOCK:baseline", result.snapshot)
        assert len(repo.recent(KEY)) == 1
        assert len(repo.recent("MOCK:baseline")) == 1


class TestPrune:
    def test_keeps_newest(self, repo, result):
        base = result.snapshot
        for i in range(10):
            repo.save(
                KEY, base.model_copy(update={"as_of": base.as_of + timedelta(minutes=i)})
            )
        removed = repo.prune(KEY, keep=3)
        assert removed == 7
        rows = repo.recent(KEY, limit=50)
        assert len(rows) == 3
        assert rows[-1].as_of == base.as_of + timedelta(minutes=9)


class TestScheduler:
    def test_stream_key_matches_service(self):
        assert stream_key(Settings(scenario="ai_divergence")) == KEY

    def test_run_once_persists(self, repo):
        summary = run_once(Settings(scenario="ai_divergence"), repo)
        assert "state=" in summary
        assert len(repo.recent(KEY)) == 1

    def test_consecutive_ticks_confirm_divergences(self, repo):
        """
        스케줄러를 몇 틱 돌려 두면 화면이 첫 순간부터 채워진다.
        첫 틱은 후보만, 둘째 틱부터 확정된다.
        """
        s = Settings(scenario="ai_divergence")
        run_once(s, repo)
        assert repo.recent(KEY)[-1].divergences == []
        run_once(s, repo)
        assert repo.recent(KEY)[-1].divergences

    def test_loop_stops_at_max_ticks(self, repo):
        import threading

        stop = threading.Event()
        ticks = loop(
            Settings(scenario="baseline"),
            repo,
            interval=0.0,
            stop=stop,
            max_ticks=3,
        )
        assert ticks == 3

    def test_loop_survives_a_failing_tick(self, repo, monkeypatch):
        """한 틱의 실패가 루프를 죽이면 안 된다."""
        import threading

        calls = {"n": 0}

        def boom(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("의도적 실패")

        monkeypatch.setattr("marketpulse.scheduler.runner.run_once", boom)
        ticks = loop(
            Settings(scenario="baseline"),
            repo,
            interval=0.0,
            stop=threading.Event(),
            max_ticks=2,
        )
        assert ticks == 2 and calls["n"] == 2
