"""SQLite bookkeeping for resumable collection. / 采集进度索引（可断点续传）。

Tables / 表:
    players(puuid, tier, league_points, wins, losses, platform, fetched_at)
    match_index(match_id, status, set_number, patch, game_datetime, queue_id,
                error, discovered_at, fetched_at)

``status``: pending → done | skipped (wrong queue/set) | error
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

from tft_tool.common.settings import load_config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    puuid TEXT PRIMARY KEY,
    tier TEXT,
    league_points INTEGER,
    wins INTEGER,
    losses INTEGER,
    platform TEXT,
    fetched_at REAL
);
CREATE TABLE IF NOT EXISTS match_index (
    match_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    set_number INTEGER,
    patch TEXT,
    game_datetime INTEGER,
    queue_id INTEGER,
    error TEXT,
    discovered_at REAL,
    fetched_at REAL
);
CREATE INDEX IF NOT EXISTS ix_match_status ON match_index(status);
CREATE INDEX IF NOT EXISTS ix_match_patch ON match_index(patch);
"""


class IngestIndex:
    def __init__(self, path: Path | None = None) -> None:
        cfg = load_config()
        self.path = path or cfg.paths.resolve("processed") / "ingest_index.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)

    # ---- players ---------------------------------------------------------
    def upsert_players(self, rows: Iterable[dict], platform: str) -> int:
        now = time.time()
        data = [
            (
                r["puuid"],
                r.get("tier"),
                r.get("leaguePoints"),
                r.get("wins"),
                r.get("losses"),
                platform,
                now,
            )
            for r in rows
            if r.get("puuid")
        ]
        self.conn.executemany(
            """INSERT INTO players VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(puuid) DO UPDATE SET tier=excluded.tier,
               league_points=excluded.league_points, wins=excluded.wins,
               losses=excluded.losses, fetched_at=excluded.fetched_at""",
            data,
        )
        self.conn.commit()
        return len(data)

    def puuids(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT puuid FROM players")]

    # ---- match ids -------------------------------------------------------
    def add_match_ids(self, ids: Iterable[str]) -> int:
        now = time.time()
        cur = self.conn.executemany(
            "INSERT OR IGNORE INTO match_index(match_id, discovered_at) VALUES (?, ?)",
            [(m, now) for m in ids],
        )
        self.conn.commit()
        return cur.rowcount if cur.rowcount is not None else 0

    @staticmethod
    def _id_num(match_id: str) -> int:
        """Numeric part of 'NA1_5676033029' (monotonic ≈ game time). / 对局 ID 数字部分。"""
        try:
            return int(match_id.split("_", 1)[1])
        except (IndexError, ValueError):
            return 0

    def pending(self, limit: int | None = None, newest_first: bool = True) -> list[str]:
        ids = [r[0] for r in self.conn.execute(
            "SELECT match_id FROM match_index WHERE status='pending'")]
        ids.sort(key=self._id_num, reverse=newest_first)
        return ids[:limit] if limit else ids

    def min_done_id(self, patch: str) -> int | None:
        """Smallest numeric id among done matches of a patch. / 某版本已下载对局的最小 ID。"""
        rows = self.conn.execute(
            "SELECT match_id FROM match_index WHERE status='done' AND patch=?", (patch,)
        ).fetchall()
        nums = [self._id_num(r[0]) for r in rows]
        return min(nums) if nums else None

    def prune_pending_before(self, threshold: int, reason: str) -> int:
        """Mark pending ids numerically below threshold as skipped. / 清理旧 pending。"""
        ids = [m for m in self.pending(newest_first=False) if self._id_num(m) < threshold]
        self.conn.executemany(
            "UPDATE match_index SET status='skipped', error=?, fetched_at=? WHERE match_id=?",
            [(reason, time.time(), m) for m in ids],
        )
        self.conn.commit()
        return len(ids)

    def mark(
        self,
        match_id: str,
        status: str,
        *,
        set_number: int | None = None,
        patch: str | None = None,
        game_datetime: int | None = None,
        queue_id: int | None = None,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """UPDATE match_index SET status=?, set_number=?, patch=?, game_datetime=?,
               queue_id=?, error=?, fetched_at=? WHERE match_id=?""",
            (status, set_number, patch, game_datetime, queue_id, error, time.time(), match_id),
        )
        self.conn.commit()

    # ---- reporting -------------------------------------------------------
    def status_counts(self) -> dict[str, int]:
        return dict(self.conn.execute("SELECT status, COUNT(*) FROM match_index GROUP BY status"))

    def patch_counts(self) -> dict[str, int]:
        return dict(
            self.conn.execute(
                "SELECT COALESCE(patch,'?'), COUNT(*) FROM match_index "
                "WHERE status='done' GROUP BY patch ORDER BY patch"
            )
        )

    def n_players(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
