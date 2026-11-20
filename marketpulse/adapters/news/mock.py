"""MOCK 뉴스 어댑터. 시나리오 파일의 news 배열을 RawNewsItem 으로 바꾼다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ...models.common import DataMeta, DataMode, DataQuality, utcnow
from ...models.news import RawNewsItem
from ..base import NewsAdapter
from ..market.scenario import load_scenario


class MockNewsAdapter(NewsAdapter):
    mode = DataMode.MOCK

    def __init__(self, mock_dir: Path, scenario_name: str = "baseline") -> None:
        self.mock_dir = mock_dir
        self.scenario_name = scenario_name
        self.name = f"mock:scenario_{scenario_name}"

    def fetch_news(
        self, *, limit: int = 100, as_of: datetime | None = None
    ) -> list[RawNewsItem]:
        sc = load_scenario(self.mock_dir, self.scenario_name)
        end = (as_of or utcnow()).astimezone(timezone.utc)
        retrieved = utcnow()

        items: list[RawNewsItem] = []
        for spec in sc.news:
            published = end - timedelta(hours=spec.hours_ago)
            items.append(
                RawNewsItem(
                    id=spec.id,
                    title=spec.title,
                    body=spec.body,
                    url=spec.url,
                    publisher=spec.publisher,
                    published_at=published,
                    language=spec.language,
                    meta=DataMeta(
                        source=self.name,
                        mode=DataMode.MOCK,
                        retrieved_at=retrieved,
                        as_of=published,
                        quality=DataQuality.OK,
                    ),
                )
            )
        items.sort(key=lambda i: i.published_at, reverse=True)
        return items[:limit]
