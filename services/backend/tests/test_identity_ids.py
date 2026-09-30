"""Show-id resolution across episode-list providers (design spec 6.2)."""

from arm_common import Config, DiscType, Job, JobStatus
from arm_common.schemas import ExternalIds

from arm_backend.identity.episodes.model import Episode
from arm_backend.identity.http import SourceError, SourceMiss
from arm_backend.identity.ids import current_ids, resolve_show_ids


def _job(meta: dict | None = None) -> Job:
    return Job(
        id="job_1",
        drive_id="drv_1",
        disc_type=DiscType.BLURAY,
        status=JobStatus.IDENTIFIED,
        metadata_json=meta or {},
    )


class FakeProvider:
    """Minimal EpisodeListProvider double: records the ids it was called
    with and returns a canned result (or raises a canned error)."""

    def __init__(self, source_id: str, id_field: str, *, result: str | None = None, error: Exception | None = None):
        self.source_id = source_id
        self.id_field = id_field
        self.http = None
        self._result = result
        self._error = error
        self.calls: list[ExternalIds] = []

    def configured(self, cfg: Config) -> str | None:
        return None

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        self.calls.append(ids)
        if self._error is not None:
            raise self._error
        return self._result

    async def seasons(self, show_id: str) -> list[int]:
        return []

    async def season(self, show_id: str, number: int) -> list[Episode]:
        return []


# ---------------------------------------------------------------------------
# current_ids
# ---------------------------------------------------------------------------


def test_current_ids_empty_job() -> None:
    assert current_ids(_job()) == ExternalIds()


def test_current_ids_no_identity_section() -> None:
    assert current_ids(_job({"scan_result": {"x": 1}})) == ExternalIds()


def test_current_ids_non_dict_identity_section() -> None:
    assert current_ids(_job({"identity": "garbage"})) == ExternalIds()


def test_current_ids_non_dict_external_ids() -> None:
    job = _job({"identity": {"provider": "tmdb", "external_ids": "garbage"}})
    assert current_ids(job) == ExternalIds()


def test_current_ids_invalid_external_ids_logs_and_is_empty(caplog) -> None:
    # A dict value where ExternalIds expects str|None fails pydantic
    # validation (unlike an int, which pydantic happily coerces to str).
    job = _job({"identity": {"external_ids": {"tmdb": {"nested": 1}}}})
    assert current_ids(job) == ExternalIds()
    assert "external_ids invalid" in caplog.text


def test_current_ids_valid() -> None:
    job = _job({"identity": {"external_ids": {"tmdb": "1399", "imdb": "tt0944947"}}})
    ids = current_ids(job)
    assert ids.tmdb == "1399"
    assert ids.imdb == "tt0944947"


# ---------------------------------------------------------------------------
# resolve_show_ids
# ---------------------------------------------------------------------------


async def test_existing_id_is_not_re_resolved() -> None:
    job = _job({"identity": {"external_ids": {"tmdb": "1399"}}})
    provider = FakeProvider("episodes_tmdb", "tmdb", result="9999")

    result = await resolve_show_ids(job, [provider])

    assert result.tmdb == "1399"
    assert provider.calls == []


async def test_new_id_persisted_other_keys_survive() -> None:
    job = _job(
        {
            "scan_result": {"x": 1},
            "identity": {
                "provider": "manual",
                "external_ids": {},
                "overview": "a show",
            },
        }
    )
    before = job.metadata_json
    provider = FakeProvider("episodes_tvmaze", "tvmaze", result="123")

    result = await resolve_show_ids(job, [provider])

    assert result.tvmaze == "123"
    assert provider.calls == [ExternalIds()]
    assert job.metadata_json is not before  # reassigned, not mutated in place
    assert job.metadata_json["scan_result"] == {"x": 1}
    assert job.metadata_json["identity"]["provider"] == "manual"
    assert job.metadata_json["identity"]["overview"] == "a show"
    assert job.metadata_json["identity"]["external_ids"]["tvmaze"] == "123"


async def test_provider_error_leaves_field_empty_others_still_resolve(caplog) -> None:
    job = _job({"identity": {"external_ids": {}}})
    failing = FakeProvider("episodes_tvdb", "tvdb", error=SourceError("boom"))
    ok = FakeProvider("episodes_tmdb", "tmdb", result="42")

    result = await resolve_show_ids(job, [failing, ok])

    assert result.tvdb is None
    assert result.tmdb == "42"
    assert "resolve_show_id failed source=episodes_tvdb" in caplog.text


async def test_provider_miss_leaves_field_empty() -> None:
    job = _job({"identity": {"external_ids": {}}})
    provider = FakeProvider("episodes_tvdb", "tvdb", error=SourceMiss("not found"))

    result = await resolve_show_ids(job, [provider])

    assert result.tvdb is None


async def test_provider_returning_none_leaves_field_empty_and_no_write() -> None:
    job = _job({"identity": {"external_ids": {}}})
    before = job.metadata_json
    provider = FakeProvider("episodes_tvdb", "tvdb", result=None)

    result = await resolve_show_ids(job, [provider])

    assert result.tvdb is None
    assert job.metadata_json is before  # nothing new found, nothing written


async def test_earlier_resolved_id_is_visible_to_later_provider() -> None:
    job = _job({"identity": {"external_ids": {}}})
    seen: list[ExternalIds] = []

    class Recorder(FakeProvider):
        async def resolve_show_id(self, ids: ExternalIds) -> str | None:
            seen.append(ids)
            return "200"

    first = FakeProvider("episodes_tmdb", "tmdb", result="100")
    second = Recorder("episodes_tvmaze", "tvmaze")

    result = await resolve_show_ids(job, [first, second])

    assert result.tmdb == "100"
    assert result.tvmaze == "200"
    assert seen[0].tmdb == "100"


async def test_provider_asked_at_most_once() -> None:
    job = _job({"identity": {"external_ids": {}}})
    provider = FakeProvider("episodes_tmdb", "tmdb", result="1")

    await resolve_show_ids(job, [provider])

    assert len(provider.calls) == 1


async def test_job_without_identity_section_returns_ids_without_writing() -> None:
    job = _job({"scan_result": {"x": 1}})
    before = job.metadata_json
    provider = FakeProvider("episodes_tmdb", "tmdb", result="55")

    result = await resolve_show_ids(job, [provider])

    assert result.tmdb == "55"
    assert job.metadata_json is before
    assert "identity" not in job.metadata_json


async def test_job_with_non_dict_identity_section_returns_ids_without_writing() -> None:
    job = _job({"identity": "garbage"})
    before = job.metadata_json
    provider = FakeProvider("episodes_tmdb", "tmdb", result="55")

    result = await resolve_show_ids(job, [provider])

    assert result.tmdb == "55"
    assert job.metadata_json is before


async def test_persist_false_resolves_without_writing() -> None:
    job = _job({"identity": {"provider": "tmdb", "external_ids": {"imdb": "tt1"}}})
    before = job.metadata_json
    provider = FakeProvider("episodes_tvmaze", "tvmaze", result="123")

    result = await resolve_show_ids(job, [provider], persist=False)

    assert result.tvmaze == "123"
    assert result.imdb == "tt1"
    assert job.metadata_json is before
    assert job.metadata_json["identity"]["external_ids"] == {"imdb": "tt1"}
