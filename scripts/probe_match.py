"""Probe one live match to inventory the API schema. / 拉取一局，盘点 API 返回字段。

Answers planning question #9: does tft-match-v1 still return `augments`?
Also records every participant/unit/trait field name so the ETL schema (M3)
is built from reality, not from docs.
用于回答规划问题 9（海克斯字段是否存在），并记录所有字段名供 M3 建表参考。

Run on your machine (needs RIOT_API_KEY in .env) / 在本机运行:
    uv run python scripts/probe_match.py
    uv run python scripts/probe_match.py --tier GRANDMASTER --save
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rich import print as rprint

from tft_tool.common.settings import REPO_ROOT
from tft_tool.ingest.riot_client import RiotClient


def _keys(d: dict[str, Any]) -> list[str]:
    return sorted(d.keys())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="CHALLENGER")
    ap.add_argument("--save", action="store_true", help="save raw JSON under data/raw/probe/")
    args = ap.parse_args()

    client = RiotClient()
    ladder = client.ladder(args.tier)
    entries = ladder.get("entries", [])
    if not entries:
        raise SystemExit("ladder empty — check platform / 榜单为空，检查平台设置")
    rprint(f"[bold]ladder[/] {args.tier}: {len(entries)} players; entry keys = {_keys(entries[0])}")

    # Newer league responses carry `puuid` directly; fall back to summonerId otherwise.
    first = entries[0]
    puuid = first.get("puuid")
    if not puuid:
        raise SystemExit(
            "ladder entry has no puuid; need tft-summoner-v1 lookup by summonerId / 榜单无 puuid"
        )

    ids = client.match_ids(puuid, count=5)
    rprint(f"[bold]match ids[/] ({len(ids)}): {ids}")
    if not ids:
        raise SystemExit("no matches for this player")

    m = client.match(ids[0])
    info = m["info"]
    rprint(f"[bold]metadata keys[/]: {_keys(m['metadata'])}")
    rprint(f"[bold]info keys[/]: {_keys(info)}")
    rprint(
        f"game_version={info.get('game_version')!r} queue_id={info.get('queue_id')} "
        f"tft_set_number={info.get('tft_set_number')} tft_game_type={info.get('tft_game_type')!r}"
    )

    p = info["participants"][0]
    rprint(f"[bold]participant keys[/]: {_keys(p)}")
    has_aug = "augments" in p
    rprint(
        f"[bold {'green' if has_aug else 'red'}]augments field present: {has_aug}[/] "
        f"-> {p.get('augments')}"
    )
    if p.get("units"):
        rprint(f"[bold]unit keys[/]: {_keys(p['units'][0])}  sample={p['units'][0]}")
    if p.get("traits"):
        rprint(f"[bold]trait keys[/]: {_keys(p['traits'][0])}  sample={p['traits'][0]}")

    # Fields that matter for stage proxy / 阶段代理所需字段
    for k in ("placement", "level", "last_round", "time_eliminated", "gold_left",
              "players_eliminated", "total_damage_to_players"):
        rprint(f"  {k:26s} = {p.get(k)}")

    if args.save:
        out = REPO_ROOT / "data" / "raw" / "probe"
        out.mkdir(parents=True, exist_ok=True)
        path: Path = out / f"{m['metadata']['match_id']}.json"
        path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        rprint(f"saved -> {path}")

    client.close()


if __name__ == "__main__":
    main()
