"""
Daily Full Dashboard Archive API (2026-10-21) — 읽기 전용.

과거 날짜 화면은 저장된 JSON 을 돌려준다. 다시 계산하지 않고, 없는 섹션을 지금 값으로 메우지 않는다.
예외 하나 (2026-10-21): history 섹션의 날짜 기준. 예전 저장본은 저장 키(UTC 날짜)로 날짜가 붙고 장중 LIVE 가 daily 띠에 들어 있어,
읽을 때 KST Daily Snapshot 날짜 view 로 바꿔 보낸다(history/legacy_view.py — 날짜별 값은 그대로, 파일도 그대로). ?view=stored 면 파일 그대로.
저장(capture)은 HTTP 로 열지 않는다 — 브라우저 사용자가 저장본을 만들거나 덮어쓸 길이 없다. 저장은 CLI·스케줄러만:
    python -m marketpulse.archive capture --if-due
"""

from __future__ import annotations

from typing import Any

from datetime import datetime

from fastapi import APIRouter, HTTPException

from ...archive import ArchiveNotFoundError, DailyArchiveService, default_service
from ...archive.store import parse_date

router = APIRouter(prefix="/api/v1/archive", tags=["archive"])

_svc: DailyArchiveService | None = None


def get_archive_service() -> DailyArchiveService:
    global _svc
    if _svc is None:
        _svc = default_service()
    return _svc


def use_archive_service(svc: DailyArchiveService | None) -> None:
    """테스트가 저장소를 바꿔 끼운다."""
    global _svc
    _svc = svc


_rows_of = None


def use_history_rows(rows_of) -> None:
    """테스트가 history 저장소(tab → {저장 키: snapshot})를 바꿔 끼운다."""
    global _rows_of
    _rows_of = rows_of


def history_view(doc: dict[str, Any], view: str = "kst") -> dict[str, Any]:
    """history 섹션만 KST snapshot 날짜 view 로. view='stored' 면 파일 그대로."""
    if view == "stored":
        return doc
    from ...history.legacy_view import store_rows_of, upgrade_sections
    rows_of = _rows_of
    if rows_of is None:  # 요청마다 읽는다 — 저장소는 매일 늘어난다
        from ...config.settings import get_settings
        from ...history.manager import DailySnapshotManager
        from ...history.store import JsonDirStore
        rows_of = store_rows_of(DailySnapshotManager(JsonDirStore(get_settings().history_dir)))
    src = (doc.get("meta") or {}).get("source_asof")
    live = datetime.fromisoformat(str(src).replace("Z", "+00:00")) if src else None
    return upgrade_sections(doc, live_asof=live, rows_of=rows_of)


@router.get("/dates", response_model=list[str])
def archive_dates() -> list[str]:
    """저장된 날짜, 최신순."""
    return get_archive_service().list_dates()


@router.get("/index")
def archive_index() -> list[dict[str, Any]]:
    """날짜별 요약(최신순) — archive_status(COMPLETE/PARTIAL) · source_asof · 빠진 섹션. 날짜 선택 UI 가 쓴다."""
    return get_archive_service().index()


@router.get("/latest")
def archive_latest(view: str = "kst") -> dict[str, Any]:
    """가장 최근 저장본."""
    try:
        return history_view(get_archive_service().latest(), view)
    except ArchiveNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{snapshot_date}")
def archive_get(snapshot_date: str, view: str = "kst") -> dict[str, Any]:
    """그날 저장된 화면 전체. 없으면 404 와 가장 가까운 저장일."""
    svc = get_archive_service()
    try:
        d = parse_date(snapshot_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        doc = svc.get(d)
    except ArchiveNotFoundError:
        near = svc.nearest(d)
        raise HTTPException(status_code=404, detail={"message": f"{d.isoformat()} 저장 화면이 없습니다", "date": d.isoformat(), "nearest": near})
    return history_view(doc, view)
