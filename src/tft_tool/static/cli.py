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
def diagnose(patch: str | None = typer.Option(None)) -> None:
    """Explain validation warnings with raw evidence. / 用原始数据解释校验警告。

    Lists: champions with null stats, champions with zero ability variables,
    cost distribution incl. non-shop units, and a sample raw champion record so
    schema drift (Unreal-era cdragon) is visible.
    """
    cfg = load_config()
    patch = patch or cfg.set.patch
    lang = cfg.static.languages[0]
    raw = cdragon.load_raw(lang, patch)
    sd = cdragon.select_set(raw, cfg.set.id)
    b = build_bundle({lang: raw}, cfg.set.id, patch, primary_lang=lang)

    champs = b.champions
    rprint(f"[bold]set entry:[/] number={sd.get('number')} mutator={sd.get('mutator')!r} "
           f"name={sd.get('name')!r}; keys={sorted(sd.keys())}")

    rprint("\n[bold]cost distribution (incl. non-shop units) / 费用分布:[/]")
    rprint(champs.group_by("cost").agg(pl.col("api_name")).sort("cost"))

    null_stats = champs.filter(pl.any_horizontal([pl.col(f"stat_{k}").is_null()
                                                 for k in ("hp", "damage", "attackSpeed")]))
    rprint(f"\n[bold]champions with null core stats ({null_stats.height}):[/]")
    rprint(null_stats.select("api_name", "cost", "traits").to_dicts())

    with_vars: set[str] = set()
    if b.ability_vars.height:
        with_vars = set(b.ability_vars["api_name"].unique().to_list())
    no_vars = [a for a in champs["api_name"].to_list() if a not in with_vars]
    rprint(f"\n[bold]champions with ZERO ability variables ({len(no_vars)}/{champs.height}):[/]")
    rprint(no_vars)

    # raw record for a shop champion so we can see the real schema
    sample = next((c for c in sd.get("champions", [])
                   if c.get("cost") in (1, 2, 3, 4, 5) and c.get("traits")), None)
    if sample:
        rprint(f"\n[bold]raw record sample ({sample.get('apiName')}) top-level keys:[/] "
               f"{sorted(sample.keys())}")
        rprint("[bold]ability keys:[/]", sorted((sample.get("ability") or {}).keys()))
        rprint("[bold]ability record:[/]")
        rprint(sample.get("ability"))
        rprint("[bold]stats record:[/]")
        rprint(sample.get("stats"))


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
