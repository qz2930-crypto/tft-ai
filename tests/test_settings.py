"""Smoke tests for configuration loading. / 配置加载冒烟测试。"""

from tft_tool.common.settings import REPO_ROOT, load_config


def test_config_loads() -> None:
    cfg = load_config()
    assert cfg.set.id == 18
    assert "CHALLENGER" in cfg.ingest.tiers
    assert cfg.analysis.shrinkage_k > 0
    assert cfg.analysis.min_n_display <= cfg.analysis.min_n_reliable


def test_paths_resolve_inside_repo() -> None:
    cfg = load_config()
    for name in ("raw", "processed", "results", "static"):
        p = cfg.paths.resolve(name)
        assert REPO_ROOT in p.parents
