"""Masking of credentials embedded in URLs before they are shown or logged."""

from urllib.parse import urlsplit, urlunsplit


def strip_userinfo(url: str) -> str:
    """Replace any `user:pass@` in a URL with `***@`; non-URLs pass through, malformed ones are masked."""
    try:
        parts = urlsplit(url)
    except ValueError:
        # Unparseable: fail closed, the raw string may carry credentials.
        return "***"
    if "@" not in parts.netloc:
        # An `@` outside the host part means urlsplit cut the userinfo short
        # (an unencoded `#`, `/` or `?` in it, or no scheme): fail closed.
        return "***" if "@" in url else url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit(parts._replace(netloc=f"***@{host}"))
