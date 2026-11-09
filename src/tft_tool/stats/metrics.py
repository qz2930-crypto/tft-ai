"""M4 metric tables (docs/03-metrics.md §2, §5). / 统计指标表。

Each function returns a polars frame already passed through :func:`core.finalize`.
每个函数返回已完成收缩/区间/排序的表。
"""

from __future__ import annotations

from itertools import combinations

import polars as pl

from tft_tool.common.settings import load_config
from tft_tool.stats import core
from tft_tool.stats.load import Tables, items_with_outcome, units_with_outcome


# --------------------------------------------------------------------------- #
# M4.1 champion baselines   Δ = P̄(u, star) − 4.5
# --------------------------------------------------------------------------- #
def champion_baseline(t: Tables, shop: set[str] | None) -> pl.DataFrame:
    df = units_with_outcome(t, shop)
    agg = core.aggregate(df, ["character_id", "tier"])
    return core.finalize(agg)


def champion_baseline_by_level(t: Tables, shop: set[str] | None) -> pl.DataFrame:
    """Stratified baseline used by the item tables. / 装备表所用的分层基线。"""
    df = units_with_outcome(t, shop)
    agg = core.aggregate(df, ["character_id", "tier", "level_bucket"])
    return core.finalize(agg)


# --------------------------------------------------------------------------- #
# M4.2 champion × items   Δ = P̄(u, star, lvl, item) − P̄(u, star, lvl)
# --------------------------------------------------------------------------- #
def _item_combos(items: pl.DataFrame, size: int) -> pl.DataFrame:
    """Explode each unit's item list into unordered combos of ``size``. / 装备组合展开。"""
    per_unit = (
        items.group_by(["match_id", "puuid", "unit_idx", "character_id", "tier",
                        "placement", "is_top4", "is_win", "level_bucket"])
        .agg(pl.col("item").sort().alias("items"))
        .filter(pl.col("items").list.len() >= size)
    )
    rows: list[dict] = []
    for r in per_unit.iter_rows(named=True):
        for combo in combinations(sorted(set(r["items"])), size):
            base = {k: v for k, v in r.items() if k != "items"}
            rows.append({**base, "combo": " + ".join(combo), "combo_size": size})
    if not rows:
        schema = {c: per_unit.schema[c] for c in per_unit.columns if c != "items"}
        return pl.DataFrame(schema={**schema, "combo": pl.Utf8, "combo_size": pl.Int64})
    return pl.DataFrame(rows)


def champion_items(t: Tables, shop: set[str] | None, max_size: int = 3) -> pl.DataFrame:
    items = items_with_outcome(t, shop)
    base = champion_baseline_by_level(t, shop).select(
        "character_id", "tier", "level_bucket",
        pl.col("mean_placement").alias("base_mean"), pl.col("n").alias("base_n"),
    )
    frames = []
    for size in range(1, max_size + 1):
        combos = _item_combos(items, size)
        if combos.height == 0:
            continue
        keys = ["character_id", "tier", "level_bucket", "combo", "combo_size"]
        agg = core.aggregate(combos, keys)
        agg = agg.join(base, on=["character_id", "tier", "level_bucket"], how="left")
        frames.append(core.finalize(agg, baseline_col="base_mean"))
    return pl.concat(frames) if frames else pl.DataFrame()


def champion_items_pooled(t: Tables, shop: set[str] | None) -> pl.DataFrame:
    """Single items pooled across level buckets (more samples, display-friendly).
    单件装备跨等级合并（样本更多，便于展示）；基线为同棋子同星级。"""
    items = items_with_outcome(t, shop)
    base = champion_baseline(t, shop).select(
        "character_id", "tier", pl.col("mean_placement").alias("base_mean")
    )
    agg = core.aggregate(items, ["character_id", "tier", "item"]).join(
        base, on=["character_id", "tier"], how="left"
    )
    return core.finalize(agg, baseline_col="base_mean")


# --------------------------------------------------------------------------- #
# M4.3 champion co-occurrence   Synergy(a,b) = P̄(a,b) − [P̄(a) + P̄(b) − 4.5]
# --------------------------------------------------------------------------- #
def champion_pairs(t: Tables, shop: set[str] | None) -> pl.DataFrame:
    units = units_with_outcome(t, shop)
    boards = (
        units.group_by(["match_id", "puuid", "placement", "is_top4", "is_win"])
        .agg(pl.col("character_id").unique().sort().alias("units"))
    )
    rows: list[dict] = []
    for r in boards.iter_rows(named=True):
        for a, b in combinations(r["units"], 2):
            rows.append({"a": a, "b": b, "placement": r["placement"],
                         "is_top4": r["is_top4"], "is_win": r["is_win"]})
    if not rows:
        return pl.DataFrame()
    pairs = core.aggregate(pl.DataFrame(rows), ["a", "b"])

    single = (
        units.unique(["match_id", "puuid", "character_id"])
        .group_by("character_id").agg(pl.col("placement").mean().alias("m"),
                                      pl.len().alias("n_single"))
    )
    pairs = (
        pairs.join(single.rename({"character_id": "a", "m": "m_a", "n_single": "n_a"}), on="a")
        .join(single.rename({"character_id": "b", "m": "m_b", "n_single": "n_b"}), on="b")
        .with_columns((pl.col("m_a") + pl.col("m_b") - core.GLOBAL_MEAN).alias("expected_additive"))
    )
    out = core.finalize(pairs, baseline_col="expected_additive")
    # lift: how much more often they appear together than independence predicts
    n_boards = boards.height
    return out.with_columns(
        (pl.col("n") * n_boards / (pl.col("n_a") * pl.col("n_b"))).alias("lift")
    )


# --------------------------------------------------------------------------- #
# M4.6 trait breakpoints   Δ = P̄(trait, k) − P̄(trait, k−1)
# --------------------------------------------------------------------------- #
def trait_tiers(t: Tables) -> pl.DataFrame:
    df = t.traits.join(
        t.participants.select("match_id", "puuid", "placement", "is_top4", "is_win"),
        on=["match_id", "puuid"],
    ).filter(pl.col("tier_current") > 0)
    agg = core.aggregate(df, ["trait", "tier_current", "num_units"])
    prev = agg.select(
        "trait", (pl.col("tier_current") + 1).alias("tier_current"),
        pl.col("mean_placement").alias("prev_mean"),
    ).group_by(["trait", "tier_current"]).agg(pl.col("prev_mean").mean())
    agg = agg.join(prev, on=["trait", "tier_current"], how="left").with_columns(
        pl.coalesce([pl.col("prev_mean"), pl.lit(core.GLOBAL_MEAN)]).alias("prev_mean")
    )
    return core.finalize(agg, baseline_col="prev_mean")


# --------------------------------------------------------------------------- #
# M4.4 stage proxy   EarlyPower(u, s) = freq(u | elim s+1..s+2) / freq(u | elim s)
# --------------------------------------------------------------------------- #
def stage_power(t: Tables, shop: set[str] | None) -> pl.DataFrame:
    """Experimental, survivor-biased (docs/03 §5). / 实验性，存在幸存者偏差。"""
    cfg = load_config().analysis
    units = units_with_outcome(t, shop).unique(["match_id", "puuid", "character_id"])
    parts = t.participants
    stage_cap = 6
    units = units.with_columns(pl.min_horizontal(pl.col("stage"), stage_cap).alias("stage_b"))
    parts = parts.with_columns(pl.min_horizontal(pl.col("stage"), stage_cap).alias("stage_b"))
    boards_per_stage = parts.group_by("stage_b").agg(pl.len().alias("boards"))
    freq = (
        units.group_by(["character_id", "stage_b"]).agg(pl.len().alias("n"))
        .join(boards_per_stage, on="stage_b")
        .with_columns((pl.col("n") / pl.col("boards")).alias("freq"))
    )
    rows = []
    for s in range(2, stage_cap):
        here = freq.filter(pl.col("stage_b") == s).select(
            "character_id", pl.col("freq").alias("f_here"), pl.col("n").alias("n_here")
        )
        later = (
            freq.filter(pl.col("stage_b").is_in([s + 1, s + 2]))
            .group_by("character_id").agg(pl.col("n").sum().alias("n_later"),
                                          pl.col("boards").sum().alias("b_later"))
            .with_columns((pl.col("n_later") / pl.col("b_later")).alias("f_later"))
        )
        j = here.join(later, on="character_id", how="inner").with_columns(
            pl.lit(s).alias("stage"),
            (pl.col("f_later") / pl.col("f_here")).alias("early_power"),
            (pl.col("n_here") + pl.col("n_later")).alias("n"),
        )
        rows.append(j)
    out = pl.concat(rows) if rows else pl.DataFrame()
    if out.height:
        out = out.with_columns(
            pl.when(pl.col("n") < cfg.min_n_display).then(pl.lit("hidden"))
            .when(pl.col("n") < cfg.min_n_reliable).then(pl.lit("low"))
            .otherwise(pl.lit("ok")).alias("reliability")
        ).sort(["stage", "early_power"], descending=[False, True])
    return out
