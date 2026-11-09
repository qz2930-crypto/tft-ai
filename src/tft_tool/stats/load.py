"""Load processed tables for one patch as polars frames. / 读取某版本的处理后表。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from tft_tool.common.settings import load_config


@dataclass
class Tables:
    patch: str
    matches: pl.DataFrame
    participants: pl.DataFrame
    units: pl.DataFrame
    unit_items: pl.DataFrame
    traits: pl.DataFrame

    @property
    def n_matches(self) -> int:
        return self.matches.height


def processed_dir(patch: str) -> Path:
    cfg = load_config()
    return cfg.paths.resolve("processed") / str(cfg.set.id) / patch


def load_tables(patch: str, exclude_afk: bool = True) -> Tables:
    """Read the five Parquet tables. ``exclude_afk`` drops participants with zero
    units (early quitters) from participant-level stats. / 读取五张表；默认剔除 0 单位玩家。"""
    d = processed_dir(patch)
    if not d.exists():
        raise FileNotFoundError(f"{d} — run `tft etl build` first / 请先建表")
    parts = pl.read_parquet(d / "participants.parquet")
    if exclude_afk:
        parts = parts.filter(pl.col("n_units") > 0)
    keep = parts.select("match_id", "puuid")
    units = pl.read_parquet(d / "units.parquet").join(keep, on=["match_id", "puuid"])
    items = pl.read_parquet(d / "unit_items.parquet").join(keep, on=["match_id", "puuid"])
    traits = pl.read_parquet(d / "traits.parquet").join(keep, on=["match_id", "puuid"])
    return Tables(
        patch=patch,
        matches=pl.read_parquet(d / "matches.parquet"),
        participants=parts,
        units=units,
        unit_items=items,
        traits=traits,
    )


def shop_units(patch: str) -> set[str] | None:
    """Champion api_names that are real shop units (cost 1–5 with traits), from static
    data if archived; ``None`` when static data is unavailable. / 商店棋子集合。"""
    cfg = load_config()
    try:
        from tft_tool.static import cdragon
        from tft_tool.static.parse import build_bundle

        lang = cfg.static.languages[0]
        raw = cdragon.load_raw(lang, patch)
        b = build_bundle({lang: raw}, cfg.set.id, patch, primary_lang=lang)
    except FileNotFoundError:
        return None
    df = b.champions.filter(
        pl.col("cost").is_in([1, 2, 3, 4, 5]) & (pl.col("traits").list.len() > 0)
    )
    return set(df["api_name"].to_list())


# participant-level columns we join onto unit/item rows / 需要并到单位行上的玩家列
PART_COLS = ["match_id", "puuid", "placement", "is_top4", "is_win", "level_bucket", "stage"]


def units_with_outcome(t: Tables, only_shop: set[str] | None = None) -> pl.DataFrame:
    df = t.units.join(t.participants.select(PART_COLS), on=["match_id", "puuid"])
    if only_shop:
        df = df.filter(pl.col("character_id").is_in(list(only_shop)))
    return df


def items_with_outcome(t: Tables, only_shop: set[str] | None = None) -> pl.DataFrame:
    df = t.unit_items.join(t.participants.select(PART_COLS), on=["match_id", "puuid"])
    if only_shop:
        df = df.filter(pl.col("character_id").is_in(list(only_shop)))
    return df
