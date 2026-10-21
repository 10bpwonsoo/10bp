"""
Daily Full Dashboard Archive API (2026-10-21) — 읽기 전용.

과거 날짜 화면은 저장된 JSON 을 그대로 돌려준다. 다시 계산하지 않고, 없는 섹션을 지금 값으로 메우지 않는다.
저장(capture)은 HTTP 로 열지 않는다 — 브라우저 사용자가 저장본을 만들거나 덮어쓸 길이 없다. 저장은 CLI·스케줄러만:
    python -m marketpulse.archive capture --if-due
"""

from __future__ import annotations

from typing import Any

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


@router.get("/dates", response_model=list[str])
def archive_dates() -> list[str]:
    """저장된 날짜, 최신순."""
    return get_archive_service().list_dates()


@router.get("/index")
def archive_index() -> list[dict[str, Any]]:
    """날짜별 요약(최신순) — archive_status(COMPLETE/PARTIAL) · source_asof · 빠진 섹션. 날짜 선택 UI 가 쓴다."""
    return get_archive_service().index()


@router.get("/latest")
def archive_latest() -> dict[str, Any]:
    """가장 최근 저장본."""
    try:
        return get_archive_service().latest()
    except ArchiveNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{snapshot_date}")
def archive_get(snapshot_date: str) -> dict[str, Any]:
    """그날 저장된 화면 전체. 없으면 404 와 가장 가까운 저장일."""
    svc = get_archive_service()
    try:
        d = parse_date(snapshot_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return svc.get(d)
    except ArchiveNotFoundError:
        near = svc.nearest(d)
        raise HTTPException(status_code=404, detail={"message": f"{d.isoformat()} 저장 화면이 없습니다", "date": d.isoformat(), "nearest": near})
