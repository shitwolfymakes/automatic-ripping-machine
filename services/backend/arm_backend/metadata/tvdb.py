import logging

import httpx

from arm_backend.metadata.base import LookupError, LookupTimeout

logger = logging.getLogger("arm_backend.metadata.tvdb")

_BASE_URL = "https://api4.thetvdb.com/v4"


class TVDBClient:
    """TVDB v4 client. Tier-1 scope: key validation only.

    TVDB v4 authenticates via a login handshake: POST /v4/login with the
    API key returns a bearer token. For key validation we only need the
    login to succeed; episode-matching methods are a later (Tier-4) addition.
    """

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http

    async def validate_key(self) -> None:
        """POST /v4/login. Returns None on success; raises LookupError on
        auth/transport failure, LookupTimeout on timeout."""
        try:
            r = await self._http.post(f"{_BASE_URL}/login", json={"apikey": self._api_key})
        except httpx.TimeoutException as e:
            raise LookupTimeout("tvdb login timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"tvdb login transport error: {e}") from e

        if r.status_code == 401:
            logger.warning("tvdb auth_failed status=401")
            raise LookupError("tvdb auth failed")
        if r.status_code >= 500:
            raise LookupError(f"tvdb login 5xx status={r.status_code}")
        if r.status_code != 200:
            raise LookupError(f"tvdb login status={r.status_code}")
