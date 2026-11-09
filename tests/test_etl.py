"""Flattener + round mapping on a synthetic match. / 合成对局测试。"""

from tft_tool.common.settings import RoundsConfig
from tft_tool.etl.build import flatten
from tft_tool.etl.schema import Match


def test_round_labels() -> None:
    rc = RoundsConfig(stage1_rounds=4, rounds_per_stage=7)
    assert rc.label(1) == (1, 1)
    assert rc.label(4) == (1, 4)
    assert rc.label(5) == (2, 1)
    assert rc.label(11) == (2, 7)
    assert rc.label(12) == (3, 1)
    assert rc.label(26) == (5, 1)


def _match() -> Match:
    parts = []
    for i in range(8):
        parts.append(
            {
                "puuid": f"p{i}",
                "placement": i + 1,
                "level": 9 if i < 2 else 7,
                "last_round": 30 - i,
                "gold_left": 3,
                "players_eliminated": 0,
                "total_damage_to_players": 100,
                "time_eliminated": 1800.0,
                "units": [
                    {"character_id": "TFT18_Lux", "tier": 2, "rarity": 3,
                     "itemNames": ["TFT_Item_JeweledGauntlet", "TFT_Item_RabadonsDeathcap"]},
                    {"character_id": "TFT18_Sett", "tier": 2, "rarity": 3, "itemNames": []},
                ],
                "traits": [
                    {"name": "TFT18_Blossom", "num_units": 4, "style": 3,
                     "tier_current": 2, "tier_total": 4}
                ],
                "companion": {"skin_ID": 1},  # extra field must be tolerated
            }
        )
    return Match.model_validate(
        {
            "metadata": {"match_id": "NA1_1", "data_version": "6"},
            "info": {
                "game_datetime": 1762300000000,
                "game_length": 2000.0,
                "queue_id": 1100,
                "tft_set_number": 18,
                "tft_game_type": "standard",
                "game_version": "TFT Unreal Version ?.?.?.?",
                "participants": parts,
            },
        }
    )


def test_flatten_counts_and_derived_fields() -> None:
    r = flatten(_match(), "18.6")
    assert len(r.matches) == 1
    assert len(r.participants) == 8
    assert len(r.units) == 16
    assert len(r.unit_items) == 16  # 2 items × 8 players
    assert len(r.traits) == 8
    p0 = r.participants[0]
    assert p0["is_win"] and p0["is_top4"]
    assert p0["level_bucket"] == "9+"
    assert r.participants[7]["level_bucket"] == "≤7"
    assert p0["stage_round"] == "5-5"  # last_round 30 → stage 5 round 5
    assert r.unit_items[0]["item"] == "TFT_Item_JeweledGauntlet"
