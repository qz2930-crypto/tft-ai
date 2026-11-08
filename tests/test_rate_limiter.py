"""RateLimiter behaviour. / 限速器行为测试。"""

import time

from tft_tool.ingest.riot_client import RateLimiter


def test_limiter_blocks_after_burst() -> None:
    rl = RateLimiter([(3, 0.5)])  # 3 calls per 0.5 s
    t0 = time.monotonic()
    for _ in range(3):
        rl.acquire()
    assert time.monotonic() - t0 < 0.1  # burst is free
    rl.acquire()  # 4th must wait for window
    assert time.monotonic() - t0 >= 0.45
