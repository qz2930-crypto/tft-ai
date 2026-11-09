"""`tft etl ...` subcommands. / ETL 子命令。"""

from __future__ import annotations

import logging

import typer
from rich import print as rprint

from tft_tool.common.settings import load_config
from tft_tool.etl.build import available_patches, build_patch, refresh_duckdb
from tft_tool.etl.quality import query_df, report

app = typer.Typer(no_args_is_help=True)


@app.callback()
def _root() -> None:
    """Raw JSON → DuckDB tables (M3). / 清洗建表。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


@app.command()
def build(
    patch: str | None = typer.Option(None, help="one patch; default = all under data/raw/{set}"),
) -> None:
    """Build Parquet tables and refresh DuckDB views. / 构建表并刷新视图。"""
    cfg = load_config()
    patches = [patch] if patch else available_patches(cfg.set.id)
    if not patches:
        rprint("[red]no raw data — run `tft ingest run` first[/]")
        raise typer.Exit(1)
    for p in patches:
        counts = build_patch(cfg.set.id, p)
        rprint(f"[green]✓[/] {p}: {counts}")
    db = refresh_duckdb()
    rprint(f"[green]✓[/] duckdb views refreshed -> {db}")


@app.command()
def quality(patch: str | None = typer.Option(None)) -> None:
    """Print the data-quality report. / 打印质量报告。"""
    for name, df in report(patch).items():
        rprint(f"\n[bold]{name}[/]")
        rprint(df)


@app.command()
def sql(query: str) -> None:
    """Run an ad-hoc query against tft.duckdb. / 临时查询。"""
    import duckdb

    cfg = load_config()
    con = duckdb.connect(str(cfg.paths.resolve("processed") / "tft.duckdb"), read_only=True)
    rprint(query_df(con, query))
    con.close()
