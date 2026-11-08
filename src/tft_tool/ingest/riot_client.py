"""Minimal Riot TFT API client with rate limiting. / 带限速的 Riot TFT API 客户端。

Endpoints covered (read-only) / 覆盖的只读端点:
    tft-league-v1   challenger / grandmaster / master ladders
    tft-match-v1    match ids by puuid, match by id

Rate limiting is a dual token bucket (per-second and per-two-minutes) that
mirrors the dev-key defaults; 429 responses honour ``Retry-After``.
限速采用双令牌桶（每秒 / 每两分钟），429 时按 Retry-After 退避。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

import httpx

from tft_tool.common.settings import load_config, load_secrets

log = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window limiter for N calls per window. / 滑动窗口限速。"""

    def __init__(self, limits: list[tuple[int, float]]) -> None:
        # limits: [(max_calls, window_seconds), ...]
        self._limits = limits
        self._hist: list[deque[float]] = [deque() for _ in limits]
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                wait = 0.0
                for (max_calls, window), hist in zip(self._limits, self._hist, strict=True):
                    while hist and now - hist[0] >= window:
                        hist.popleft()
                    if len(hist) >= max_calls:
                        wait = max(wait, window - (now - hist[0]) + 0.01)
                if wait == 0.0:
                    for hist in self._hist:
                        hist.append(now)
                    return
            time.sleep(wait)


class RiotAPIError(RuntimeError):
    def __init__(self, status: int, url: str, body: str) -> None:
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")
        self.status = status


class RiotClient:
    """Thin synchronous client. / 轻量同步客户端。"""

    def __init__(
        self,
        api_key: str | None = None,
        platform: str | None = None,
        region: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        sec = load_secrets()
        cfg = load_config()
        self.api_key = api_key or sec.riot_api_key
        if not self.api_key:
            raise RuntimeError("RIOT_API_KEY is not set (see .env.example) / 未设置 RIOT_API_KEY")
        self.platform = platform or sec.riot_platform
        self.region = region or sec.riot_region
        rl = cfg.ingest.rate_limit
        self._limiter = RateLimiter([(rl.per_second, 1.0), (rl.per_two_minutes, 120.0)])
        self._http = httpx.Client(timeout=timeout, headers={"X-Riot-Token": self.api_key})

    # ---- low level -------------------------------------------------------

    def _get(self, url: str, params: dict[str, Any] | None = None, retries: int = 5) -> Any:
        for attempt in range(retries):
            self._limiter.acquire()
            resp = self._http.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                log.warning("429 rate limited; sleeping %.1fs", retry_after)
                time.sleep(retry_after)
                continue
            if resp.status_code in (500, 502, 503, 504):
                backoff = 2**attempt
                log.warning("%s from Riot; retry in %ss", resp.status_code, backoff)
                time.sleep(backoff)
                continue
            if resp.status_code == 403:
                msg = "Forbidden — API key expired or invalid? / 密钥过期或无效"
                raise RiotAPIError(403, url, msg)
            raise RiotAPIError(resp.status_code, url, resp.text)
        raise RiotAPIError(599, url, "retries exhausted / 重试耗尽")

    @property
    def _platform_base(self) -> str:
        return f"https://{self.platform}.api.riotgames.com"

    @property
    def _region_base(self) -> str:
        return f"https://{self.region}.api.riotgames.com"

    # ---- tft-league-v1 ---------------------------------------------------

    def ladder(self, tier: str, queue: str = "RANKED_TFT") -> dict[str, Any]:
        """Return the ladder for CHALLENGER / GRANDMASTER / MASTER. / 返回高分段榜单。"""
        tier_path = {"CHALLENGER": "challenger", "GRANDMASTER": "grandmaster", "MASTER": "master"}[
            tier.upper()
        ]
        return self._get(f"{self._platform_base}/tft/league/v1/{tier_path}", {"queue": queue})

    # ---- tft-match-v1 ----------------------------------------------------

    def match_ids(self, puuid: str, count: int = 20, start: int = 0) -> list[str]:
        return self._get(
            f"{self._region_base}/tft/match/v1/matches/by-puuid/{puuid}/ids",
            {"count": count, "start": start},
        )

    def match(self, match_id: str) -> dict[str, Any]:
        return self._get(f"{self._region_base}/tft/match/v1/matches/{match_id}")

    def close(self) -> None:
        self._http.close()
