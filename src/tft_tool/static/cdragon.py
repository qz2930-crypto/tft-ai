"""CommunityDragon TFT static data downloader. / CommunityDragon 静态数据下载。

Source files (one per language) / 数据源（每语言一个文件）:
    https://raw.communitydragon.org/{branch}/cdragon/tft/{lang}.json

Files are archived per patch under ``data/static/{patch}/{lang}.json`` and never
overwritten, so every analysis snapshot can be reproduced against the exact
static data it was built with.
文件按 patch 存档于 ``data/static/{patch}/{lang}.json``，不覆盖，保证结果可复现。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from tft_tool.common.settings import load_config

log = logging.getLogger(__name__)


def cdragon_url(lang: str, branch: str | None = None, base: str | None = None) -> str:
    cfg = load_config().static
    return f"{base or cfg.cdragon_base}/{branch or cfg.cdragon_branch}/cdragon/tft/{lang}.json"


def static_path(patch: str, lang: str) -> Path:
    cfg = load_config()
    return cfg.paths.resolve("static") / patch / f"{lang}.json"


def fetch(lang: str, patch: str | None = None, force: bool = False, timeout: float = 120.0) -> Path:
    """Download one language file, archive under the patch dir. / 下载并按版本归档。"""
    cfg = load_config()
    patch = patch or cfg.set.patch
    dest = static_path(patch, lang)
    if dest.exists() and not force:
        log.info("static %s/%s already present, skipping (use --force)", patch, lang)
        return dest
    url = cdragon_url(lang)
    log.info("downloading %s", url)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    log.info("saved %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    return dest


def load_raw(lang: str, patch: str | None = None) -> dict[str, Any]:
    """Load an archived file. / 读取已归档文件。"""
    cfg = load_config()
    path = static_path(patch or cfg.set.patch, lang)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `tft static fetch` first / 请先执行下载")
    return json.loads(path.read_text(encoding="utf-8"))


def select_set(raw: dict[str, Any], set_number: int) -> dict[str, Any]:
    """Pick the ``setData`` entry for a set. / 选出指定赛季的 setData。

    cdragon ships every set in one file; entries carry ``number`` and ``mutator``
    (e.g. ``TFTSet18``). Some mid-set entries share a number — we prefer the one
    whose mutator is exactly ``TFTSet{n}`` and fall back to the first match.
    """
    candidates = [s for s in raw.get("setData", []) if s.get("number") == set_number]
    if not candidates:
        nums = sorted({s.get("number") for s in raw.get("setData", [])})
        raise KeyError(f"set {set_number} not in setData (available: {nums})")
    exact = [s for s in candidates if s.get("mutator") == f"TFTSet{set_number}"]
    return (exact or candidates)[0]
