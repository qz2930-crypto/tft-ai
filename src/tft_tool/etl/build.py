"""Raw match JSON → normalised Parquet tables → DuckDB views (M3). / 建表。

Layout / 目录:
    data/raw/{set}/{patch}/*.json              (input, from M2)
    data/processed/{set}/{patch}/{table}.parquet
    data/processed/tft.duckdb                  (views over all patches)

Rebuild is per patch and idempotent; it is fast enough (≈1–2 min / 30k files) that we
don't track per-file state. 每个版本整体重建，幂等。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import polars as pl
from pydantic import ValidationError
from rich.progress import track

from tft_tool.common.settings import load_config
from tft_tool.etl.schema import Match

log = logging.getLogger(__name__)

TABLES = ("matches", "participants", "units", "unit_items", "traits")


@dataclass
class Rows:
    matches: list[dict] = field(default_factory=list)
    participants: list[dict] = field(default_factory=list)
    units: list[dict] = field(default_factory=list)
    unit_items: list[dict] = field(default_factory=list)
    traits: list[dict] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


def _level_bucket(level: int, buckets: list[list[int]]) -> str:
    for lo, hi in buckets:
        if lo <= level <= hi:
            return f"{lo}" if lo == hi else (f"≤{hi}" if lo <= 1 else f"{lo}+")
    return "?"


def flatten(match: Match, patch: str) -> Rows:
    """One match → rows for every table. / 单局展开。"""
    cfg = load_config()
    r = Rows()
    mid = match.metadata.match_id
    info = match.info
    r.matches.append(
        {
            "match_id": mid,
            "set_number": info.tft_set_number,
            "patch": patch,
            "game_datetime": info.game_datetime,
            "game_length": info.game_length,
            "queue_id": info.queue_id,
            "tft_game_type": info.tft_game_type,
        }
    )
    for p in info.participants:
        stage, rnd = cfg.rounds.label(p.last_round)
        r.participants.append(
            {
                "match_id": mid,
                "patch": patch,
                "puuid": p.puuid,
                "placement": p.placement,
                "level": p.level,
                "level_bucket": _level_bucket(p.level, cfg.analysis.level_buckets),
                "last_round": p.last_round,
                "stage": stage,
                "stage_round": f"{stage}-{rnd}",
                "gold_left": p.gold_left,
                "players_eliminated": p.players_eliminated,
                "total_damage_to_players": p.total_damage_to_players,
                "time_eliminated": p.time_eliminated,
                "is_top4": p.placement <= 4,
                "is_win": p.placement == 1,
                "n_units": len(p.units),
                "n_items": sum(len(u.itemNames) for u in p.units),
            }
        )
        for i, u in enumerate(p.units):
            r.units.append(
                {
                    "match_id": mid,
                    "patch": patch,
                    "puuid": p.puuid,
                    "unit_idx": i,
                    "character_id": u.character_id,
                    "tier": u.tier,
                    "rarity": u.rarity,
                    "n_items": len(u.itemNames),
                }
            )
            for slot, item in enumerate(u.itemNames):
                r.unit_items.append(
                    {
                        "match_id": mid,
                        "patch": patch,
                        "puuid": p.puuid,
                        "unit_idx": i,
                        "character_id": u.character_id,
                        "tier": u.tier,
                        "slot": slot,
                        "item": item,
                    }
                )
        for t in p.traits:
            r.traits.append(
                {
                    "match_id": mid,
                    "patch": patch,
                    "puuid": p.puuid,
                    "trait": t.name,
                    "num_units": t.num_units,
                    "style": t.style,
                    "tier_current": t.tier_current,
                    "tier_total": t.tier_total,
                }
            )
    return r


def build_patch(set_number: int, patch: str) -> dict[str, int]:
    """Parse every raw file for a patch and write Parquet tables. / 构建一个版本。"""
    cfg = load_config()
    src = cfg.paths.resolve("raw") / str(set_number) / patch
    files = sorted(src.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no raw matches under {src}")
    acc = Rows()
    for f in track(files, description=f"etl {patch}"):
        try:
            m = Match.model_validate(json.loads(f.read_text(encoding="utf-8")))
        except (ValidationError, json.JSONDecodeError, OSError) as exc:
            acc.errors.append((f.name, str(exc)[:160]))
            continue
        rows = flatten(m, patch)
        for t in TABLES:
            getattr(acc, t).extend(getattr(rows, t))

    out = cfg.paths.resolve("processed") / str(set_number) / patch
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for t in TABLES:
        df = pl.DataFrame(getattr(acc, t))
        df.write_parquet(out / f"{t}.parquet")
        counts[t] = df.height
    counts["errors"] = len(acc.errors)
    if acc.errors:
        (out / "errors.log").write_text(
            "\n".join(f"{n}\t{e}" for n, e in acc.errors), encoding="utf-8"
        )
    log.info("%s: %s", patch, counts)
    return counts


def refresh_duckdb() -> Path:
    """(Re)create views over all processed parquet files. / 重建 DuckDB 视图。"""
    cfg = load_config()
    root = cfg.paths.resolve("processed")
    db = root / "tft.duckdb"
    con = duckdb.connect(str(db))
    for t in TABLES:
        pattern = (root / "*" / "*" / f"{t}.parquet").as_posix()
        con.execute(f"CREATE OR REPLACE VIEW {t} AS SELECT * FROM read_parquet('{pattern}')")
    con.close()
    return db


def available_patches(set_number: int) -> list[str]:
    cfg = load_config()
    src = cfg.paths.resolve("raw") / str(set_number)
    return sorted(p.name for p in src.iterdir() if p.is_dir()) if src.exists() else []
