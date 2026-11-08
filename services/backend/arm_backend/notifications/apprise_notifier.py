"""The apprise adapter: the notifier apprise deliveries go through, and URL
validation.

URL credentials never appear in log output. `redact_apprise_url(url)` (in
`url_composer`) returns `"<scheme>://****"` — scheme-only redaction is
conservative because Apprise providers stash credentials in netloc, path,
or query depending on the scheme.

`first_invalid_apprise_url(urls)` lives here too so the apprise import
stays in one module; channel edits use it to validate a channel's URL at
PATCH-time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import apprise

from arm_backend.notifications.url_composer import redact_apprise_url

if TYPE_CHECKING:
    from collections.abc import Sequence


def first_invalid_apprise_url(urls: list[str]) -> str | None:
    """Return the first URL `apprise.Apprise().add(url)` rejects, else None.

    Used by channel edits to validate a URL before it lands in the DB.
    Each URL gets a fresh Apprise() to keep validation side-effect-free —
    `.add()` mutates the bag.
    """
    for url in urls:
        ap = apprise.Apprise()
        if not ap.add(url):
            return url
    return None


class AppriseNotifier(Protocol):
    async def notify(self, urls: Sequence[str], title: str, body: str) -> None: ...


class AppriseDeliveryError(RuntimeError):
    """Apprise reported failure. apprise signals by RETURN VALUE (False on
    delivery failure, None on an empty/unparseable URL bag) and swallows
    exceptions internally — this converts that into the exception the
    listeners' ok/last_error bookkeeping expects; without it a failed send
    is indistinguishable from success."""


class RealAppriseNotifier:
    """Production notifier. Wraps `apprise.Apprise().async_notify`.

    Brands outbound notifications via an `AppriseAsset`: the sender is always
    labelled "ARM", and when `image_url` is set, that public image becomes the
    Discord avatar / embed thumbnail (and the equivalent on other services).
    """

    def __init__(self, image_url: str = "") -> None:
        self._image_url = image_url

    def _asset(self) -> "apprise.AppriseAsset":
        asset = apprise.AppriseAsset(app_id="ARM", app_desc="Automatic Ripping Machine")
        if self._image_url:
            # A static URL (no {TYPE}/{XY} placeholders) is returned verbatim by
            # AppriseAsset.image_url() for every notify type — so the same ARM
            # image is used for success/failure/info and for both the avatar mask
            # and the logo variant.
            asset.image_url_mask = self._image_url
            asset.image_url_logo = self._image_url
        return asset

    async def notify(self, urls: Sequence[str], title: str, body: str) -> None:
        ap = apprise.Apprise(asset=self._asset())
        for url in urls:
            if not ap.add(url):
                raise AppriseDeliveryError(f"apprise rejected url {redact_apprise_url(url)}")
        # apprise's async_notify fans out URLs internally; one call covers
        # every configured destination for this event.
        result = await ap.async_notify(title=title, body=body)
        if result is not True:
            raise AppriseDeliveryError(f"apprise delivery failed (result={result!r})")
