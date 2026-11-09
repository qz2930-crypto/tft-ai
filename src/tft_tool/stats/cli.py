"""`tft stats ...` subcommands. / 统计子命令。"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import typer
from rich import print as rprint

from tft_tool.common.settings import load_config
from tft_tool.stats import metrics
from tft_tool.stats.core import visible
from tft_tool.stats.load import load_tables, shop_units

app = typer.Typer(no_args_is_help=True)

TABLE_FUNCS = {
    "champion_baseline": lambda t, s: metrics.champion_baseline(t, s),
    "champion_baseline_by_level": lambda t, s: metrics.champion_baseline_by_level(t, s),
    "champion_items": lambda t, s: metrics.champion_items(t, s),
    "champion_items_pooled": lambda t, s: metrics.champion_items_pooled(t, s),
    "champion_pairs": lambda t, s: metrics.champion_pairs(t, s),
    "trait_tiers": lambda t, s: metrics.trait_tiers(t),
    "stage_power": lambda t, s: metrics.stage_power(t, s),
}


@app.callback()
def _root() -> None:
    """Statistical analysis (M4). / 统计分析。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def results_dir(patch: str) -> Path:
    cfg = load_config()
    return cfg.paths.resolve("results") / str(cfg.set.id) / patch


@app.command()
def run(
    patch: str | None = typer.Option(None),
    only: str | None = typer.Option(None, help="comma-separated table names"),
) -> None:
    """Compute all metric tables for a patch → data/results/{set}/{patch}/. / 计算全部指标。"""
    cfg = load_config()
    patch = patch or cfg.set.patch
    t = load_tables(patch)
    shop = shop_units(patch)
    if shop is None:
        rprint("[yellow]static data not found for this patch — unit filter disabled[/]")
    out = results_dir(patch)
    out.mkdir(parents=True, exist_ok=True)
    names = [n.strip() for n in only.split(",")] if only else list(TABLE_FUNCS)
    manifest: dict = {
        "set": cfg.set.id, "patch": patch, "n_matches": t.n_matches,
        "n_participants": t.participants.height,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_version": _git_sha(),
        "metrics_doc": "docs/03-metrics.md",
        "params": cfg.analysis.model_dump(),
        "tables": {},
    }
    for name in names:
        df = TABLE_FUNCS[name](t, shop)
        df.write_parquet(out / f"{name}.parquet")
        n_vis = visible(df).height if "reliability" in df.columns else df.height
        manifest["tables"][name] = {"rows": df.height, "visible": n_vis}
        rprint(f"[green]✓[/] {name}: {df.height} rows")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    rprint(f"[green]✓[/] manifest -> {out / 'manifest.json'}")


@app.command()
def show(
    table: str,
    patch: str | None = typer.Option(None),
    champion: str | None = typer.Option(None, help="filter by character_id substring"),
    top: int = typer.Option(25),
    all_rows: bool = typer.Option(False, help="include hidden (n < min_n_display)"),
) -> None:
    """Print a results table. / 查看结果表。"""
    cfg = load_config()
    patch = patch or cfg.set.patch
    df = pl.read_parquet(results_dir(patch) / f"{table}.parquet")
    if not all_rows and "reliability" in df.columns:
        df = visible(df)
    if champion:
        col = "character_id" if "character_id" in df.columns else "a"
        df = df.filter(pl.col(col).str.contains(champion))
    pl.Config.set_tbl_rows(top)
    pl.Config.set_tbl_cols(20)
    pl.Config.set_fmt_str_lengths(60)
    rprint(df.head(top))
