"""
LlmSearchNewsAdapter — Claude 의 web_search 로 기사를 찾는다 (P5).

왜 필요한가
-----------
조직 네트워크가 RSS 호스트를 전부 막으면 뉴스 패널이 0건이 되고, 그 뒤의
뉴스 감성·괴리·Impact Map 사건 노드가 전부 잠긴다. 웹검색은 Anthropic
서버가 수행하므로 api.anthropic.com 하나만 열려 있으면 기사에 닿는다.

무엇을 믿는가
-------------
**검색 결과 블록만** 믿는다. 제목·URL·게시 시각은 검색 엔진이 돌려준 실재
페이지의 것이다. 모델이 쓴 문장은 버린다 — 요약이든 목록이든. 그래야
존재하지 않는 기사가 화면에 오르는 경로가 없다 (요구 15-11).

그래서 이 어댑터가 주는 RawNewsItem 은 본문이 없다. 제목만 있다. 룰
추출기는 제목으로 동작하고, LLM 추출기도 제목만으로 태깅한다. 본문이
있는 RSS 보다 정보가 얕다는 사실은 DataMeta.quality=PARTIAL 로 남긴다.

시각을 모르는 결과는 버린다. RSS 어댑터와 같은 이유다 — 게시 시각을
'지금' 으로 두면 시간 감쇠 가중이 최대가 되어 옛 기사가 최신 기사를
누른다.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import yaml

from ...ai.client import LLMClient, LLMFailure, SearchHit
from ...config.settings import CONFIG_DIR
from ...models.common import DataMeta, DataMode, DataQuality, utcnow
from ...models.news import RawNewsItem
from ..base import NewsAdapter

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")
#: "3 hours ago" / "2 days ago" / "1 minute ago"
_RELATIVE = re.compile(
    r"(\d+)\s*(minute|hour|day|week)s?\s*ago", re.IGNORECASE
)
#: "September 11, 2026" / "Sep 11, 2026"
_MONTH_DAY_YEAR = ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ")

SYSTEM_PROMPT = """당신은 시장 뉴스 검색 도우미다. 주어진 검색어를 web_search 도구로
하나씩 검색한다. 검색 결과를 요약하거나 해석하지 않는다. 검색만 하고 "완료" 라고
답한다. 시장 상태를 판단하지 않는다 — 그것은 별도의 정량 엔진이 한다."""


@lru_cache(maxsize=4)
def load_search_config(config_dir: Path | None = None) -> dict:
    d = config_dir or CONFIG_DIR
    path = d / "feeds.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return dict((yaml.safe_load(fh) or {}).get("search") or {})


def reset_search_config_cache() -> None:
    load_search_config.cache_clear()


def parse_page_age(raw: str | None, now: datetime) -> datetime | None:
    """
    검색 결과의 page_age 를 시각으로. 읽을 수 없으면 None — 호출자가 버린다.

    형식이 공급자마다 다르다. 상대 표현("3 hours ago")과 절대 날짜 둘 다
    받되, 못 읽은 것을 '지금' 으로 둔갑시키지 않는다.
    """
    if not raw:
        return None
    text = raw.strip()
    m = _RELATIVE.search(text)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "minute": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
        }[unit]
        return now - delta
    for fmt in _MONTH_DAY_YEAR:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(
            timezone.utc
        )
    return None


def _publisher(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def hits_to_items(
    hits: list[SearchHit],
    *,
    as_of: datetime,
    retrieved: datetime,
    recency_hours: float,
    limit: int,
) -> tuple[list[RawNewsItem], dict[str, int]]:
    """
    검색 결과를 RawNewsItem 으로. 버린 이유별 개수를 함께 돌려준다.

    네트워크 없이 테스트할 수 있게 변환을 따로 둔다.
    """
    dropped = {"no_time": 0, "too_old": 0, "future": 0, "duplicate": 0}
    seen: set[str] = set()
    out: list[RawNewsItem] = []
    oldest = as_of - timedelta(hours=recency_hours)

    for hit in hits:
        published = parse_page_age(hit.page_age, retrieved)
        if published is None:
            dropped["no_time"] += 1
            continue
        if published > as_of:
            dropped["future"] += 1
            continue
        if published < oldest:
            dropped["too_old"] += 1
            continue
        key = _WS.sub("", hit.title)[:60]
        if key in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(key)
        publisher = _publisher(hit.url)
        out.append(
            RawNewsItem(
                id=hashlib.sha256(hit.url.encode()).hexdigest()[:16],
                title=hit.title,
                body="",  # 검색 결과에는 본문이 없다. 지어내지 않는다.
                url=hit.url,
                publisher=publisher,
                published_at=published,
                language="ko" if re.search(r"[가-힣]", hit.title) else "en",
                meta=DataMeta(
                    source=f"llm_search:{publisher}",
                    mode=DataMode.DELAYED,
                    retrieved_at=retrieved,
                    as_of=published,
                    # 제목뿐이다. 본문이 있는 RSS 보다 얕다는 사실을 남긴다.
                    quality=DataQuality.PARTIAL,
                ),
            )
        )

    out.sort(key=lambda i: i.published_at, reverse=True)
    return out[:limit], dropped


class LlmSearchNewsAdapter(NewsAdapter):
    """feeds.yaml 의 search.queries 를 web_search 로 돌려 기사를 모은다."""

    def __init__(
        self,
        client: LLMClient,
        *,
        config_dir: Path | None = None,
        mode: DataMode = DataMode.DELAYED,
    ) -> None:
        self.mode = mode
        self.name = "llm_search"
        self.client = client
        self.config_dir = config_dir
        #: 직전 수집 결과. data_health 와 probe 가 읽는다. 값이 "n건" 으로
        #: 끝나면 성공, 아니면 실패 사유다 (orchestrator.adapter_warnings 규약).
        self.outcomes: dict[str, str] = {}

    def fetch_news(
        self, *, limit: int = 100, as_of: datetime | None = None
    ) -> list[RawNewsItem]:
        cfg = load_search_config(self.config_dir)
        queries = [str(q) for q in (cfg.get("queries") or []) if str(q).strip()]
        self.outcomes = {}
        if not queries:
            self.outcomes["LLM 검색"] = "검색어가 설정되지 않았다 (feeds.yaml search.queries)"
            return []
        if not self.client.available():
            self.outcomes["LLM 검색"] = (
                self.client.last_error or f"LLM 사용 불가 ({self.client.status})"
            )
            return []

        end = (as_of or utcnow()).astimezone(timezone.utc)
        retrieved = utcnow()
        user = "다음 검색어를 각각 한 번씩 web_search 로 검색하라. 결과를 요약하지 마라.\n\n" + "\n".join(
            f"{i + 1}. {q}" for i, q in enumerate(queries)
        )
        result = self.client.search_news(
            system=SYSTEM_PROMPT,
            user=user,
            max_uses=int(cfg.get("max_uses", 4)),
        )
        if isinstance(result, LLMFailure):
            logger.warning("LLM 검색 실패 (%s): %s", result.kind, result.reason)
            self.outcomes["LLM 검색"] = f"실패({result.kind}): {result.reason}"
            return []

        items, dropped = hits_to_items(
            result,
            as_of=end,
            retrieved=retrieved,
            recency_hours=float(cfg.get("recency_hours", 48)),
            limit=min(limit, int(cfg.get("limit", 30))),
        )
        detail = ", ".join(f"{k} {v}" for k, v in dropped.items() if v)
        self.outcomes["LLM 검색"] = f"{len(items)}건" + (f" (제외: {detail})" if detail else "")
        # adapter_warnings 는 '건' 으로 끝나야 성공으로 본다. 제외 내역은
        # 별도 키로 남긴다.
        if detail:
            self.outcomes["LLM 검색"] = f"{len(items)}건"
            self.outcomes["LLM 검색 제외"] = f"{sum(dropped.values())}건"
        return items

    def probe(self) -> dict[str, str]:
        return dict(self.outcomes)


class CompositeNewsAdapter(NewsAdapter):
    """
    RSS 를 먼저, LLM 검색을 정책에 따라.

    auto  RSS 가 0건일 때만 검색한다. 검색은 돈이 들고, RSS 가 살아 있으면
          필요도 없다.
    on    항상 둘 다 모아 제목으로 중복을 거른다.
    off   검색을 쓰지 않는다.
    """

    def __init__(
        self,
        primary: NewsAdapter,
        fallback: NewsAdapter,
        *,
        policy: str = "auto",
        mode: DataMode = DataMode.DELAYED,
    ) -> None:
        self.mode = mode
        self.primary = primary
        self.fallback = fallback
        self.policy = policy
        self.name = f"{primary.name}+{fallback.name}"
        self.outcomes: dict[str, str] = {}

    def fetch_news(
        self, *, limit: int = 100, as_of: datetime | None = None
    ) -> list[RawNewsItem]:
        items = list(self.primary.fetch_news(limit=limit, as_of=as_of))
        self.outcomes = dict(getattr(self.primary, "outcomes", {}) or {})

        use_fallback = self.policy == "on" or (self.policy == "auto" and not items)
        if not use_fallback:
            return items

        extra = self.fallback.fetch_news(limit=limit, as_of=as_of)
        self.outcomes.update(getattr(self.fallback, "outcomes", {}) or {})

        seen = {_WS.sub("", i.title)[:60] for i in items}
        for item in extra:
            key = _WS.sub("", item.title)[:60]
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
        items.sort(key=lambda i: i.published_at, reverse=True)
        return items[:limit]

    def probe(self) -> dict[str, str]:
        return dict(self.outcomes)
