"""metadata_provider column on the Config singleton."""

from __future__ import annotations

from arm_common import Config


def test_config_has_metadata_provider_field() -> None:
    cfg = Config(id=1)
    # Field(default="tmdb") fires in Python, so a bare in-memory Config already
    # carries "tmdb"; the DB-level server_default is the backup for raw INSERTs.
    assert cfg.metadata_provider == "tmdb"
    cfg.metadata_provider = "omdb"
    assert cfg.metadata_provider == "omdb"
