"""
애널리스트 코멘트 저장소·검색 어댑터 (2026-09-29).

세 층이다.
1. manual: data/analyst_views/manual/*.json — 사람이 웹에서 확인해 적은 항목(retrieved_by=manual). 정적 배포본의 재료.
2. cache: data/analyst_views/cache.json — LLM 웹검색이 찾은 항목. TTL 안에서는 다시 검색하지 않는다.
3. provider: Claude 의 web_search 로 radar 종목만 찾는다. 모델이 쓴 문장을 그대로 믿지 않는다 — source_url 은
   검색 엔진이 돌려준 URL 목록 안에 있어야 하고, 이름·증권사·날짜·요약이 다 있어야 하고, 날짜가 max_age_days 안이어야 한다.
   하나라도 어긋나면 그 종목은 버린다(빈 줄을 만들지 않는다).

키는 환경변수로만 들어오고 어디에도 출력하지 않는다. 검색이 실패해도 radar 는 뜬다 — 이 층만 숨는다.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from ..models.analyst_view import AnalystView

logger = logging.getLogger(__name__)

_URL = re.compile(r"^https?://[^\s]+$")


def validate_view(raw: Mapping, *, as_of: datetime, max_age_days: int, allowed_urls: Iterable[str] | None = None, retrieved_by: str = "manual") -> AnalystView | None:
    """필수 필드가 다 있고 날짜가 한도 안일 때만 AnalystView. 아니면 None — 추정으로 채우지 않는다."""
    try:
        analyst = str(raw.get("analyst") or "").strip(); broker = str(raw.get("broker") or "").strip()
        url = str(raw.get("source_url") or "").strip(); summary = str(raw.get("summary") or "").strip()
        pd = raw.get("published_date")
        published = pd if isinstance(pd, date) else date.fromisoformat(str(pd)[:10])
    except Exception:
        return None
    if not (analyst and broker and summary and _URL.match(url)):
        return None
    if allowed_urls is not None and url not in set(allowed_urls):
        return None  # 검색 결과에 없는 URL 은 모델이 쓴 것일 수 있다
    age = (as_of.date() - published).days
    if age < 0 or age > max_age_days:
        return None
    ra = raw.get("retrieved_at")
    try:
        retrieved = ra if isinstance(ra, datetime) else datetime.fromisoformat(str(ra)) if ra else as_of
    except Exception:
        retrieved = as_of
    if retrieved.tzinfo is None:
        retrieved = retrieved.replace(tzinfo=timezone.utc)
    kv = raw.get("key_variables") or []
    return AnalystView(
        stock_id=str(raw.get("stock_id") or ""), stock_name=str(raw.get("stock_name") or ""), analyst=analyst, broker=broker, published_date=published,
        source_url=url, source_title=str(raw.get("source_title") or ""), summary=summary, key_view=str(raw.get("key_view") or ""),
        key_variables=[str(x) for x in kv][:6], stance=str(raw.get("stance") or "neutral") if str(raw.get("stance") or "neutral") in ("constructive", "cautious", "neutral", "mixed") else "neutral",  # type: ignore[arg-type]
        rating=str(raw.get("rating") or ""), target_change=str(raw.get("target_change") or ""), retrieved_at=retrieved,
        retrieved_by=str(raw.get("retrieved_by") or retrieved_by),  # type: ignore[arg-type]
        age_days=age, freshness=f"{age}D",
    )


class AnalystViewStore:
    """manual 디렉터리 + JSON 캐시. 종목별 최신 하나만 남긴다."""

    def __init__(self, cache_path: Path, manual_dir: Path) -> None:
        self.cache_path, self.manual_dir = cache_path, manual_dir
        self._lock = threading.Lock()

    def _read_json(self, p: Path) -> list[dict]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
        rows = data.get("views") if isinstance(data, dict) else data
        return [r for r in (rows or []) if isinstance(r, dict)]

    def manual(self) -> list[dict]:
        if not self.manual_dir.exists():
            return []
        out: list[dict] = []
        for p in sorted(self.manual_dir.glob("*.json")):
            for r in self._read_json(p):
                r.setdefault("retrieved_by", "manual"); out.append(r)
        return out

    def cached(self) -> list[dict]:
        with self._lock:
            return self._read_json(self.cache_path) if self.cache_path.exists() else []

    def put(self, rows: Sequence[dict]) -> None:
        with self._lock:
            cur = {r.get("stock_id"): r for r in (self._read_json(self.cache_path) if self.cache_path.exists() else [])}
            for r in rows:
                cur[r.get("stock_id")] = r
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps({"views": list(cur.values())}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    def best(self, stock_ids: Sequence[str], *, as_of: datetime, max_age_days: int) -> dict[str, AnalystView]:
        """종목별로 가장 최근 발행 코멘트(검증 통과한 것만)."""
        out: dict[str, AnalystView] = {}
        for raw in self.manual() + self.cached():
            sid = str(raw.get("stock_id") or "")
            if sid not in stock_ids:
                continue
            v = validate_view(raw, as_of=as_of, max_age_days=max_age_days)
            if v is None:
                continue
            if sid not in out or v.published_date > out[sid].published_date:
                out[sid] = v
        return out

    def retrieved_at(self, stock_id: str) -> datetime | None:
        for raw in self.cached():
            if raw.get("stock_id") == stock_id and raw.get("retrieved_at"):
                try:
                    t = datetime.fromisoformat(str(raw["retrieved_at"]))
                    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
                except Exception:
                    return None
        return None


SEARCH_SYSTEM = """당신은 증권사 리서치 코멘트를 찾는 도우미다. 주어진 종목 하나에 대해 web_search 로 최근 30일 안의
sell-side 애널리스트 코멘트(공개 리서치 페이지, Bloomberg/Reuters/CNBC 인용, 국내 종목은 국내 증권사 리포트를 인용한 경제매체, 실적 뒤 업데이트)를 찾는다.
반드시 지킬 것:
- 검색 결과에 실제로 나온 페이지에서 확인된 애널리스트 이름 · 증권사 · 발행일 · URL 만 적는다. 추정·생성 금지.
- 이름이나 증권사나 날짜를 확인할 수 없으면 found=false 로 답한다. 빈 값으로 채우지 않는다.
- summary 는 원문 복사가 아니라 '왜 그렇게 보는가' 를 한 문장으로 바꿔 쓴다(투자의견이 아니라 근거 변수: HBM 수요, ASP, capex, margin, EPS revision 등).
- key_variables 에는 그 애널리스트가 말한 핵심 변수만 2~5개.
- stance 는 코멘트 톤: constructive / cautious / neutral / mixed.
- 7일 이내 자료를 우선하고, 없으면 30일 이내. 그보다 오래된 것은 found=false."""

SEARCH_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "found": {"type": "boolean"}, "analyst": {"type": "string"}, "broker": {"type": "string"}, "published_date": {"type": "string"},
        "source_url": {"type": "string"}, "source_title": {"type": "string"}, "summary": {"type": "string"}, "key_view": {"type": "string"},
        "key_variables": {"type": "array", "items": {"type": "string"}}, "stance": {"type": "string", "enum": ["constructive", "cautious", "neutral", "mixed"]},
        "rating": {"type": "string"}, "target_change": {"type": "string"},
    },
    "required": ["found", "analyst", "broker", "published_date", "source_url", "source_title", "summary", "key_view", "key_variables", "stance", "rating", "target_change"],
}


class LlmAnalystSearch:
    """Claude web_search 로 종목 하나의 최신 코멘트를 찾는다. 결과는 validate_view 를 통과해야만 저장된다."""

    def __init__(self, client, *, max_uses: int = 3) -> None:
        self._client, self._max_uses = client, max_uses

    @property
    def available(self) -> bool:
        return bool(getattr(self._client, "enabled", False))

    def search(self, stock_id: str, name: str, aliases: Sequence[str], *, as_of: datetime, max_age_days: int) -> AnalystView | None:
        if not self.available:
            return None
        user = (f"종목: {name} ({stock_id}; 다른 표기: {', '.join(aliases) if aliases else '-'}). 기준일 {as_of.date().isoformat()}. "
                f"최근 {max_age_days}일 안의 sell-side 애널리스트 코멘트를 찾아 스키마대로 답하라.")
        try:
            res = self._client.search_structured(system=SEARCH_SYSTEM, user=user, schema=SEARCH_SCHEMA, max_uses=self._max_uses)
        except Exception:
            logger.exception("analyst search 실패 %s", stock_id)
            return None
        if not isinstance(res, tuple):
            return None
        data, hits = res
        if not isinstance(data, dict) or not data.get("found"):
            return None
        data = dict(data); data.update(stock_id=stock_id, stock_name=name, retrieved_at=datetime.now(timezone.utc).isoformat(), retrieved_by="llm_web")
        return validate_view(data, as_of=as_of, max_age_days=max_age_days, allowed_urls=[h.url for h in hits], retrieved_by="llm_web")


def ttl_expired(retrieved_at: datetime | None, *, ttl_hours: float, now: datetime) -> bool:
    return retrieved_at is None or (now - retrieved_at) > timedelta(hours=ttl_hours)
