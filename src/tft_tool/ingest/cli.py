"""`tft ingest ...` subcommands. / 采集子命令。"""

from __future__ import annotations

import logging

import typer
from rich import print as rprint
from rich.table import Table

from tft_tool.ingest.collector import Collector
from tft_tool.ingest.index import IngestIndex

app = typer.Typer(no_args_is_help=True)


@app.callback()
def _root() -> None:
    """Match collection (M2). / 对局采集。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


@app.command()
def players() -> None:
    """Stage 1: ladder → players index. / 拉取宗师+王者名单。"""
    n = Collector().collect_players()
    rprint(f"[green]✓[/] players upserted: {n}")


@app.command()
def ids(
    per_player: int | None = typer.Option(None, help="match ids per player"),
    since_patch: str | None = typer.Option(None, help="only ids after this patch start"),
) -> None:
    """Stage 2: players → match id pool. / 收集对局 ID。"""
    n = Collector().collect_match_ids(per_player, since_patch)
    rprint(f"[green]✓[/] new match ids: {n}")


@app.command()
def matches(limit: int | None = typer.Option(None, help="max matches this run")) -> None:
    """Stage 3: fetch pending matches to data/raw. / 下载对局 JSON。"""
    s = Collector().collect_matches(limit)
    rprint(f"[green]✓[/] {s}")


@app.command()
def run(limit: int | None = typer.Option(None, help="max matches this run")) -> None:
    """All three stages. / 一键执行三阶段。"""
    Collector().run(limit)
    status()


@app.command()
def prune(
    before_patch: str = typer.Option(..., help="drop pending ids older than this patch's data"),
    dry_run: bool = typer.Option(False),
) -> None:
    """Skip pending ids that predate a patch (uses smallest downloaded id of that patch).
    清理早于某版本的待下载 ID（以该版本已下载的最小 ID 为界）。"""
    idx = IngestIndex()
    thr = idx.min_done_id(before_patch)
    if thr is None:
        rprint(f"[red]no done matches for patch {before_patch}; download some first[/]")
        raise typer.Exit(1)
    if dry_run:
        n = sum(1 for m in idx.pending() if idx._id_num(m) < thr)
        rprint(f"would prune {n} pending ids below {thr}")
    else:
        n = idx.prune_pending_before(thr, f"pruned: before {before_patch}")
        rprint(f"[green]✓[/] pruned {n} pending ids below {thr}")
    idx.close()


@app.command()
def status() -> None:
    """Show index counts. / 查看采集进度。"""
    idx = IngestIndex()
    t = Table(title="ingest status / 采集进度")
    t.add_column("metric")
    t.add_column("value", justify="right")
    t.add_row("players", str(idx.n_players()))
    for k, v in sorted(idx.status_counts().items()):
        t.add_row(f"matches {k}", str(v))
    for k, v in idx.patch_counts().items():
        t.add_row(f"  done @ patch {k}", str(v))
    rprint(t)
    idx.close()
