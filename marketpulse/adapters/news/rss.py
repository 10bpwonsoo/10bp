"""
RssNewsAdapter — feeds.yaml 의 RSS 를 읽는다 (P4).

RSS 만 쓰는 이유는 셋이다. 무료이고, 키가 필요 없고, 계약이 안정적이다.
유료 뉴스 API 는 재배포 라이선스가 걸리고 크롤링은 약관이 걸린다.

피드 하나가 죽어도 나머지는 나온다. 전부 죽으면 기사 0건으로 돌아가고,
정량 대시보드는 그대로 동작한다 — 뉴스는 enrichment 지 전제가 아니다
(요구 15-7 과 같은 원칙).

파서는 표준 라이브러리만 쓴다. feedparser 를 들이면 의존성이 하나 늘고
데모가 죽을 경로도 하나 는다 (설계서 STEP 7.7).
"""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path

import yaml

from ...config.settings import CONFIG_DIR
from ...models.common import DataMeta, DataMode, utcnow
from ...models.news import RawNewsItem
from ..base import NewsAdapter
from ..http import FetchError, HttpClient

logger = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
#: RSS 2.0 과 Atom 을 한 코드로 다룬다.
_ATOM = "{http://www.w3.org/2005/Atom}"


@lru_cache(maxsize=4)
def load_feeds(config_dir: Path | None = None) -> list[dict]:
    d = config_dir or CONFIG_DIR
    path = d / "feeds.yaml"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list((yaml.safe_load(fh) or {}).get("feeds") or [])


def reset_feeds_cache() -> None:
    load_feeds.cache_clear()


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return _WS.sub(" ", _TAG.sub(" ", node.text)).strip()


def _published(entry: ET.Element, fallback: datetime) -> datetime:
    for tag in ("pubDate", "published", f"{_ATOM}published", f"{_ATOM}updated", "updated"):
        node = entry.find(tag)
        if node is None or not node.text:
            continue
        raw = node.text.strip()
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(raw, fmt)
                return (
                    parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                ).astimezone(timezone.utc)
            except ValueError:
                continue
    # 날짜를 못 읽으면 지금으로 두지 않는다 — 오래된 기사가 최신으로
    # 둔갑하면 시간 감쇠 가중이 통째로 틀어진다. 호출자가 걸러낸다.
    return fallback


def parse_feed(raw: bytes, *, source: str, weight: float, lang: str) -> list[RawNewsItem]:
    """
    RSS/Atom 바이트를 RawNewsItem 으로. 네트워크 없이 테스트할 수 있게
    파싱을 따로 둔다.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise FetchError(f"XML 파싱 실패: {exc}", kind="parse", permanent=True) from exc

    entries = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
    if not entries:
        raise FetchError("항목이 없다", kind="empty", permanent=True)

    now = utcnow()
    out: list[RawNewsItem] = []
    for entry in entries:
        title = _text(entry.find("title")) or _text(entry.find(f"{_ATOM}title"))
        if not title:
            continue
        body = (
            _text(entry.find("description"))
            or _text(entry.find(f"{_ATOM}summary"))
            or _text(entry.find(f"{_ATOM}content"))
        )
        link_node = entry.find("link")
        url = (link_node.text or "").strip() if link_node is not None and link_node.text else None
        if url is None:
            atom_link = entry.find(f"{_ATOM}link")
            url = atom_link.get("href") if atom_link is not None else None

        guid = _text(entry.find("guid")) or url or title
        published = _published(entry, now)
        out.append(
            RawNewsItem(
                id=hashlib.sha256(f"{source}:{guid}".encode()).hexdigest()[:16],
                title=title,
                body=body[:1200],
                url=url,
                publisher=source,
                published_at=published,
                language=lang,
                meta=DataMeta(
                    source=source,
                    mode=DataMode.DELAYED,
                    retrieved_at=now,
                    as_of=published,
                ),
            )
        )
    return out


class RssNewsAdapter(NewsAdapter):
    """feeds.yaml 의 모든 피드를 읽어 최신순으로 합친다."""

    def __init__(
        self,
        *,
        config_dir: Path | None = None,
        client: HttpClient | None = None,
        mode: DataMode = DataMode.DELAYED,
    ) -> None:
        self.mode = mode
        self.name = "rss"
        self.config_dir = config_dir
        self.client = client or HttpClient()
        #: 직전 수집의 피드별 결과. data_health 와 probe 가 읽는다.
        self.outcomes: dict[str, str] = {}

    def fetch_news(
        self, *, limit: int = 100, as_of: datetime | None = None
    ) -> list[RawNewsItem]:
        feeds = load_feeds(self.config_dir)
        end = (as_of or utcnow()).astimezone(timezone.utc)
        self.outcomes = {}
        items: list[RawNewsItem] = []

        for feed in feeds:
            name = str(feed.get("name") or feed.get("url") or "?")
            try:
                raw = self.client.get(str(feed["url"]))
                parsed = parse_feed(
                    raw,
                    source=name,
                    weight=float(feed.get("weight", 1.0)),
                    lang=str(feed.get("lang") or "ko"),
                )
            except FetchError as exc:
                self.outcomes[name] = str(exc)
                continue
            except Exception as exc:  # noqa: BLE001 — 피드 하나가 화면을 막지 않는다
                logger.exception("%s 피드 처리 실패", name)
                self.outcomes[name] = f"예상 못 한 오류: {exc}"
                continue

            # 미래 시각 기사는 버린다. 피드가 타임존을 틀리는 일이 흔하고,
            # 그대로 두면 시간 감쇠 가중이 1 을 넘는다.
            fresh = [i for i in parsed if i.published_at <= end]
            items.extend(fresh)
            self.outcomes[name] = f"{len(fresh)}건"

        seen: set[str] = set()
        unique: list[RawNewsItem] = []
        for item in sorted(items, key=lambda i: i.published_at, reverse=True):
            # 같은 기사가 여러 피드에 실린다. 제목으로 한 번 더 거른다.
            key = _WS.sub("", item.title)[:60]
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique[:limit]

    def probe(self) -> dict[str, str]:
        return dict(self.outcomes)
