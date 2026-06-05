---
name: ISO-source ripping must use ephemeral backend-spawned workers, not a long-running service
description: First-class "rip from an .iso file" in v3 is designed as ephemeral worker containers spawned per-ISO by the backend (the transcode-container lifecycle), NOT a persistent arm-ripper-iso service. Owner directive; eventual front door is UI file upload → spawn an ephemeral ripper per upload. Design lives at v3/docs/arch/10-iso-source-ripping.md.
type: project
---

"ISO ripping" in v3 is ambiguous and the two meanings point opposite ways: `rip_presets.output_mode = 'iso'` produces an ISO *as output* from a disc; **ISO-source ripping** (this entry) rips *from* an existing `.iso` *as input* through the normal scan→identify→rip pipeline. Always disambiguate.

The owner's architectural directive: **ISO-source rippers are ephemeral, spawned on demand like the GPU/transcode containers — never long-running.** Do not design or build a persistent `arm-ripper-iso` daemon, and do not orchestrate it via a hand-rolled `docker run` script or a `docker-compose.iso.yml` service. The correct template is the **transcode dispatcher** ([v3/services/backend/arm_backend/transcode_dispatcher.py](../../v3/services/backend/arm_backend/transcode_dispatcher.py)): a task table + dispatcher tick that `containers.run(..., auto_remove=True)`, a worker that claims its task and exits, a `MAX_PARALLEL_*` cap, and a stale-claim sweep (which becomes the crash-recovery story).

**Why:** My first design draft proposed a long-running logical `arm-ripper-iso` service (registers a persistent Drive, subscribes to a WS `iso.rip` command, idles between rips). The owner rejected that: it must be ephemeral/spawned like transcoders. The existing `ARM_MANUAL_TRIGGER_ISO` env-var path (ripper rips once then idles forever, [v3/services/ripper/arm_ripper/main.py](../../v3/services/ripper/arm_ripper/main.py)) is a test hook, not the feature — it's the opposite of ephemeral.

**How to apply:**
- Clone the transcode model: a `rip_tasks` table, a rip dispatcher, ephemeral `arm-ripper-iso-{task_suffix}` containers with `auto_remove=True` and a `{label: task_id}`, a `tasks/{id}/claim` CAS handshake (like `routers/transcoder.py`), and `MAX_PARALLEL_ISO_RIPS`. No `iso.rip` WS command — dispatcher-spawn replaces it; WS stays only for cancel (label force-stop).
- The pipeline downstream of scan is source-blind — reuse it verbatim. The only genuine new wrinkle is `Job.drive_id` is `nullable=False`, so an ISO job still needs a drive: recommended v1 = per-spawn ephemeral Drive row with a `kind` (`optical`|`iso`) discriminator; alternative = decouple (nullable drive_id + `Job.source`), bigger.
- Auth/cert: follow the transcoder (CA cert + `ARM_SERVICE_TOKEN`, no per-container leaf cert), not the physical ripper's mTLS leaf — an ephemeral worker can't hold a stable cert. Log identity should come from an explicit `ARM_SERVICE_NAME`, not `ARM_DRIVE_DEV`.
- v1 source = a server-side ISO **library directory** (host path `ARM_HOST_ISO_LIBRARY_PATH`, mounted into the spawned worker; backend validates the requested name with realpath containment under the library root — never accept an absolute client path). **Deferred (not today):** UI file upload writes the ISO into that library then enqueues the same task; the ephemeral-spawn core is unchanged.
- The Docker socket is already mounted into the backend for transcode spawns, so no new privilege is taken on.

Full design + open decisions: [v3/docs/arch/10-iso-source-ripping.md](../../v3/docs/arch/10-iso-source-ripping.md). Related: [[feedback_db_enums_as_varchar]] (any new enum like a Drive `kind` or `rip_tasks.status` is VARCHAR, validated in-app), [[feedback_ripper_no_per_title]] (the rip the ephemeral worker runs is still one makemkvcon per disc).
