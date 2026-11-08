"""Build the docker-py client the transcode dispatcher and the ripper
manager spawn containers with."""

import logging

logger = logging.getLogger(__name__)


def build_docker_client(docker_host: str = "", *, purpose: str = "transcode dispatcher") -> object | None:
    """Construct a docker-py client. When `docker_host` is set (e.g.
    "ssh://sam@transcoder-server"), target that remote daemon so transcode
    containers spawn on a remote GPU host; otherwise use the local socket.
    Returns None if the client can't be built (dev without the socket, or an
    unreachable/misconfigured remote host) so the caller's docker-backed
    feature (named by `purpose`, e.g. "ripper manager") stays disabled rather
    than crashing the backend."""
    try:
        import docker  # type: ignore[import-untyped]

        client: object = docker.DockerClient(base_url=docker_host) if docker_host else docker.from_env()
        return client
    except Exception as exc:
        logger.warning("docker-py client unavailable: %s — %s disabled", exc, purpose)
        return None
