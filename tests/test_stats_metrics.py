"""Metric tables on a tiny synthetic Tables object. / 指标表合成数据测试。"""

import polars as pl

from tft_tool.stats import metrics
from tft_tool.stats.load import Tables


def _tables() -> Tables:
    # 4 boards: A+B together twice (placements 1,2), A alone (8), B alone (8)
    parts = pl.DataFrame({
        "match_id": ["m1", "m1", "m2", "m2"],
        "puuid": ["p1", "p2", "p3", "p4"],
        "placement": [1, 2, 8, 8],
        "is_top4": [True, True, False, False],
        "is_win": [True, False, False, False],
        "level": [9, 9, 8, 8],
        "level_bucket": ["9+", "9+", "8", "8"],
        "stage": [7, 7, 4, 4],
        "n_units": [2, 2, 1, 1],
    })
    units = pl.DataFrame({
        "match_id": ["m1", "m1", "m1", "m1", "m2", "m2"],
        "puuid": ["p1", "p1", "p2", "p2", "p3", "p4"],
        "unit_idx": [0, 1, 0, 1, 0, 0],
        "character_id": ["A", "B", "A", "B", "A", "B"],
        "tier": [2, 2, 2, 2, 2, 2],
        "rarity": [1, 1, 1, 1, 1, 1],
        "n_items": [1, 0, 1, 0, 0, 0],
    })
    items = pl.DataFrame({
        "match_id": ["m1", "m1"], "puuid": ["p1", "p2"], "unit_idx": [0, 0],
        "character_id": ["A", "A"], "tier": [2, 2], "slot": [0, 0],
        "item": ["TFT_Item_IE", "TFT_Item_IE"],
    })
    traits = pl.DataFrame({
        "match_id": ["m1", "m2"], "puuid": ["p1", "p3"], "trait": ["T", "T"],
        "num_units": [4, 2], "style": [3, 1], "tier_current": [2, 1], "tier_total": [3, 3],
    })
    matches = pl.DataFrame({"match_id": ["m1", "m2"]})
    return Tables("18.6", matches, parts, units, items, traits)


def test_champion_baseline() -> None:
    out = metrics.champion_baseline(_tables(), None).sort("character_id")
    a = out.filter(pl.col("character_id") == "A").row(0, named=True)
    assert a["n"] == 3 and abs(a["mean_placement"] - 11 / 3) < 1e-9


def test_pair_synergy_formula() -> None:
    out = metrics.champion_pairs(_tables(), None).row(0, named=True)
    # P̄(A,B) = 1.5 ; P̄(A) = P̄(B) = 11/3 ; expected = 11/3 + 11/3 − 4.5
    assert abs(out["mean_placement"] - 1.5) < 1e-9
    assert abs(out["expected_additive"] - (22 / 3 - 4.5)) < 1e-9
    assert out["delta"] < 0  # real synergy


def test_item_delta_uses_stratified_baseline() -> None:
    out = metrics.champion_items(_tables(), None)
    row = out.filter(pl.col("combo") == "TFT_Item_IE").row(0, named=True)
    # A with IE at 9+ → placements 1,2 (mean 1.5); baseline A@2★@9+ = same two boards → Δ = 0
    assert abs(row["delta"]) < 1e-9
    assert row["base_n"] == 2
