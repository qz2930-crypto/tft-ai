# CLAUDE.md — repo conventions / 仓库约定

- Language: identifiers & commit messages in English; comments/docstrings bilingual (EN / 中文) where non-trivial; user-facing text has both languages.
- Python ≥ 3.11, managed with `uv`. Run `uv run ruff check .` and `uv run pytest -q` before committing.
- Never commit `.env`, raw match JSON, or anything under `data/` except `.gitkeep`.
- All logic is set/patch-parameterised via `config.yaml`; never hard-code champion ids.
- Metrics must follow `docs/03-metrics.md` (shrinkage k, LCB ranking, min-n thresholds). Any new metric needs a bias statement in that doc.
- Riot API calls go through `tft_tool.ingest.riot_client.RiotClient` only (rate limiting lives there).
- Module map: M1 static → M2 ingest → M3 etl → M4 stats → M5 ml → M7 api → M8 web. Keep modules importable independently.
