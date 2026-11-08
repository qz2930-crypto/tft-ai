# docs/

Canonical planning documents live in the Claude Project **"tft ai tool"**:

| Doc | Content |
|---|---|
| `01-project-plan-v1.md` | Full plan: decision log, module breakdown M0–M11, phases, risks |
| `02-track-m-mechanistic-model.md` | Mechanistic track: ability spec library, strength formulas, duel/board simulator, positioning |
| `03-metrics.md` | Metric definitions used by `src/tft_tool/stats` (mirrored here) |

规划文档的权威版本在 Claude Project 中；`03-metrics.md` 因代码直接依赖，在此镜像一份。

## API findings (2026-11-08, probe of NA1 match on patch 18.6)

- `tft-match-v1` **does not return `augments`** → no augment table/metrics (planning Q9 closed).
- `info.game_version` is a placeholder `"TFT Unreal Version ?.?.?.?"` → patch inferred from
  `tft_set_number` + `game_datetime` against the calendar in `config.yaml`.
- Ladder entries (`/tft/league/v1/challenger|grandmaster`) carry `puuid` directly.
- Participant: `placement, level, last_round, gold_left, players_eliminated,
  total_damage_to_players, traits, units, companion, missions, riotIdGameName, riotIdTagline`.
- Unit: `character_id, itemNames, rarity, tier` (`name` empty). Trait: `name, num_units, style,
  tier_current, tier_total`.
