"""`StageStatus` and the `TrackStage` model: VARCHAR-backed status, the id prefix, the one-row-per-track key."""

from __future__ import annotations

from arm_common import StageStatus, TrackStage
from arm_common.ulid import is_valid_id


def test_stage_status_values() -> None:
    assert [s.value for s in StageStatus] == ["pending", "copying", "staged", "failed", "stalled"]


def test_a_new_stage_has_a_stg_id_and_starts_empty() -> None:
    stage = TrackStage(track_id="trk_a", job_id="job_a", source_path="/raw/a", dest_path="/raw/.staging/a")
    assert is_valid_id("stg", stage.id)
    assert stage.bytes_durable == 0 and stage.attempts == 0
    assert stage.linked is None and stage.last_error is None


def test_the_status_column_is_a_plain_varchar_defaulting_to_pending() -> None:
    column = TrackStage.__table__.columns["status"]
    assert str(column.type) == "VARCHAR"
    assert column.server_default is not None and column.server_default.arg == "pending"  # type: ignore[attr-defined]
    assert not column.nullable


def test_one_stage_row_per_track_and_cascades_follow_the_track_and_job() -> None:
    table = TrackStage.__table__
    assert table.columns["track_id"].unique
    cascades = {fk.parent.name: fk.ondelete for fk in table.foreign_keys}
    assert cascades == {"track_id": "CASCADE", "job_id": "CASCADE"}
