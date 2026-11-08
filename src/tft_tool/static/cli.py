"""`tft static ...` subcommands. / 静态数据子命令。"""

from __future__ import annotations

import logging

import polars as pl
import typer
from rich import print as rprint
from rich.table import Table

from tft_tool.common.settings import load_config
from tft_tool.static import cdragon
from tft_tool.static.parse import build_bundle

app = typer.Typer(no_args_is_help=True)


@app.callback()
def _root() -> None:
    """Static data (M1). / 静态数据。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


@app.command()
def fetch(
    patch: str | None = typer.Option(None, help="patch tag for archive dir / 归档版本号"),
    force: bool = typer.Option(False, help="re-download even if present / 强制重新下载"),
) -> None:
    """Download cdragon JSON for all configured languages. / 下载所有配置语言的 JSON。"""
    cfg = load_config()
    for lang in cfg.static.languages:
        p = cdragon.fetch(lang, patch=patch, force=force)
        rprint(f"[green]✓[/] {lang} -> {p}")


@app.command()
def summary(
    patch: str | None = typer.Option(None),
    export: bool = typer.Option(False, help="write parquet tables to data/static/{patch}/tables/"),
) -> None:
    """Parse, validate, and summarise. / 解析、校验并汇总。"""
    cfg = load_config()
    patch = patch or cfg.set.patch
    raw_by_lang = {lang: cdragon.load_raw(lang, patch) for lang in cfg.static.languages}
    b = build_bundle(raw_by_lang, cfg.set.id, patch, primary_lang=cfg.static.languages[0])

    t = Table(title=f"Static data — set {b.set_number} / patch {b.patch}")
    t.add_column("table / 表")
    t.add_column("rows / 行数", justify="right")
    for name in ("champions", "ability_vars", "traits", "trait_breakpoints", "items"):
        t.add_row(name, str(getattr(b, name).height))
    rprint(t)

    rprint("[bold]champions by cost / 按费用:[/]")
    rprint(b.champions.group_by("cost").len().sort("cost"))
    rprint("[bold]items by category / 装备分类:[/]")
    rprint(b.items.group_by("category").len().sort("category"))

    if b.warnings:
        rprint("[bold yellow]warnings:[/]")
        for w in b.warnings:
            rprint(f"  [yellow]•[/] {w}")
    else:
        rprint("[green]validation passed[/]")

    if export:
        out = cfg.paths.resolve("static") / patch / "tables"
        out.mkdir(parents=True, exist_ok=True)
        for name in ("champions", "ability_vars", "traits", "trait_breakpoints", "items"):
            df: pl.DataFrame = getattr(b, name)
            # list/struct columns are fine in parquet; dict 'variables'/'effects' need stringify
            for col in df.columns:
                if df[col].dtype == pl.Object:
                    df = df.with_columns(pl.col(col).map_elements(str, return_dtype=pl.Utf8))
            df.write_parquet(out / f"{name}.parquet")
        rprint(f"[green]exported[/] -> {out}")


@app.command()
def champion(api_name: str, patch: str | None = typer.Option(None)) -> None:
    """Show one champion's stats + ability variables. / 查看单个棋子。"""
    cfg = load_config()
    patch = patch or cfg.set.patch
    raw_by_lang = {lang: cdragon.load_raw(lang, patch) for lang in cfg.static.languages}
    b = build_bundle(raw_by_lang, cfg.set.id, patch, primary_lang=cfg.static.languages[0])
    row = b.champions.filter(pl.col("api_name").str.contains(api_name, literal=False))
    if row.height == 0:
        rprint(f"[red]no champion matching {api_name!r}[/]")
        raise typer.Exit(1)
    rprint(row.to_dicts()[0])
    rprint(b.ability_vars.filter(pl.col("api_name") == row["api_name"][0]))
