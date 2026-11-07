"""Process-wide environment for the backend suite.

`arm_backend.config` builds its `Settings` singleton at import, and the two
required variables must exist before the first test module imports the
package. pytest loads this conftest before it imports any module under this
directory, whichever way the suite is invoked (the testpaths-driven root run,
a single file, any subset or order), so the values are defined here once and
nowhere else. Test modules hard-code "tok-service" in their service-token
headers, so the assignment is unconditional: a value exported by the
developer's shell must not reach the singleton either.
"""

import os

import pytest

os.environ["DATABASE_URL"] = "postgresql://x:x@localhost/x"
os.environ["ARM_SERVICE_TOKEN"] = "tok-service"


@pytest.fixture(autouse=True)
def _unspaced_musicbrainz_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the MusicBrainz client's 1 s spacing between requests.

    The client sleeps for real to stay under MusicBrainz's 1 req/s limit, and
    across the metadata tests that adds up to over a minute of waiting. Tests
    of the spacing itself set their own interval on top of this one. The
    import sits in the fixture so `arm_backend` is never imported before the
    environment above is set.
    """
    from arm_backend.metadata import musicbrainz

    monkeypatch.setattr(musicbrainz, "_MIN_INTERVAL_SECONDS", 0.0)
