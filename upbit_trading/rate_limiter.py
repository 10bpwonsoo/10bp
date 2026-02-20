"""Upbit API 공유 Rate Limiter

여러 전략/엔진이 동시에 Upbit API를 호출할 때
초당 요청 수를 제한하여 429 에러를 방지한다.
"""

import threading
import time
from collections import deque


class UpbitRateLimiter:
    """슬라이딩 윈도우 기반 API 호출 속도 제한기

    Args:
        max_per_sec: 초당 최대 허용 요청 수 (기본 8)
    """

    def __init__(self, max_per_sec: int = 8):
        self._max_per_sec = max_per_sec
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self):
        """요청 슬롯을 획득한다. 한도 초과 시 필요한 만큼 대기한다."""
        with self._lock:
            now = time.monotonic()
            # 1초 이전의 타임스탬프 제거
            while self._timestamps and self._timestamps[0] <= now - 1.0:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max_per_sec:
                # 가장 오래된 요청이 1초가 될 때까지 대기
                wait = 1.0 - (now - self._timestamps[0])
                if wait > 0:
                    time.sleep(wait)
                # 대기 후 다시 정리
                now = time.monotonic()
                while self._timestamps and self._timestamps[0] <= now - 1.0:
                    self._timestamps.popleft()

            self._timestamps.append(time.monotonic())

    @property
    def available(self) -> int:
        """현재 사용 가능한 요청 슬롯 수"""
        with self._lock:
            now = time.monotonic()
            while self._timestamps and self._timestamps[0] <= now - 1.0:
                self._timestamps.popleft()
            return max(0, self._max_per_sec - len(self._timestamps))
