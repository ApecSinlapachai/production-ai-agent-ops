"""IP-hashed (SHA-256) sliding-window rate limiter for proxy-safe Free-Tier protection."""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request


def extract_client_ip(request: Request) -> str:
    """Extract client IP using the first hop of X-Forwarded-For behind Render/Vercel proxies."""
    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def hash_client_ip(raw_ip: str) -> str:
    """Return a SHA-256 digest so raw client IPs are never stored in memory or logs."""
    return hashlib.sha256(raw_ip.encode("utf-8")).hexdigest()


class SlidingWindowRateLimiter:
    """Thread-safe in-memory per-minute and per-day sliding-window rate limiter."""

    def __init__(
        self,
        *,
        per_minute: int,
        per_day: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._per_minute = per_minute
        self._per_day = per_day
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = {}

    def check_and_record(self, ip_hash: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds) and record the request timestamp if allowed."""
        with self._lock:
            now = self._clock()
            day_cutoff = now - 86400.0
            minute_cutoff = now - 60.0

            timestamps = self._windows.setdefault(ip_hash, deque())
            while timestamps and timestamps[0] <= day_cutoff:
                timestamps.popleft()

            if len(timestamps) >= self._per_day:
                retry_after = max(1, math.ceil(timestamps[0] + 86400.0 - now))
                return False, retry_after

            minute_timestamps = [ts for ts in timestamps if ts > minute_cutoff]
            if len(minute_timestamps) >= self._per_minute:
                retry_after = max(1, math.ceil(minute_timestamps[0] + 60.0 - now))
                return False, retry_after

            timestamps.append(now)
            return True, 0
