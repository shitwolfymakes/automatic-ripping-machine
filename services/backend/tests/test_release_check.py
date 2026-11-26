"""The latest-stable-release check: version ordering, the GitHub fetch, the
cache loop, and the version endpoint's three states."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from arm_backend import release_check
from arm_backend.release_check import Release, ReleaseCheckError

REPO_ROOT = Path(__file__).resolve().parents[3]

# (a, b, a older than b)
VERSION_CASES: list[tuple[str, str, bool]] = [
    ("3.0.0-rc3", "3.0.0", True),
    ("3.0.0", "3.0.0-rc3", False),
    ("3.0.0-rc2", "3.0.0-rc10", True),
    ("3.0.0-rc10", "3.0.0-rc2", False),
    ("3.0.0-rc1", "3.0.0-rc1", False),
    ("2.24.4", "3.0.0-rc3", True),
    ("3.0.0-rc3", "2.24.4", False),
    ("v3.0.0", "3.0.1", True),
    ("3.0.1", "v3.0.0", False),
    ("v3.1.0", "3.1.0", False),
    ("3.0.0", "3.0.0", False),
    ("3.9.0", "3.10.0", True),
    ("3.1", "3.1.0", True),
    ("0.0.0+unknown", "3.0.0", True),
    ("3.0.0", "0.0.0+unknown", False),
    ("garbage", "also-garbage", False),
    ("junk", "junk", False),
]


@pytest.fixture(autouse=True)
def _clean_cache():
    release_check.cache.release = None
    yield
    release_check.cache.release = None


@pytest.mark.parametrize(("a", "b", "older"), VERSION_CASES)
def test_version_older_table(a: str, b: str, older: bool) -> None:
    assert release_check.version_older(a, b) is older


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.parametrize(("a", "b", "older"), VERSION_CASES)
def test_version_older_agrees_with_armctl(a: str, b: str, older: bool) -> None:
    script = (REPO_ROOT / "deploy" / "armctl.sh").read_text().splitlines()
    start = script.index("version_older() {")
    end = script.index("}", start)
    function = "\n".join(script[start : end + 1])
    result = subprocess.run(
        ["bash", "-c", f'{function}\nversion_older "$1" "$2"', "bash", a, b],
        capture_output=True,
        check=False,
    )
    assert (result.returncode == 0) is older


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3.0.0", ((3, 0, 0), "")),
        ("v3.1.2-rc1", ((3, 1, 2), "rc1")),
        ("0.0.0+unknown", None),
        ("main", None),
        ("", None),
    ],
)
def test_parse_version(text: str, expected: object) -> None:
    assert release_check.parse_version(text) == expected


@pytest.mark.parametrize(
    ("running", "tag", "expected"),
    [
        ("3.0.0-rc3", "v3.0.0", True),
        ("3.0.0-rc3", "2.24.4", False),
        ("3.0.0", "3.0.0", False),
        ("0.0.0+unknown", "3.0.0", False),
        ("3.0.0", "nightly", False),
    ],
)
def test_update_available(running: str, tag: str, expected: bool) -> None:
    assert (
        release_check.update_available(running, Release(tag=tag, url="https://github.com/o/r/releases/tag/v3.1.0"))
        is expected
    )


def test_release_repo_defaults_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARMCTL_RELEASE_REPO", raising=False)
    assert release_check.release_repo() == release_check.DEFAULT_REPO
    monkeypatch.setenv("ARMCTL_RELEASE_REPO", "  ")
    assert release_check.release_repo() == release_check.DEFAULT_REPO
    monkeypatch.setenv("ARMCTL_RELEASE_REPO", "me/fork")
    assert release_check.release_repo() == "me/fork"


@pytest.mark.parametrize("value", ["me/fork; rm -rf /", "../etc", "a/b/c", "javascript:x", "me", "/fork", "me/"])
def test_release_repo_ignores_a_value_that_is_not_owner_slash_repo(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    # The name goes into the API URL and the repo link, so anything else falls back to upstream.
    monkeypatch.setenv("ARMCTL_RELEASE_REPO", value)
    assert release_check.release_repo() == release_check.DEFAULT_REPO


def test_release_repo_accepts_dots_dashes_and_underscores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARMCTL_RELEASE_REPO", "my-org/arm_fork.v3")
    assert release_check.release_repo() == "my-org/arm_fork.v3"


def test_repo_url_follows_the_release_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARMCTL_RELEASE_REPO", raising=False)
    assert release_check.repo_url() == f"https://github.com/{release_check.DEFAULT_REPO}"
    monkeypatch.setenv("ARMCTL_RELEASE_REPO", "me/fork")
    assert release_check.repo_url() == "https://github.com/me/fork"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _fetch(handler) -> Release | None:
    async with _client(handler) as client:
        return await release_check.latest_stable_release(client, "o/r")


def test_latest_stable_release_success_sends_generic_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"tag_name": "v3.1.0", "html_url": "https://github.com/o/r/releases/tag/v1", "prerelease": False}
        )

    assert asyncio.run(_fetch(handler)) == Release(tag="v3.1.0", url="https://github.com/o/r/releases/tag/v1")
    request = seen[0]
    assert request.url == "https://api.github.com/repos/o/r/releases/latest"
    assert request.headers["user-agent"] == "arm-release-check"
    assert "authorization" not in request.headers


@pytest.mark.parametrize("flag", ["prerelease", "draft"])
def test_latest_stable_release_ignores_prerelease_and_draft(flag: str) -> None:
    body = {"tag_name": "v9.0.0-rc1", "html_url": "https://github.com/o/r/releases/tag/v1", flag: True}
    assert asyncio.run(_fetch(lambda _: httpx.Response(200, json=body))) is None


@pytest.mark.parametrize("status", [404, 403, 500, 503])
def test_latest_stable_release_http_errors_raise(status: int) -> None:
    with pytest.raises(ReleaseCheckError, match=f"HTTP {status}"):
        asyncio.run(_fetch(lambda _: httpx.Response(status)))


def test_latest_stable_release_network_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(ReleaseCheckError, match="ConnectError"):
        asyncio.run(_fetch(handler))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json=["a"]),
        httpx.Response(200, json={"html_url": "https://github.com/o/r/releases/tag/v1"}),
        httpx.Response(200, json={"tag_name": "v1", "html_url": ""}),
        # The URL becomes a link on the page, so only a GitHub page is accepted.
        httpx.Response(200, json={"tag_name": "v1", "html_url": "javascript:alert(document.domain)"}),
        httpx.Response(200, json={"tag_name": "v1", "html_url": "https://evil.example/r"}),
        httpx.Response(200, json={"tag_name": "v1", "html_url": "https://github.com.evil.example/r"}),
        httpx.Response(200, json={"tag_name": "v1", "html_url": "http://github.com/o/r"}),
    ],
)
def test_latest_stable_release_bad_payload_raises(response: httpx.Response) -> None:
    with pytest.raises(ReleaseCheckError):
        asyncio.run(_fetch(lambda _: response))


class _StopLoop(Exception):
    pass


def _run_loop(handler, sleeps: list[float], *, stop_after: int) -> None:
    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= stop_after:
            raise _StopLoop

    async def go() -> None:
        async with _client(handler) as client:
            await release_check.release_check_loop(client, "o/r", sleep)

    with pytest.raises(_StopLoop):
        asyncio.run(go())


def test_loop_checks_at_start_then_every_six_hours() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            200, json={"tag_name": f"v3.{len(calls)}.0", "html_url": "https://github.com/o/r/releases/tag/v1"}
        )

    sleeps: list[float] = []
    _run_loop(handler, sleeps, stop_after=3)
    assert sleeps == [6 * 3600] * 3
    assert len(calls) == 3
    assert release_check.cache.release == Release(tag="v3.3.0", url="https://github.com/o/r/releases/tag/v1")


def test_loop_warns_once_per_failure_streak_and_rearms_after_success(caplog: pytest.LogCaptureFixture) -> None:
    statuses = iter([500, 500, 403, 200, 500, 500])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        if status == 200:
            return httpx.Response(
                200, json={"tag_name": "v3.1.0", "html_url": "https://github.com/o/r/releases/tag/v1"}
            )
        return httpx.Response(status)

    with caplog.at_level(logging.WARNING, logger="arm_backend.release_check"):
        _run_loop(handler, [], stop_after=6)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert "HTTP 500" in warnings[0].getMessage()


def test_failure_keeps_the_last_good_release() -> None:
    answers = iter([200, 500])

    def handler(request: httpx.Request) -> httpx.Response:
        if next(answers) == 200:
            return httpx.Response(
                200, json={"tag_name": "v3.1.0", "html_url": "https://github.com/o/r/releases/tag/v1"}
            )
        return httpx.Response(500)

    _run_loop(handler, [], stop_after=2)
    assert release_check.cache.release == Release(tag="v3.1.0", url="https://github.com/o/r/releases/tag/v1")


def test_prerelease_answer_clears_the_cache() -> None:
    release_check.cache.release = Release(tag="v3.0.0", url="https://github.com/o/r/releases/tag/v3.1.0")
    _run_loop(
        lambda _: httpx.Response(
            200,
            json={
                "tag_name": "v4.0.0-rc1",
                "html_url": "https://github.com/o/r/releases/tag/v3.1.0",
                "prerelease": True,
            },
        ),
        [],
        stop_after=1,
    )
    assert release_check.cache.release is None


def test_unexpected_exception_does_not_end_the_loop_and_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(
                200, json={"tag_name": "v3.1.0", "html_url": "https://github.com/o/r/releases/tag/v3.1.0"}
            )
        raise httpx.InvalidURL("bad repo")

    sleeps: list[float] = []
    with caplog.at_level(logging.WARNING, logger="arm_backend.release_check"):
        _run_loop(handler, sleeps, stop_after=4)
    assert sleeps == [6 * 3600] * 4
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    assert release_check.cache.release == Release(tag="v3.1.0", url="https://github.com/o/r/releases/tag/v3.1.0")


def test_cancellation_is_not_swallowed() -> None:
    async def handler_cancel(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    async def go() -> None:
        async with _client(handler_cancel) as client:
            await release_check.release_check_loop(client, "o/r")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())


def test_404_warning_says_there_are_no_published_releases() -> None:
    with pytest.raises(ReleaseCheckError, match="no published releases"):
        asyncio.run(_fetch(lambda _: httpx.Response(404)))


def test_lifespan_starts_and_cancels_the_release_check(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from arm_backend import main as main_mod

    started: list[tuple[object, str]] = []

    async def fake_loop(client: object, repo: str) -> None:
        started.append((client, repo))
        await asyncio.sleep(3600)

    monkeypatch.setattr(release_check, "release_check_loop", fake_loop)
    monkeypatch.setenv("ARMCTL_RELEASE_REPO", "me/fork")

    async def go() -> asyncio.Task[None]:
        app = SimpleNamespace(state=SimpleNamespace(http="client"))
        services = main_mod._BackendServices(app)  # type: ignore[arg-type]
        services._start_release_check()
        await asyncio.sleep(0)
        task = services._release_check_task
        await services._stop_release_check()
        return task

    task = asyncio.run(go())
    assert started == [("client", "me/fork")]
    assert task.cancelled()
