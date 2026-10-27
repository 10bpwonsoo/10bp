"""
DailyArchiveService — 그날 대시보드 화면 전체를 날짜별 JSON 하나로 저장하고 다시 읽는다.

    capture()      지금 상태를 저장 (같은 날짜가 있으면 건너뛴다 — 덮어쓰지 않는다)
    get(date)      저장본 그대로 (다시 계산하지 않는다)
    latest()       가장 최근 저장본
    list_dates()   저장된 날짜, 최신순
    correct(...)   명시적 correction — 이전 파일은 superseded/ 에 남기고 audit 을 붙인다

스케줄러와 분리된 순수 서비스다. 무엇을 모을지는 collectors(섹션 이름 → 함수)로 주입한다 — 기본값은 collect.py 가
API 와 같은 서비스(같은 캐시·같은 as_of)를 부르는 것이다. 섹션 하나가 실패해도 저장은 계속하고(null + errors · PARTIAL),
필수 섹션(snapshot)이 실패하면 아무 파일도 남기지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import yaml

from .store import ArchiveExistsError, ArchiveNotFoundError, ArchiveStore

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "archive.yaml"

Collector = Callable[[], Any]


class ArchiveCaptureError(RuntimeError):
    """필수 섹션을 못 모았다. 파일을 남기지 않는다."""


class NotAvailableHistorically(RuntimeError):
    """그 날짜 시점의 값을 복원할 수 없다 — 지금 값으로 채우지 않고 null + NOT_AVAILABLE_HISTORICALLY 로 저장한다."""


def is_snapshot_day(d: date, cfg: Mapping[str, Any] | None = None) -> bool:
    """Daily Snapshot 대상일 — 월~금(weekday < 5). config 의 holidays(YYYY-MM-DD 목록)는 휴장일 확장 자리다(지금은 비어 있다)."""
    cfg = cfg or {}
    if cfg.get("weekdays_only", True) and d.weekday() >= 5:
        return False
    return d.isoformat() not in set(str(x) for x in (cfg.get("holidays") or []))


def skip_reason(d: date, cfg: Mapping[str, Any] | None = None) -> str | None:
    if (cfg or {}).get("weekdays_only", True) and d.weekday() >= 5:
        return "WEEKEND"
    if d.isoformat() in set(str(x) for x in ((cfg or {}).get("holidays") or [])):
        return "HOLIDAY"
    return None


#: 데이터 시각을 뜻하는 키 — 이 값이 cutoff 뒤면 미래 데이터다. calculated_at · retrieved_at 같은 처리 시각과
#: 앞으로의 일정(upcoming 의 date · release_utc)은 데이터 시각이 아니므로 보지 않는다.
DATA_TIME_KEYS = ("as_of", "data_asof", "published_at", "timestamp", "source_asof", "last_date", "last_bar", "observed_at")
SCHEDULE_PARENTS = ("upcoming", "next", "calendar", "what_matters_next", "triggers", "release")


def future_data_paths(value: Any, cutoff: datetime, *, path: str = "", limit: int = 20) -> list[str]:
    """cutoff 뒤의 데이터 시각을 가진 위치. 일정(upcoming 등) 아래는 건너뛴다."""
    out: list[str] = []

    def walk(v: Any, p: str) -> None:
        if len(out) >= limit:
            return
        if isinstance(v, Mapping):
            for k, x in v.items():
                k = str(k)
                if k in SCHEDULE_PARENTS:
                    continue
                if k in DATA_TIME_KEYS and isinstance(x, str):
                    t = _parse_ts(x)
                    if t is None and len(x) == 10:
                        try:
                            t = datetime.combine(date.fromisoformat(x), time(0, 0), tzinfo=timezone.utc)
                        except ValueError:
                            t = None
                    if t is not None and t > cutoff:
                        out.append(f"{p}.{k}={x}")
                        continue
                walk(x, f"{p}.{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{p}[{i}]")

    walk(value, path)
    return out


def load_archive_config(path: Path | None = None) -> dict[str, Any]:
    return yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8")) or {}


def to_jsonable(value: Any) -> Any:
    """API 응답과 같은 JSON 형태로. pydantic 모델은 model_dump(mode='json'), 목록·사전은 안쪽까지."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _parse_ts(text: Any) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class CaptureResult:
    status: str                      # WRITTEN | EXISTS
    snapshot_date: str
    path: Path
    archive_status: str | None = None  # COMPLETE | PARTIAL
    errors: dict[str, str] = field(default_factory=dict)

    def line(self) -> str:
        if self.status.startswith("SKIPPED"):
            return f"{self.snapshot_date} {self.status.replace('_', ' - ', 1)} — 만들지 않음"
        if self.status == "EXISTS":
            return f"{self.snapshot_date} 저장본이 이미 있어 건너뜀 (덮어쓰지 않음) · {self.path}"
        miss = f" · 빠진 섹션 {', '.join(sorted(self.errors))}" if self.errors else ""
        return f"{self.snapshot_date} 저장 {self.archive_status}{miss} · {self.path}"


class DailyArchiveService:
    def __init__(self, store: ArchiveStore, *, collectors: Mapping[str, Collector] | None = None,
                 config: dict[str, Any] | None = None, created_by: str = "daily_archive") -> None:
        self.store = store
        self.cfg = config or load_archive_config()
        self.collectors = dict(collectors or {})
        self.created_by = created_by

    # ── 설정 ──────────────────────────────────────────────
    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(str(self.cfg.get("timezone", "Asia/Seoul")))

    @property
    def schema_version(self) -> str:
        return str(self.cfg.get("schema_version", "1"))

    def archive_date(self, now: datetime) -> date:
        """저장 날짜 = 저장 시각을 설정 시간대로 본 날짜 (기본 KST)."""
        return now.astimezone(self.tz).date()

    def due(self, now: datetime) -> bool:
        """정기 저장 시각이 지났고 오늘 저장본이 아직 없으면 참. 주말은 weekdays_only 면 건너뛴다."""
        local = now.astimezone(self.tz)
        if not is_snapshot_day(local.date(), self.cfg):
            return False
        hh, mm = (int(x) for x in str(self.cfg.get("archive_time", "07:30")).split(":"))
        return local.time() >= time(hh, mm) and not self.store.exists(local.date())

    # ── 읽기 ──────────────────────────────────────────────
    def list_dates(self) -> list[str]:
        return [d.isoformat() for d in self.store.dates()]

    def index(self) -> list[dict[str, Any]]:
        return self.store.index()

    def get(self, d: date | str) -> dict[str, Any]:
        if isinstance(d, str):
            from .store import parse_date
            d = parse_date(d)
        return self.store.read(d)

    def latest(self) -> dict[str, Any]:
        ds = self.store.dates()
        if not ds:
            raise ArchiveNotFoundError("저장된 화면이 아직 없습니다")
        return self.store.read(ds[0])

    def nearest(self, d: date, k: int = 1) -> dict[str, list[str]]:
        """없는 날짜를 골랐을 때 보여 줄 가장 가까운 앞·뒤 저장일."""
        ds = sorted(self.store.dates())
        before = [x.isoformat() for x in ds if x < d][-k:][::-1]
        after = [x.isoformat() for x in ds if x > d][:k]
        return {"before": before, "after": after}

    # ── 저장 ──────────────────────────────────────────────
    def build(self, *, now: datetime | None = None, collectors: Mapping[str, Collector] | None = None,
              created_by: str | None = None, generated_at_basis: str = "capture_time", origin: str = "daily_archive",
              cutoff: datetime | None = None, check_future: bool = False, created_at: datetime | None = None,
              extra_meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """섹션을 모아 저장본 사전을 만든다(아직 쓰지 않는다).

        now        그날 화면의 기준 시각(= 데이터 cutoff). 저장 날짜는 이것의 KST 날짜다.
        cutoff     과거 재구성이면 그 cutoff. check_future 면 cutoff 뒤의 데이터 시각을 가진 섹션을 빼고 FUTURE_DATA 로 남긴다.
        origin     daily_archive(정기) · latest_update(오늘 최신) · historical_backfill(과거 재구성) · capture_import(커밋된 캡처)
        """
        now = now or datetime.now(timezone.utc)
        cutoff = cutoff or now
        created_at = created_at or datetime.now(timezone.utc)
        status: dict[str, str] = {}
        cols = dict(collectors or self.collectors)
        sections: list[str] = list(self.cfg.get("sections") or [])
        required = set(self.cfg.get("required") or ["snapshot"])
        payload: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for name in sections:
            fn = cols.get(name)
            if fn is None:
                payload[name] = None
                errors[name] = "NOT ARCHIVED · 이 저장 경로에서 모으지 않는 섹션"
                continue
            try:
                payload[name] = to_jsonable(fn())
            except NotAvailableHistorically as exc:
                payload[name] = None
                errors[name] = f"NOT_AVAILABLE_HISTORICALLY: {exc}"[:500]
                status[name] = "NOT_AVAILABLE_HISTORICALLY"
            except Exception as exc:  # 섹션 하나의 실패가 저장 전체를 막지 않는다
                logger.exception("archive 섹션 %s 수집 실패", name)
                payload[name] = None
                errors[name] = f"{type(exc).__name__}: {exc}"[:500]
        if check_future:  # look-ahead 검증 — 미래 데이터 시각이 하나라도 있으면 그 섹션을 넣지 않는다
            for name in sections:
                if payload.get(name) is None:
                    continue
                bad = future_data_paths(payload[name], cutoff, path=name)
                if bad:
                    if name in required:
                        raise ArchiveCaptureError(f"필수 섹션 {name} 에 cutoff({cutoff.isoformat()}) 뒤 데이터가 있어 저장하지 않습니다: {bad[:3]}")
                    payload[name] = None
                    errors[name] = f"FUTURE_DATA: cutoff 뒤 데이터 시각 {len(bad)}곳 — {bad[:3]}"[:500]
                    status[name] = "FUTURE_DATA_REMOVED"
        for name in required:
            if payload.get(name) is None:
                raise ArchiveCaptureError(f"필수 섹션 {name} 을 모으지 못해 저장하지 않습니다 — {errors.get(name, 'empty')}")

        snap = payload["snapshot"]
        source_asof = snap.get("as_of")
        consistency = self._consistency(payload, source_asof, set(self.cfg.get("as_of_independent") or []), set(self.cfg.get("as_of_windowed") or []), float(self.cfg.get("as_of_window_sec", 900)))
        for name in consistency["mismatched"]:
            errors.setdefault(name, f"as_of 불일치 — snapshot {source_asof} · {name} {consistency['as_of'][name]}")
        health = snap.get("data_health") or {}
        d = self.archive_date(now)
        gen = now if origin == "capture_import" else created_at  # 가져온 캡처는 생성 시각을 모르므로 데이터 기준 시각(basis 에 적는다)
        return {
            "schema_version": self.schema_version,
            "snapshot_date": d.isoformat(),
            "cutoff": cutoff.astimezone(self.tz).isoformat(),
            "generated_at": gen.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "archive_status": "PARTIAL" if errors else "COMPLETE",
            **payload,
            "llm_commentary": llm_commentary_of(payload),
            "errors": errors,
            "meta": {
                "created_at": created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "archive_origin": origin,
                "is_weekend": d.weekday() >= 5,
                "data_mode": snap.get("mode") or health.get("mode"),
                "scenario": snap.get("scenario"),
                "coverage": health.get("coverage"),
                "available_instruments": health.get("available_instruments"),
                "expected_instruments": health.get("expected_instruments"),
                "news_judgment": health.get("news_judgment"),
                "source_asof": source_asof,
                "created_by": created_by or self.created_by,
                "generated_at_basis": generated_at_basis,
                "timezone": str(self.tz),
                "archive_time": self.cfg.get("archive_time"),
                "sections": {n: status.get(n) or ("OK" if payload.get(n) is not None and n not in errors else "MISSING" if payload.get(n) is None else "MISMATCH") for n in sections},
                "consistency": consistency,
                "corrections": [],
                **dict(extra_meta or {}),
            },
        }

    def capture(self, *, now: datetime | None = None, collectors: Mapping[str, Collector] | None = None,
                created_by: str | None = None, generated_at_basis: str = "capture_time", origin: str = "daily_archive",
                cutoff: datetime | None = None, check_future: bool = False, extra_meta: Mapping[str, Any] | None = None) -> CaptureResult:
        """저장. 토·일(휴장일 설정 포함)이면 만들지 않고 SKIPPED, 같은 날짜가 있으면 아무것도 모으지 않고 EXISTS — 기존 파일은 그대로."""
        now = now or datetime.now(timezone.utc)
        d = self.archive_date(now)
        why = skip_reason(d, self.cfg)
        if why:
            logger.info("%s SKIPPED - %s", d.isoformat(), why)
            return CaptureResult(f"SKIPPED_{why}", d.isoformat(), self.store.path_for(d))
        if self.store.exists(d):
            return CaptureResult("EXISTS", d.isoformat(), self.store.path_for(d))
        payload = self.build(now=now, collectors=collectors, created_by=created_by, generated_at_basis=generated_at_basis,
                             origin=origin, cutoff=cutoff, check_future=check_future, extra_meta=extra_meta)
        try:
            path = self.store.write_new(d, payload)
        except ArchiveExistsError:
            return CaptureResult("EXISTS", d.isoformat(), self.store.path_for(d))
        return CaptureResult("WRITTEN", d.isoformat(), path, payload["archive_status"], dict(payload["errors"]))

    def correct(self, d: date, payload: dict[str, Any], *, reason: str, by: str) -> tuple[Path, Path]:
        """명시적 correction. 이유·작성자·이전 파일 경로를 meta.corrections 에 남긴다."""
        if not reason.strip():
            raise ValueError("correction 에는 이유가 필요합니다")
        old = self.store.read(d)
        payload = dict(payload)
        payload["snapshot_date"] = d.isoformat()
        payload.setdefault("schema_version", self.schema_version)
        meta = dict(payload.get("meta") or {})
        prior = list((old.get("meta") or {}).get("corrections") or [])
        entry = {"at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "reason": reason, "by": by,
                 "previous_generated_at": old.get("generated_at")}
        meta["corrections"] = prior + [entry]
        payload["meta"] = meta
        final, keep = self.store.replace_for_correction(d, payload)
        return final, keep

    @staticmethod
    def _consistency(payload: dict[str, Any], source_asof: Any, independent: set[str], windowed: set[str], window_sec: float) -> dict[str, Any]:
        """같은 snapshot 위에서 계산한 섹션은 as_of 가 같아야 한다. 자기 시각을 갖는 섹션은 snapshot 뒤 window 안이어야 한다."""
        base = _parse_ts(source_asof)
        as_of: dict[str, Any] = {}
        mismatched: list[str] = []
        for name, value in payload.items():
            if name == "snapshot" or not isinstance(value, dict) or "as_of" not in value:
                continue
            as_of[name] = value.get("as_of")
            t = _parse_ts(value.get("as_of"))
            if base is None or t is None:
                continue
            gap = (t - base).total_seconds()
            if name in independent:
                continue
            if name in windowed:
                if not -1 <= gap <= window_sec:
                    mismatched.append(name)
            elif abs(gap) > 1:
                mismatched.append(name)
        return {"ok": not mismatched, "source_asof": source_asof, "as_of": as_of, "mismatched": mismatched}


def llm_commentary_of(payload: Mapping[str, Any]) -> dict[str, Any]:
    """그날 화면의 LLM 해석 문구를 한곳에 모은다 — 저장본을 열 때 LLM 을 다시 부르지 않는다(문구는 각 섹션에 그대로 있고 이것은 색인)."""
    out: dict[str, Any] = {}
    rr = payload.get("rates_regime") or {}
    top = rr.get("top") or {}
    if top.get("market_read"):
        out["rates_market_read"] = {"text": top.get("market_read"), "meta": top.get("market_read_meta")}
    im = rr.get("inflation_map") or {}
    if im.get("read"):
        out["inflation_read"] = {"text": im.get("read"), "meta": im.get("read_meta")}
    snap = payload.get("snapshot") or {}
    health = snap.get("data_health") or {}
    out["news_judgment"] = {"mode": health.get("news_judgment"), "note": health.get("news_judgment_note"), "llm_status": health.get("llm_status")}
    return out
