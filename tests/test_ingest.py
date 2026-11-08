"""Collector logic without network. / 不联网的采集逻辑测试。"""

from datetime import UTC, datetime
from pathlib import Path

from tft_tool.common.settings import PatchWindow, SetConfig
from tft_tool.ingest.index import IngestIndex


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp() * 1000)


def test_patch_for_uses_calendar() -> None:
    sc = SetConfig(
        id=18, name="x", name_zh="x", patch="18.6",
        patches=[
            PatchWindow(tag="18.5", start=datetime(2026, 10, 21, tzinfo=UTC)),
            PatchWindow(tag="18.6", start=datetime(2026, 11, 4, tzinfo=UTC)),
        ],
    )
    assert sc.patch_for(_ms("2026-11-05T12:00:00")) == "18.6"
    assert sc.patch_for(_ms("2026-10-25T12:00:00")) == "18.5"
    assert sc.patch_for(_ms("2026-10-01T12:00:00")) is None


def test_index_roundtrip(tmp_path: Path) -> None:
    idx = IngestIndex(tmp_path / "ix.sqlite")
    assert idx.upsert_players([{"puuid": "p1", "leaguePoints": 900}, {"puuid": "p2"}], "na1") == 2
    assert idx.upsert_players([{"puuid": "p1", "leaguePoints": 950}], "na1") == 1  # update
    assert idx.n_players() == 2
    assert idx.add_match_ids(["NA1_1", "NA1_2", "NA1_1"]) == 2
    assert idx.pending() == ["NA1_1", "NA1_2"]
    idx.mark("NA1_1", "done", set_number=18, patch="18.6", game_datetime=1, queue_id=1100)
    idx.mark("NA1_2", "skipped", error="queue_id=1130")
    assert idx.pending() == []
    assert idx.status_counts() == {"done": 1, "skipped": 1}
    assert idx.patch_counts() == {"18.6": 1}
    idx.close()
