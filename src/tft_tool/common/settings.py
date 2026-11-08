"""Central configuration loader. / 统一配置加载。

Secrets come from ``.env`` (pydantic-settings); non-secret project config comes
from ``config.yaml``. Both are resolved relative to the repository root.
密钥从 ``.env`` 读取，非敏感配置从 ``config.yaml`` 读取，均相对于仓库根目录解析。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Secrets(BaseSettings):
    """Values that must never be committed. / 不得入库的值。"""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    riot_api_key: str = Field(default="", alias="RIOT_API_KEY")
    riot_platform: str = Field(default="na1", alias="RIOT_PLATFORM")
    riot_region: str = Field(default="americas", alias="RIOT_REGION")


class SetConfig(BaseModel):
    id: int
    name: str
    name_zh: str
    patch: str


class RateLimit(BaseModel):
    per_second: int = 20
    per_two_minutes: int = 100


class IngestConfig(BaseModel):
    tiers: list[str]
    queue: str = "RANKED_TFT"
    queue_id: int = 1100
    matches_per_player: int = 40
    target_matches: int = 30000
    rate_limit: RateLimit = RateLimit()


class StaticConfig(BaseModel):
    cdragon_base: str
    cdragon_branch: str = "latest"
    languages: list[str]


class AnalysisConfig(BaseModel):
    shrinkage_k: float = 30
    min_n_display: int = 50
    min_n_reliable: int = 200
    placement_sigma_default: float = 2.29
    level_buckets: list[list[int]]
    stage_buckets: list[str]
    rank_weight: bool = False


class PathsConfig(BaseModel):
    raw: str
    processed: str
    results: str
    static: str

    def resolve(self, name: str) -> Path:
        """Absolute path for a data dir. / 返回数据目录绝对路径。"""
        return REPO_ROOT / getattr(self, name)


class Config(BaseModel):
    set: SetConfig
    ingest: IngestConfig
    static: StaticConfig
    analysis: AnalysisConfig
    paths: PathsConfig


@lru_cache(maxsize=1)
def load_config(path: Path | None = None) -> Config:
    """Load and validate ``config.yaml``. / 加载并校验 config.yaml。"""
    cfg_path = path or REPO_ROOT / "config.yaml"
    with cfg_path.open("r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)
    return Config.model_validate(raw)


@lru_cache(maxsize=1)
def load_secrets() -> Secrets:
    """Load ``.env`` secrets. / 加载 .env 密钥。"""
    return Secrets()
