---
name: Ripper runs unprivileged — read disc fingerprints device-side, never via mount
description: The ripper container drops root to the `arm` user via `gosu` (PUID drop), which clears effective capabilities — so `cap_add: SYS_ADMIN` does NOT let the service call `mount` (it gets EPERM "must be superuser"). Disc CRC64/fingerprints are read device-side via `pydvdid_m.DvdId`/PyCdlib with only cdrom-group read access, never by mounting. Don't add cap_add/privileged/AppArmor exceptions expecting the dropped service process to use them.
type: feedback
---

The ripper computes a DVD's pydvdid CRC64 by reading the disc/ISO **directly via `pydvdid_m.DvdId` (PyCdlib)** in [services/ripper/arm_ripper/scan/disc_probe.py](../../services/ripper/arm_ripper/scan/disc_probe.py) — it needs only `cdrom`-group read access on `/dev/sr0`, no mount and no `CAP_SYS_ADMIN`. **Do not re-introduce a mount-based probe**, and do not add `cap_add`, `privileged`, or AppArmor exceptions to the ripper expecting the *service process* to use them.

**Why:** disc-probe originally mounted the disc read-only to read `VIDEO_TS` for pydvdid. That never worked in the running service — three stacked blockers, peeled back one at a time:

1. Docker's `docker-default` AppArmor profile carries a blanket `deny mount,` rule → `mount(2)` returns **EACCES** (which the `mount` CLI mislabels "cannot mount read-only").
2. The shared entrypoint [services/_common/docker-entrypoint.sh](../../services/_common/docker-entrypoint.sh) ends with `exec tini -- gosu arm "$@"`. `gosu` drops root → the non-root `arm` user, which **clears the effective/permitted capability sets** (no ambient caps are configured), so even with `cap_add: SYS_ADMIN` the dropped process gets **EPERM** ("must be superuser to use mount"). `docker exec` runs as **root** and hides this — always reproduce capability/mount behaviour with `gosu arm …`.
3. The compute itself called `pydvdid.compute()` (the original-`pydvdid` top-level API); the pinned dep is the **`pydvdid-m` fork**, whose API is the `DvdId` class — so `getattr(pydvdid_m, "compute", None)` was always `None` and it silently returned `None`.

With no CRC64, the metadata dispatcher skipped its 1337server `lookup_by_crc64` fast path and fuzzy-matched titles on OMDb/TMDB for every disc. Fixed in commit `fd372371` by reading device-side and removing the mount entirely (MakeMKV's `CINFO:1` is already authoritative for `disc_type`, so the layout mount was redundant).

**How to apply:**

- Need to read disc *content/metadata*? Read the device/ISO directly (PyCdlib for ISO 9660; MakeMKV via the `dev:`/`iso:` source URL). Don't mount.
- Anything the ripper does that *seems* to need elevated privilege: first check whether it survives the `gosu arm` drop. The container runs unprivileged by design (ripper service in [docker-compose.yml](../../docker-compose.yml): no `cap_add`, no `security_opt`, just `group_add: ${CDROM_GID}`) — keep it that way.
- `pydvdid_m.DvdId(target)`: pass a **device/ISO path** (it opens via PyCdlib, no prompt). Do **not** pass a mounted VIDEO_TS folder — folder mode prompts interactively (raises `EOFError` here), and `allow_folder_id=True` makes `__init__` return early without a `.checksum`.
- **CRC64 wire format: plain 16-hex, NO pipe.** pydvdid-m's `CRC64.__str__` returns `"<high8>|<low8>"` (e.g. `79df7b12|8b27d001`), but 1337server is keyed on ARM v2's original-`pydvdid` form `format(crc, "016x")` (`79df7b128b27d001`) — the *same bytes*, no separator. [disc_probe.py](../../services/ripper/arm_ripper/scan/disc_probe.py) `_compute_crc` strips the pipe (`str(crc).replace("|", "")`) so the stored fingerprint *and* the lookup match the DB; [arm_server.py](../../services/backend/arm_backend/metadata/arm_server.py) `lookup_by_crc64` strips it again defensively. A piped value misses **every** disc on format alone (not just discs absent from the DB) — verified against a live deploy: Sintel's `79df7b12|8b27d001` returned HTTP 200 `no match`. Do **not** reintroduce the raw `str(crc)`. (Earlier memory wrongly claimed the piped form was wire-compatible — it is not.)

Related: the ripper's other hard-won invariant is [[Ripper uses one makemkvcon invocation per disc, not per title]] ([feedback_ripper_no_per_title.md](feedback_ripper_no_per_title.md)).
