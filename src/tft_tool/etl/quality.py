"""Data-quality report over the DuckDB views (M3.4). / 数据质量报告。"""

from __future__ import annotations

import duckdb
import polars as pl

from tft_tool.common.settings import load_config


def query_df(con: duckdb.DuckDBPyConnection, sql: str) -> pl.DataFrame:
    """Run SQL and return a polars frame without going through pyarrow.
    执行 SQL 并返回 polars 表；不经由 pyarrow（duckdb 2.x 的 ``.pl()`` 需要它）。
    """
    rel = con.sql(sql)
    return pl.DataFrame(rel.fetchall(), schema=rel.columns, orient="row")


def report(patch: str | None = None) -> dict[str, pl.DataFrame]:
    cfg = load_config()
    db = cfg.paths.resolve("processed") / "tft.duckdb"
    con = duckdb.connect(str(db), read_only=True)
    where = f"WHERE patch = '{patch}'" if patch else ""
    out: dict[str, pl.DataFrame] = {}

    out["counts"] = query_df(
        con,
        f"""
        SELECT patch,
               COUNT(DISTINCT match_id)                           AS matches,
               COUNT(*)                                           AS participants,
               ROUND(AVG(n_units), 2)                             AS avg_units,
               ROUND(AVG(level), 2)                               AS avg_level,
               ROUND(AVG(placement), 3)                           AS avg_placement
        FROM participants {where} GROUP BY patch ORDER BY patch
        """,
    )
    # each match must have placements 1..8 exactly once / 每局名次应为 1–8 各一次
    out["bad_placement_matches"] = query_df(
        con,
        f"""
        SELECT match_id, COUNT(*) AS n, COUNT(DISTINCT placement) AS distinct_pl,
               MIN(placement) AS min_pl, MAX(placement) AS max_pl
        FROM participants {where}
        GROUP BY match_id
        HAVING n <> 8 OR distinct_pl <> 8 OR min_pl <> 1 OR max_pl <> 8
        LIMIT 20
        """,
    )
    out["stage_distribution"] = query_df(
        con,
        f"""
        SELECT stage, COUNT(*) AS eliminated_here,
               ROUND(AVG(placement), 2) AS avg_placement
        FROM participants {where} GROUP BY stage ORDER BY stage
        """,
    )
    out["units_per_level"] = query_df(
        con,
        f"""
        SELECT level, COUNT(*) AS n, ROUND(AVG(n_units), 2) AS avg_units
        FROM participants {where} GROUP BY level ORDER BY level
        """,
    )
    out["top_units"] = query_df(
        con,
        f"""
        SELECT character_id, COUNT(*) AS n, ROUND(AVG(tier), 2) AS avg_star
        FROM units {where} GROUP BY character_id ORDER BY n DESC LIMIT 15
        """,
    )
    out["top_items"] = query_df(
        con,
        f"SELECT item, COUNT(*) AS n FROM unit_items {where} "
        "GROUP BY item ORDER BY n DESC LIMIT 15",
    )
    out["trait_styles"] = query_df(
        con,
        f"SELECT style, COUNT(*) AS n FROM traits {where} GROUP BY style ORDER BY style",
    )
    con.close()
    return out
