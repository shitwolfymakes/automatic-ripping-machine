# Security Policy

## Supported Versions

Automatic Ripping Machine v3 is developed trunk-based with rolling releases:
`main` is always releasable, and stable versions are cut as semver tags
(`v3.*`) on `main`.

Two kinds of images are published, and only one is security-supported:

- **`:latest`** tracks `main` HEAD — it is republished on every push to `main`
  and rebuilt nightly. This is the **bleeding edge** and is **not** a support
  target. Run it for testing, not in production.
- **Stable tags (`v3.x.y`)** are the supported artifacts. The newest stable tag
  is rebuilt weekly against fresh base layers, so a `docker compose pull` of
  that tag picks up base-image CVE patches without us cutting a new release.

Security fixes roll **forward** into the next stable tag — they are not
back-ported to older tags.

| Version                                       | Supported          |
|-----------------------------------------------|--------------------|
| Newest stable `v3.*` tag                      | :white_check_mark: |
| Older stable `v3.*` tags                      | :x:                |
| Pre-release tags (`-RC` / `-alpha` / `-beta`) | :x:                |
| `:latest` (tracks `main` HEAD)                | :x:                |
| v2.x (frozen, pre-cutover history)            | :x:                |

If you hit a security issue, pin to and upgrade to the **newest stable `v3.*`
tag** — that's where the fix will land.

## Reporting a Vulnerability

**Please do not open a public issue for security vulnerabilities.** Doing so
discloses the problem before a fix exists.

Instead, report privately via GitHub:

1. Go to the **Security** tab → **Report a vulnerability**.
2. This opens a private draft advisory visible only to the maintainers.

Please include a description, the affected version/commit (and whether you saw
it on a stable tag or `:latest`), reproduction steps, and impact. We'll
acknowledge the report, work the fix on `main`, and cut a stable tag that rolls
the fix forward.
