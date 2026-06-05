---
name: feedback_pin_actions_to_sha
description: GitHub Actions must be pinned to full commit SHAs, not tags or branches
metadata:
  type: feedback
---

Every `uses:` in `.github/workflows/` must reference a full 40-char commit SHA with a trailing `# vX.Y.Z` version comment — never a moving tag (`@v4`) or branch (`@main`).

**Why:** Per GitHub's security-hardening guidance, a mutable tag/branch ref can be silently repointed by the action owner (or an attacker who compromises the action repo) to malicious code that then runs with the workflow's permissions/secrets. A commit SHA is immutable, so the pinned code can't change under you.

**How to apply:** Resolve a ref to its commit SHA with `gh api repos/<owner>/<repo>/commits/<ref> --jq .sha`, then write `uses: owner/action@<sha> # <version>`. Find the precise version among tags at that SHA via `gh api "repos/<owner>/<repo>/tags?per_page=100"`. Dependabot's `github-actions` ecosystem (in `.github/dependabot.yml`, directory `/`) keeps both the SHA and the version comment bumped automatically. This applies to every new workflow or newly-added action, including `@main`-pinned third-party actions like `newrelic/wiki-sync-action`.
