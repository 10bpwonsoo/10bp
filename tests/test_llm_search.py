"""
LLM 웹검색 뉴스 어댑터 (P5). 네트워크를 쓰지 않는다.

이 어댑터의 약속은 하나다 — 모델이 쓴 문장은 믿지 않고 검색 결과만 믿는다.
그리고 시각을 모르는 결과는 버린다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from marketpulse.adapters.news.llm_search import (
    CompositeNewsAdapter,
    LlmSearchNewsAdapter,
    hits_to_items,
    parse_page_age,
)
from marketpulse.adapters.registry import build_news_adapter, reset_adapter_cache
from marketpulse.ai.client import LLMClient, LLMFailure, SearchHit, reset_client_cache
from marketpulse.config.settings import Settings
from marketpulse.models.common import DataMeta, DataMode, DataQuality, utcnow
from marketpulse.models.news import RawNewsItem

NOW = datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean():
    reset_client_cache()
    reset_adapter_cache()
    yield
    reset_client_cache()
    reset_adapter_cache()


class FakeSearchClient(LLMClient):
    def __init__(self, result, *, enabled: bool = True):
        super().__init__(enabled=enabled, model="fake-model")
        self._result = result
        self.calls: list[dict] = []

    def search_news(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


class TestPageAge:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("3 hours ago", NOW - timedelta(hours=3)),
            ("2 days ago", NOW - timedelta(days=2)),
            ("1 minute ago", NOW - timedelta(minutes=1)),
            ("September 11, 2026", datetime(2026, 9, 11, tzinfo=timezone.utc)),
            ("2026-09-12", datetime(2026, 9, 12, tzinfo=timezone.utc)),
        ],
    )
    def test_parses(self, raw, expected):
        assert parse_page_age(raw, NOW) == expected

    def test_unknown_is_none_not_now(self):
        assert parse_page_age("recently", NOW) is None
        assert parse_page_age(None, NOW) is None


class TestHitsToItems:
    def _hit(self, title, url, age):
        return SearchHit(title=title, url=url, page_age=age, query="q")

    def test_keeps_only_dated_recent_unique(self):
        hits = [
            self._hit("코스피 마감", "https://www.example.co.kr/a", "2 hours ago"),
            self._hit("코스피 마감", "https://other.com/b", "3 hours ago"),  # 제목 중복
            self._hit("No date", "https://x.com/c", None),  # 시각 미상
            self._hit("Old news", "https://x.com/d", "5 days ago"),  # 오래됨
            self._hit("Future", "https://x.com/e", "2026-09-15"),  # 미래
        ]
        items, dropped = hits_to_items(
            hits, as_of=NOW, retrieved=NOW, recency_hours=48, limit=30
        )
        assert [i.title for i in items] == ["코스피 마감"]
        assert dropped == {"no_time": 1, "too_old": 1, "future": 1, "duplicate": 1}

    def test_item_provenance(self):
        items, _ = hits_to_items(
            [self._hit("Markets rally", "https://www.reuters.com/x", "1 hour ago")],
            as_of=NOW, retrieved=NOW, recency_hours=48, limit=30,
        )
        item = items[0]
        assert item.publisher == "reuters.com"
        assert item.meta.source == "llm_search:reuters.com"
        assert item.meta.quality == DataQuality.PARTIAL, "제목뿐이라는 사실을 남긴다"
        assert item.body == "", "본문을 지어내지 않는다"
        assert item.language == "en"


class TestAdapter:
    def test_disabled_client_yields_nothing_with_reason(self):
        adapter = LlmSearchNewsAdapter(FakeSearchClient([], enabled=False))
        assert adapter.fetch_news(as_of=NOW) == []
        assert "LLM 검색" in adapter.outcomes
        assert not adapter.outcomes["LLM 검색"].endswith("건")

    def test_failure_is_a_value(self):
        adapter = LlmSearchNewsAdapter(FakeSearchClient(LLMFailure("boom", "api")))
        assert adapter.fetch_news(as_of=NOW) == []
        assert "실패(api)" in adapter.outcomes["LLM 검색"]

    def test_success_records_count(self):
        client = FakeSearchClient(
            [SearchHit("코스피 상승 마감", "https://a.kr/1", "2026-09-13", "q")]
        )
        adapter = LlmSearchNewsAdapter(client)
        items = adapter.fetch_news(as_of=NOW)
        assert len(items) == 1
        assert adapter.outcomes["LLM 검색"] == "1건"
        assert client.calls and client.calls[0]["max_uses"] >= 1


def _rss_like(n: int) -> list[RawNewsItem]:
    return [
        RawNewsItem(
            id=f"r{i}",
            title=f"RSS 기사 {i}",
            published_at=NOW - timedelta(hours=i),
            meta=DataMeta(source="rss", mode=DataMode.DELAYED, retrieved_at=utcnow(), as_of=NOW),
        )
        for i in range(n)
    ]


class _Stub:
    mode = DataMode.DELAYED

    def __init__(self, name, items):
        self.name = name
        self.items = items
        self.calls = 0
        self.outcomes = {name: f"{len(items)}건"}

    def fetch_news(self, *, limit=100, as_of=None):
        self.calls += 1
        return list(self.items)


class TestComposite:
    def test_auto_skips_search_when_rss_alive(self):
        rss, search = _Stub("rss", _rss_like(3)), _Stub("llm_search", _rss_like(2))
        c = CompositeNewsAdapter(rss, search, policy="auto")
        assert len(c.fetch_news(as_of=NOW)) == 3
        assert search.calls == 0

    def test_auto_falls_back_when_rss_empty(self):
        rss, search = _Stub("rss", []), _Stub("llm_search", _rss_like(2))
        c = CompositeNewsAdapter(rss, search, policy="auto")
        assert len(c.fetch_news(as_of=NOW)) == 2
        assert search.calls == 1
        assert "llm_search" in c.outcomes

    def test_on_merges_and_dedupes(self):
        rss = _Stub("rss", _rss_like(2))
        search = _Stub("llm_search", _rss_like(3))  # 제목이 겹친다
        c = CompositeNewsAdapter(rss, search, policy="on")
        assert len(c.fetch_news(as_of=NOW)) == 3
        assert search.calls == 1

    def test_off_never_searches(self):
        rss, search = _Stub("rss", []), _Stub("llm_search", _rss_like(2))
        c = CompositeNewsAdapter(rss, search, policy="off")
        assert c.fetch_news(as_of=NOW) == []
        assert search.calls == 0


class TestRegistry:
    def test_llm_disabled_is_plain_rss(self):
        a = build_news_adapter(Settings(data_mode="DELAYED", llm_enabled=False))
        assert a.name == "rss"

    def test_llm_enabled_composes(self):
        a = build_news_adapter(Settings(data_mode="DELAYED", llm_enabled=True))
        assert isinstance(a, CompositeNewsAdapter)
        assert a.policy == "auto"

    def test_search_off_is_plain_rss(self):
        a = build_news_adapter(
            Settings(data_mode="DELAYED", llm_enabled=True, news_search="off")
        )
        assert a.name == "rss"
