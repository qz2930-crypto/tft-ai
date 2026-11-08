"""Match collection pipeline (M2). / 对局采集流程。

Three idempotent stages / 三个可重复执行的阶段:
    1. players  — ladder (GM + Challenger) → puuids into index
    2. ids      — per player, recent match ids → index (pending)
    3. matches  — fetch each pending match, filter, write JSON, mark done

Raw files land at ``data/raw/{set}/{patch}/{match_id}.json``. Patch is inferred
from ``game_datetime`` (see ``SetConfig.patch_for``) because ``game_version`` is a
placeholder in Unreal-era data.
原始文件写入 ``data/raw/{set}/{patch}/{match_id}.json``；版本由对局时间推断。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from rich.progress import Progress

from tft_tool.common.settings import load_config, load_secrets
from tft_tool.ingest.index import IngestIndex
from tft_tool.ingest.riot_client import RiotAPIError, RiotClient

log = logging.getLogger(__name__)


def raw_path(set_number: int, patch: str, match_id: str) -> Path:
    cfg = load_config()
    return cfg.paths.resolve("raw") / str(set_number) / patch / f"{match_id}.json"


class Collector:
    def __init__(self, client: RiotClient | None = None, index: IngestIndex | None = None) -> None:
        self.cfg = load_config()
        self.sec = load_secrets()
        self.client = client or RiotClient()
        self.index = index or IngestIndex()

    # ---- stage 1 ---------------------------------------------------------
    def collect_players(self) -> int:
        total = 0
        for tier in self.cfg.ingest.tiers:
            ladder = self.client.ladder(tier, self.cfg.ingest.queue)
            entries = ladder.get("entries", [])
            for e in entries:
                e["tier"] = ladder.get("tier", tier)
            n = self.index.upsert_players(entries, self.sec.riot_platform)
            log.info("%s: %d players", tier, n)
            total += n
        return total

    # ---- stage 2 ---------------------------------------------------------
    def collect_match_ids(self, per_player: int | None = None) -> int:
        per_player = per_player or self.cfg.ingest.matches_per_player
        puuids = self.index.puuids()
        added = 0
        with Progress() as prog:
            task = prog.add_task("match ids", total=len(puuids))
            for puuid in puuids:
                try:
                    ids = self.client.match_ids(puuid, count=min(per_player, 200))
                    added += self.index.add_match_ids(ids)
                except RiotAPIError as exc:
                    log.warning("match_ids failed for %s…: %s", puuid[:8], exc)
                    if exc.status == 403:
                        raise
                prog.advance(task)
        log.info("new match ids: %d", added)
        return added

    # ---- stage 3 ---------------------------------------------------------
    def _accept(self, info: dict[str, Any]) -> tuple[bool, str | None, str]:
        """Return (accept, patch, reason). / 过滤：排位 + 当前赛季 + 已知版本。"""
        if info.get("queue_id") != self.cfg.ingest.queue_id:
            return False, None, f"queue_id={info.get('queue_id')}"
        if info.get("tft_set_number") != self.cfg.set.id:
            return False, None, f"set={info.get('tft_set_number')}"
        patch = self.cfg.set.patch_for(int(info.get("game_datetime", 0)))
        if patch is None:
            return False, None, "before first known patch"
        return True, patch, "ok"

    def collect_matches(self, limit: int | None = None) -> dict[str, int]:
        pending = self.index.pending(limit)
        stats = {"done": 0, "skipped": 0, "error": 0}
        with Progress() as prog:
            task = prog.add_task("matches", total=len(pending))
            for mid in pending:
                try:
                    m = self.client.match(mid)
                except RiotAPIError as exc:
                    self.index.mark(mid, "error", error=str(exc)[:200])
                    stats["error"] += 1
                    if exc.status == 403:
                        raise
                    prog.advance(task)
                    continue
                info = m.get("info", {})
                ok, patch, reason = self._accept(info)
                if not ok:
                    self.index.mark(
                        mid, "skipped", set_number=info.get("tft_set_number"),
                        queue_id=info.get("queue_id"), error=reason,
                    )
                    stats["skipped"] += 1
                    prog.advance(task)
                    continue
                assert patch is not None
                dest = raw_path(self.cfg.set.id, patch, mid)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
                self.index.mark(
                    mid, "done", set_number=self.cfg.set.id, patch=patch,
                    game_datetime=info.get("game_datetime"), queue_id=info.get("queue_id"),
                )
                stats["done"] += 1
                prog.advance(task)
        log.info("matches: %s", stats)
        return stats

    # ---- all -------------------------------------------------------------
    def run(self, limit: int | None = None) -> None:
        self.collect_players()
        self.collect_match_ids()
        self.collect_matches(limit)
