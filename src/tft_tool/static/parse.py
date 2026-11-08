"""Normalise cdragon JSON into flat tables. / 将 cdragon JSON 规范化为平面表。

All parsers are defensive: missing keys become ``None`` rather than raising, and
the ``validate`` step reports what looks off. The Unreal-era files (S18+) may
differ from older sets, so field access goes through small helpers.
所有解析器对缺字段容错；``validate`` 负责报告异常。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import polars as pl

# Expected champion stat keys in cdragon / cdragon 中的棋子属性键
STAT_KEYS = (
    "hp",
    "mana",
    "initialMana",
    "damage",
    "armor",
    "magicResist",
    "attackSpeed",
    "range",
    "critChance",
    "critMultiplier",
)

_AUGMENT_RE = re.compile(r"_Augment_", re.IGNORECASE)
_EMBLEM_RE = re.compile(r"(Emblem|Spatula)", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# champions
# --------------------------------------------------------------------------- #
def parse_champions(set_data: dict[str, Any], lang: str) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for c in set_data.get("champions", []):
        stats = c.get("stats") or {}
        ability = c.get("ability") or {}
        row: dict[str, Any] = {
            "api_name": c.get("apiName"),
            "character_name": c.get("characterName"),
            f"name_{lang}": c.get("name"),
            "cost": c.get("cost"),
            "role": c.get("role"),
            "traits": c.get("traits") or [],
            f"ability_name_{lang}": ability.get("name"),
            f"ability_desc_{lang}": ability.get("desc"),
            "icon": c.get("icon"),
        }
        for k in STAT_KEYS:
            row[f"stat_{k}"] = stats.get(k)
        rows.append(row)
    return pl.DataFrame(rows)


def parse_ability_variables(set_data: dict[str, Any]) -> pl.DataFrame:
    """Long table: one row per (champion, variable, star). / 每棋子-变量-星级一行。

    cdragon stores ``variables: [{name, value: [v0, v1, v2, v3, ...]}]`` where
    index = star level (index 0 is usually unused / 0 星占位).
    """
    rows: list[dict[str, Any]] = []
    for c in set_data.get("champions", []):
        for v in (c.get("ability") or {}).get("variables") or []:
            values = v.get("value") or []
            for star, val in enumerate(values):
                rows.append(
                    {
                        "api_name": c.get("apiName"),
                        "variable": v.get("name"),
                        "star": star,
                        "value": val,
                    }
                )
    return pl.DataFrame(rows)


# --------------------------------------------------------------------------- #
# traits
# --------------------------------------------------------------------------- #
def parse_traits(set_data: dict[str, Any], lang: str) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for t in set_data.get("traits", []):
        rows.append(
            {
                "api_name": t.get("apiName"),
                f"name_{lang}": t.get("name"),
                f"desc_{lang}": t.get("desc"),
                "icon": t.get("icon"),
                "n_breakpoints": len(t.get("effects") or []),
            }
        )
    return pl.DataFrame(rows)


def parse_trait_breakpoints(set_data: dict[str, Any]) -> pl.DataFrame:
    """One row per trait tier. / 每羁绊每档一行。"""
    rows: list[dict[str, Any]] = []
    for t in set_data.get("traits", []):
        for i, e in enumerate(t.get("effects") or []):
            rows.append(
                {
                    "api_name": t.get("apiName"),
                    "tier_idx": i + 1,
                    "min_units": e.get("minUnits"),
                    "max_units": e.get("maxUnits"),
                    "style": e.get("style"),
                    "variables": e.get("variables") or {},
                }
            )
    return pl.DataFrame(rows)


# --------------------------------------------------------------------------- #
# items / augments
# --------------------------------------------------------------------------- #
def _classify_item(api_name: str | None, item: dict[str, Any]) -> str:
    """Rough item category. / 粗分类：component / completed / emblem / augment / other."""
    api = api_name or ""
    if _AUGMENT_RE.search(api) or "Augment" in api:
        return "augment"
    comp = item.get("composition") or []
    if _EMBLEM_RE.search(api) or item.get("associatedTraits"):
        return "emblem"
    if not comp and api.startswith("TFT_Item_") and item.get("unique") is False:
        return "component"
    if comp:
        return "completed"
    return "other"


def parse_items(raw: dict[str, Any], lang: str, set_mutator: str | None = None) -> pl.DataFrame:
    """Items + augments live at top level ``items`` for all sets. / 顶层 items 含所有赛季。

    If ``set_mutator`` (e.g. ``TFTSet18``) is given, we keep items whose apiName
    contains the set prefix (``TFT18_``) plus the generic ``TFT_Item_*`` pool.
    """
    set_prefix = None
    if set_mutator:
        m = re.search(r"(\d+)", set_mutator)
        set_prefix = f"TFT{m.group(1)}_" if m else None

    rows: list[dict[str, Any]] = []
    for it in raw.get("items", []):
        api = it.get("apiName") or ""
        if set_prefix and not (api.startswith(set_prefix) or api.startswith("TFT_Item_")):
            continue
        rows.append(
            {
                "api_name": api,
                f"name_{lang}": it.get("name"),
                f"desc_{lang}": it.get("desc"),
                "category": _classify_item(api, it),
                "composition": it.get("composition") or [],
                "associated_traits": it.get("associatedTraits") or [],
                "incompatible_traits": it.get("incompatibleTraits") or [],
                "unique": it.get("unique"),
                "effects": it.get("effects") or {},
                "icon": it.get("icon"),
            }
        )
    return pl.DataFrame(rows)


# --------------------------------------------------------------------------- #
# bundle + validation
# --------------------------------------------------------------------------- #
@dataclass
class StaticBundle:
    set_number: int
    patch: str
    champions: pl.DataFrame
    ability_vars: pl.DataFrame
    traits: pl.DataFrame
    trait_breakpoints: pl.DataFrame
    items: pl.DataFrame
    warnings: list[str] = field(default_factory=list)


def build_bundle(
    raw_by_lang: dict[str, dict[str, Any]],
    set_number: int,
    patch: str,
    primary_lang: str = "en_us",
) -> StaticBundle:
    """Merge languages on ``api_name``. / 以 api_name 为键合并多语言。"""
    from tft_tool.static.cdragon import select_set

    primary = raw_by_lang[primary_lang]
    set_data = select_set(primary, set_number)
    mutator = set_data.get("mutator")

    champions = parse_champions(set_data, primary_lang)
    traits = parse_traits(set_data, primary_lang)
    items = parse_items(primary, primary_lang, mutator)

    for lang, raw in raw_by_lang.items():
        if lang == primary_lang:
            continue
        sd = select_set(raw, set_number)
        c2 = parse_champions(sd, lang).select(
            "api_name", f"name_{lang}", f"ability_name_{lang}", f"ability_desc_{lang}"
        )
        champions = champions.join(c2, on="api_name", how="left")
        t2 = parse_traits(sd, lang).select("api_name", f"name_{lang}", f"desc_{lang}")
        traits = traits.join(t2, on="api_name", how="left")
        i2 = parse_items(raw, lang, mutator).select("api_name", f"name_{lang}", f"desc_{lang}")
        items = items.join(i2, on="api_name", how="left")

    bundle = StaticBundle(
        set_number=set_number,
        patch=patch,
        champions=champions,
        ability_vars=parse_ability_variables(set_data),
        traits=traits,
        trait_breakpoints=parse_trait_breakpoints(set_data),
        items=items,
    )
    bundle.warnings = validate(bundle)
    return bundle


def validate(b: StaticBundle) -> list[str]:
    """Sanity checks from docs/01 §M1.4. / 规划 M1.4 的校验项。"""
    w: list[str] = []
    n_champ = b.champions.height
    if not 40 <= n_champ <= 120:
        w.append(f"unexpected champion count {n_champ} (expected ~65 for S18)")
    n_traits = b.traits.height
    if not 15 <= n_traits <= 60:
        w.append(f"unexpected trait count {n_traits} (expected ~35 for S18)")
    if b.champions.height and b.champions["cost"].null_count():
        w.append("some champions have null cost")
    missing_stats = [
        k for k in STAT_KEYS if b.champions.height and b.champions[f"stat_{k}"].null_count() > 0
    ]
    if missing_stats:
        w.append(f"null stats present for: {missing_stats}")
    if b.ability_vars.height == 0:
        w.append("no ability variables parsed — cdragon schema may have changed")
    if b.items.filter(pl.col("category") == "completed").height < 20:
        w.append("fewer than 20 completed items classified — check item filter")
    return w
