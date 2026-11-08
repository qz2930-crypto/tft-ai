"""Parser tests on a tiny synthetic cdragon payload. / 用合成 cdragon 数据测试解析器。"""

from tft_tool.static.cdragon import select_set
from tft_tool.static.parse import build_bundle, parse_ability_variables, parse_champions


def _champ(api: str, name: str, cost: int, traits: list[str]) -> dict:
    return {
        "apiName": api,
        "characterName": api,
        "name": name,
        "cost": cost,
        "role": "Fighter",
        "traits": traits,
        "icon": f"ASSETS/{api}.tex",
        "stats": {
            "hp": 650, "mana": 60, "initialMana": 20, "damage": 55, "armor": 40,
            "magicResist": 40, "attackSpeed": 0.7, "range": 1, "critChance": 0.25,
            "critMultiplier": 1.4,
        },
        "ability": {
            "name": f"{name} Skill",
            "desc": "Deals @Damage@ damage.",
            "variables": [{"name": "Damage", "value": [0, 100, 150, 225, 0, 0, 0]}],
        },
    }


def _raw(lang: str) -> dict:
    sfx = "" if lang == "en_us" else "_zh"
    return {
        "items": [
            {"apiName": "TFT_Item_BFSword", "name": "B.F. Sword" + sfx, "composition": [],
             "unique": False, "effects": {"AD": 10}},
            {"apiName": "TFT_Item_InfinityEdge", "name": "IE" + sfx,
             "composition": ["TFT_Item_BFSword", "TFT_Item_SparringGloves"], "unique": False},
            {"apiName": "TFT18_Item_BlossomEmblem", "name": "Blossom Emblem" + sfx,
             "composition": ["TFT_Item_Spatula", "TFT_Item_BFSword"],
             "associatedTraits": ["TFT18_Blossom"]},
            {"apiName": "TFT18_Augment_Foo", "name": "Foo" + sfx},
            {"apiName": "TFT17_Item_OldSet", "name": "should be filtered"},
        ],
        "setData": [
            {"number": 17, "mutator": "TFTSet17", "champions": [], "traits": []},
            {
                "number": 18,
                "mutator": "TFTSet18",
                "champions": [
                    _champ("TFT18_Karma", "Karma" + sfx, 1, ["Blossom", "Spellweaver"]),
                    _champ("TFT18_Sett", "Sett" + sfx, 4, ["Blossom", "Brawler"]),
                ],
                "traits": [
                    {
                        "apiName": "TFT18_Blossom",
                        "name": "Blossom" + sfx,
                        "desc": "...",
                        "effects": [
                            {"minUnits": 2, "maxUnits": 3, "style": 1, "variables": {"AP": 12}},
                            {"minUnits": 4, "maxUnits": 5, "style": 3, "variables": {"AP": 30}},
                        ],
                    }
                ],
            },
        ],
    }


def test_select_set_prefers_exact_mutator() -> None:
    sd = select_set(_raw("en_us"), 18)
    assert sd["mutator"] == "TFTSet18"


def test_parse_champions_and_variables() -> None:
    sd = select_set(_raw("en_us"), 18)
    champs = parse_champions(sd, "en_us")
    assert champs.height == 2
    assert champs.filter(champs["api_name"] == "TFT18_Sett")["cost"][0] == 4
    av = parse_ability_variables(sd)
    sett = av.filter((av["api_name"] == "TFT18_Sett") & (av["star"] == 2))
    assert sett["value"][0] == 150


def test_bundle_merges_languages_and_filters_items() -> None:
    b = build_bundle({"en_us": _raw("en_us"), "zh_cn": _raw("zh_cn")}, 18, "18.6")
    assert "name_zh_cn" in b.champions.columns
    karma = b.champions.filter(b.champions["api_name"] == "TFT18_Karma")
    assert karma["name_zh_cn"][0] == "Karma_zh"
    cats = dict(b.items.group_by("category").len().iter_rows())
    assert cats.get("augment") == 1
    assert cats.get("emblem") == 1
    assert "TFT17_Item_OldSet" not in b.items["api_name"].to_list()
    assert b.trait_breakpoints.height == 2
    # synthetic data is tiny, so validation must warn rather than crash
    assert any("champion count" in w for w in b.warnings)
