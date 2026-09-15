"""분석 실행 로그.

원인 추적을 위해 데이터 로딩·분석 실행 내역을 파일과 화면에 남긴다.
외부 telemetry 는 사용하지 않는다. 로그는 전부 로컬 파일이다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

_CONFIGURED = set()


def get_logger(name: str = "performance_monitor",
               log_dir: str | Path | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _CONFIGURED:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    if log_dir is not None:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(
            directory / f"{datetime.now():%Y%m}.log", encoding="utf-8"
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)

    logger.propagate = False
    _CONFIGURED.add(name)
    return logger


class RunLog:
    """화면에도 보여줄 수 있도록 메시지를 모아두는 얇은 래퍼."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.lines: list[str] = []

    def info(self, message: str) -> None:
        self.logger.info(message)
        self.lines.append(f"{datetime.now():%Y-%m-%d %H:%M} | {message}")

    def warning(self, message: str) -> None:
        self.logger.warning(message)
        self.lines.append(f"{datetime.now():%Y-%m-%d %H:%M} | [WARN] {message}")

    def error(self, message: str) -> None:
        self.logger.error(message)
        self.lines.append(f"{datetime.now():%Y-%m-%d %H:%M} | [ERROR] {message}")

    def text(self) -> str:
        return "\n".join(self.lines)
