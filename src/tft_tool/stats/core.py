"""Shared metric math (docs/03-metrics.md §1–§3). / 指标公共数学。

Every aggregate table produced by M4 goes through :func:`finalize`, which adds:
    n, mean_placement, top4_rate, win_rate,
    delta             = mean − baseline                        (§2)
    shrunk            = (n·mean + k·baseline) / (n + k)        (§3.1)
    ci_low / ci_high  = mean ± 1.96·σ/√n                       (§3.2)
    top4_ci_low/high  = Wilson 95%                              (§3.2)
    lcb_score         = −(shrunk + 1.96·σ/√n)  (rank key, §3.3)
    reliability       = hidden | low | ok                       (§3.3)
所有聚合表统一经过 finalize 添加收缩、置信区间、排序键与可靠性标签。
"""

from __future__ import annotations

import math

import polars as pl

from tft_tool.common.settings import load_config

Z = 1.96
GLOBAL_MEAN = 4.5


def wilson(successes: pl.Expr, n: pl.Expr, z: float = Z) -> tuple[pl.Expr, pl.Expr]:
    """Wilson score interval as polars expressions. / Wilson 区间。"""
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)).sqrt()) / denom
    return centre - half, centre + half


def aggregate(df: pl.DataFrame, by: list[str]) -> pl.DataFrame:
    """Group → n, mean placement, top4/win counts and rates. / 分组聚合。"""
    return (
        df.group_by(by)
        .agg(
            pl.len().alias("n"),
            pl.col("placement").mean().alias("mean_placement"),
            pl.col("placement").std(ddof=1).alias("sigma"),
            pl.col("is_top4").sum().alias("top4_n"),
            pl.col("is_win").sum().alias("win_n"),
        )
        .with_columns(
            (pl.col("top4_n") / pl.col("n")).alias("top4_rate"),
            (pl.col("win_n") / pl.col("n")).alias("win_rate"),
        )
    )


def finalize(
    agg: pl.DataFrame,
    baseline_col: str | None = None,
    baseline_value: float = GLOBAL_MEAN,
    k: float | None = None,
) -> pl.DataFrame:
    """Add Δ, shrinkage, CIs, rank key, reliability. / 添加 Δ、收缩、区间、排序键。

    ``baseline_col`` names a column already joined onto ``agg`` holding the
    stratified baseline mean; when absent, ``baseline_value`` (4.5) is used.
    """
    cfg = load_config().analysis
    k = cfg.shrinkage_k if k is None else k
    sigma_default = cfg.placement_sigma_default

    base = pl.col(baseline_col) if baseline_col else pl.lit(baseline_value)
    sigma = pl.coalesce([pl.col("sigma"), pl.lit(sigma_default)]).fill_nan(sigma_default)
    se = Z * sigma / pl.col("n").sqrt()
    shrunk = (pl.col("n") * pl.col("mean_placement") + k * base) / (pl.col("n") + k)
    t4_lo, t4_hi = wilson(pl.col("top4_n"), pl.col("n"))

    out = agg.with_columns(
        base.alias("baseline"),
        (pl.col("mean_placement") - base).alias("delta"),
        shrunk.alias("shrunk"),
        (shrunk - base).alias("delta_shrunk"),
        (pl.col("mean_placement") - se).alias("ci_low"),
        (pl.col("mean_placement") + se).alias("ci_high"),
        t4_lo.alias("top4_ci_low"),
        t4_hi.alias("top4_ci_high"),
        (-(shrunk + se)).alias("lcb_score"),
        pl.when(pl.col("n") < cfg.min_n_display)
        .then(pl.lit("hidden"))
        .when(pl.col("n") < cfg.min_n_reliable)
        .then(pl.lit("low"))
        .otherwise(pl.lit("ok"))
        .alias("reliability"),
    )
    return out.sort("lcb_score", descending=True)


def visible(df: pl.DataFrame) -> pl.DataFrame:
    """Drop rows below the display threshold. / 去掉样本不足的行。"""
    return df.filter(pl.col("reliability") != "hidden")


def ci_halfwidth(n: int, sigma: float = 2.29) -> float:
    """Convenience for docs/tests. / 文档与测试用。"""
    return Z * sigma / math.sqrt(n)
