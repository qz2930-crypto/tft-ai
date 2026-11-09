"""Pydantic models mirroring the probed tft-match-v1 payload. / 对局 JSON 的数据模型。

Field set verified on a live NA1 patch-18.6 match (2026-11-08). ``extra="allow"`` so
unknown fields never break parsing; ``augments`` is intentionally absent (not returned).
字段集按真实对局核对；未知字段不报错；API 不返回 augments。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Unit(BaseModel):
    model_config = ConfigDict(extra="allow")
    character_id: str
    tier: int  # star level 1-3 (4 for some special units) / 星级
    rarity: int  # internal cost index, NOT shop cost / 内部稀有度，非商店费用
    itemNames: list[str] = Field(default_factory=list)  # noqa: N815 (API field name)


class Trait(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    num_units: int
    style: int  # 0 none,1 bronze,2 silver,3 gold,4 prismatic (approx) / 羁绊颜色
    tier_current: int
    tier_total: int


class Participant(BaseModel):
    model_config = ConfigDict(extra="allow")
    puuid: str
    placement: int
    level: int
    last_round: int
    gold_left: int
    players_eliminated: int
    total_damage_to_players: int
    time_eliminated: float | None = None
    units: list[Unit] = Field(default_factory=list)
    traits: list[Trait] = Field(default_factory=list)
    riotIdGameName: str | None = None  # noqa: N815
    riotIdTagline: str | None = None  # noqa: N815


class Info(BaseModel):
    model_config = ConfigDict(extra="allow")
    game_datetime: int
    game_length: float
    queue_id: int
    tft_set_number: int
    tft_game_type: str | None = None
    game_version: str | None = None
    participants: list[Participant]


class Metadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    match_id: str
    data_version: str | None = None


class Match(BaseModel):
    model_config = ConfigDict(extra="allow")
    metadata: Metadata
    info: Info
