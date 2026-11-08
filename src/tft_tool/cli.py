"""Command-line entry point. / 命令行入口。

Usage / 用法:
    tft info                 # show resolved config / 显示当前配置
    tft static fetch         # (M1) download CommunityDragon static data
    tft ingest run           # (M2) collect matches
    tft etl build            # (M3) build DuckDB tables
    tft stats run            # (M4) compute metrics

Subcommands are registered by their modules as they are implemented.
子命令随各模块实现逐步注册。
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from tft_tool.common.settings import REPO_ROOT, load_config, load_secrets

app = typer.Typer(help="TFT AI Tool CLI / 云顶之弈分析工具命令行", no_args_is_help=True)
console = Console()


@app.callback()
def _root() -> None:
    """TFT AI Tool — see subcommands. / 见子命令。"""


@app.command()
def info() -> None:
    """Show resolved configuration (secrets masked). / 显示配置（密钥脱敏）。"""
    cfg = load_config()
    sec = load_secrets()
    key = sec.riot_api_key
    masked = f"{key[:6]}…{key[-4:]}" if len(key) > 12 else ("(unset)" if not key else "***")

    table = Table(title="TFT AI Tool — configuration / 配置")
    table.add_column("Key / 项")
    table.add_column("Value / 值")
    table.add_row("repo root", str(REPO_ROOT))
    table.add_row("set", f"{cfg.set.id} {cfg.set.name} / {cfg.set.name_zh}")
    table.add_row("patch", cfg.set.patch)
    table.add_row("tiers", ", ".join(cfg.ingest.tiers))
    table.add_row("platform / region", f"{sec.riot_platform} / {sec.riot_region}")
    table.add_row("riot api key", masked)
    table.add_row("target matches", str(cfg.ingest.target_matches))
    console.print(table)


def _register_subapps() -> None:
    """Attach module sub-apps if present. / 若模块已实现则挂载其子命令。"""
    try:
        from tft_tool.static.cli import app as static_app

        app.add_typer(static_app, name="static", help="Static data (M1) / 静态数据")
    except ImportError:
        pass
    try:
        from tft_tool.ingest.cli import app as ingest_app

        app.add_typer(ingest_app, name="ingest", help="Match collection (M2) / 对局采集")
    except ImportError:
        pass


_register_subapps()

if __name__ == "__main__":
    app()
