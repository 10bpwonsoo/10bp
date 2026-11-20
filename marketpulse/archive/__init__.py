"""Daily Full Dashboard Archive — 그날 화면 전체를 재현하는 날짜별 JSON 저장본 (2026-10-21). 기존 daily history 위에 얹는다."""

from .service import ArchiveCaptureError, CaptureResult, DailyArchiveService, load_archive_config
from .store import ArchiveExistsError, ArchiveNotFoundError, ArchiveStore

__all__ = ["ArchiveCaptureError", "ArchiveExistsError", "ArchiveNotFoundError", "ArchiveStore", "CaptureResult", "DailyArchiveService", "load_archive_config"]


def default_service() -> DailyArchiveService:
    from ..config.settings import get_settings
    return DailyArchiveService(ArchiveStore(get_settings().archive_dir))
