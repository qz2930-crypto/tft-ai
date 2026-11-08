# TFT AI Tool / 云顶之弈分析工具

Statistical + mechanistic analysis of Teamfight Tactics match data: which items suit which champions, which champions pair well at which stage, and (research track) a combat simulator for positioning.

基于云顶之弈对局数据的统计与机制分析：哪些棋子适合哪些装备、哪些棋子在哪个阶段搭配更强，以及（研究方向）用于站位分析的战斗模拟器。

> Current set / 当前赛季: **S18 Enchanted Wilds（魔法荒野）**, used to validate the pipeline. **S19 (2026-12-01)** is the first production set.

## Architecture / 架构

```
Riot API (league-v1, match-v1)   CommunityDragon (static JSON)
          │                                  │
   M2 ingest 采集                      M1 static 静态数据
          └──────────► M3 ETL / DuckDB ◄──────┘
                     │                 │
            M4 stats 统计        M5 ML 模型 (Track S)
                     │                 │        M5b–e mechanistic model (Track M)
                     └──► results/{set}/{patch}/ ◄──┘
                                │
                   M7 FastAPI  ──  M8 Web (zh / en)
```

Design docs live in the Claude Project (`docs/01-project-plan-v1.md`, `02-track-m-mechanistic-model.md`, `03-metrics.md`); copies are mirrored in `docs/` here.

## Quick start / 快速开始

```bash
# 1. toolchain / 工具链
curl -LsSf https://astral.sh/uv/install.sh | sh      # or: pip install uv

# 2. deps / 依赖
uv sync --extra dev          # add --extra ml --extra api as modules land

# 3. secrets / 密钥
cp .env.example .env         # fill RIOT_API_KEY (https://developer.riotgames.com)

# 4. sanity / 检查
uv run tft info
uv run pytest -q

# 5. probe one real match (answers "does the API still return augments?")
#    拉一局真实对局，确认字段（含海克斯是否存在）
uv run python scripts/probe_match.py --save
```

## Repository layout / 目录

| Path | Purpose / 用途 |
|---|---|
| `src/tft_tool/common/` | settings, shared helpers / 配置与公共工具 |
| `src/tft_tool/static/` | M1 CommunityDragon loaders, ability spec library / 静态数据与技能规格 |
| `src/tft_tool/ingest/` | M2 Riot API client, collectors / 采集 |
| `src/tft_tool/etl/` | M3 JSON → DuckDB tables / 清洗建表 |
| `src/tft_tool/stats/` | M4 metrics (see `docs/03-metrics.md`) / 统计指标 |
| `src/tft_tool/ml/` | M5 placement model, recommender, mechanistic model / 模型 |
| `src/tft_tool/api/` | M7 FastAPI / 后端 |
| `web/` | M8 frontend / 前端 |
| `scripts/` | one-off utilities / 工具脚本 |
| `data/` | local only, git-ignored / 本地数据，不入库 |

## Data & conduct / 数据与合规

- Only aggregate statistics are published; raw matches stay local. / 只发布聚合统计，原始对局不外传。
- Rate limits are enforced client-side (`ingest/riot_client.py`). / 客户端强制限速。
- TFT AI Tool isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

## License

MIT
