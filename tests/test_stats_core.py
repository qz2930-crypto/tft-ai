"""Formula checks against hand-computed values (docs/03-metrics.md). / 公式校验。"""

import math

import polars as pl

from tft_tool.stats import core


def _df(placements: list[int]) -> pl.DataFrame:
    return pl.DataFrame({
        "g": ["x"] * len(placements),
        "placement": placements,
        "is_top4": [p <= 4 for p in placements],
        "is_win": [p == 1 for p in placements],
    })


def test_aggregate_and_shrinkage() -> None:
    # 10 samples, mean 3.0 ; baseline 4.5 ; k = 30 → shrunk = (10*3 + 30*4.5)/40 = 4.125
    agg = core.aggregate(_df([3] * 10), ["g"])
    out = core.finalize(agg, k=30)
    row = out.row(0, named=True)
    assert row["n"] == 10
    assert math.isclose(row["mean_placement"], 3.0)
    assert math.isclose(row["delta"], -1.5)
    assert math.isclose(row["shrunk"], 4.125)
    assert row["reliability"] == "hidden"  # n < 50


def test_ci_uses_default_sigma_when_std_undefined() -> None:
    # constant placements → std = 0 → CI collapses; sigma 0 is legit, not NaN
    agg = core.aggregate(_df([2] * 60), ["g"])
    out = core.finalize(agg)
    row = out.row(0, named=True)
    assert row["reliability"] == "low"
    assert math.isclose(row["ci_low"], row["ci_high"], abs_tol=1e-9)


def test_ci_halfwidth_matches_doc_examples() -> None:
    # docs/03 §3.2: n=50 → ±0.63 ; n=200 → ±0.32 ; n=500 → ±0.20
    assert round(core.ci_halfwidth(50), 2) == 0.63
    assert round(core.ci_halfwidth(200), 2) == 0.32
    assert round(core.ci_halfwidth(500), 2) == 0.20


def test_wilson_interval_reasonable() -> None:
    df = pl.DataFrame({"top4_n": [30], "n": [60]})
    lo, hi = core.wilson(pl.col("top4_n"), pl.col("n"))
    r = df.select(lo.alias("lo"), hi.alias("hi")).row(0)
    assert 0.37 < r[0] < 0.39 and 0.61 < r[1] < 0.63


def test_lcb_ranking_penalises_small_n() -> None:
    # same mean 3.5 but n=20 vs n=400 → larger n must rank first
    small = core.aggregate(_df([3, 4] * 10), ["g"]).with_columns(pl.lit("small").alias("g"))
    big = core.aggregate(_df([3, 4] * 200), ["g"]).with_columns(pl.lit("big").alias("g"))
    out = core.finalize(pl.concat([small, big]))
    assert out["g"].to_list() == ["big", "small"]
