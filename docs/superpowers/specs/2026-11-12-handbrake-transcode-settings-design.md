# HandBrake transcode settings: schema-driven tunables, validation and import

Design, 2026-11-12. Issue #601. Sibling #602 (AMD through HandBrake VCN) is out
of scope; section 4.11 says how this design leaves room for it. Status: awaiting
owner approval. Next step after approval: `superpowers:writing-plans`.

Revision 2 (2026-11-12): review round applied; decisions R1 to R7 in 3.2.
Where the mockups and this text disagree, this text wins (the mockups still
show a Hardware decode field, which R5 removes, and their settings counts are
illustrative).

UI mockups for sections 4.8 and 4.9 are on the design canvas "HandBrake
transcode settings (#601)" (a clickable prototype, which is the reference for
behaviour, and three static artboards: the Transcode presets page with the
preset sidebar on Video, on Audio and on the import review step). They are drawn on the current ui-neu
Settings > Sessions page (dark theme), from the owner's screenshots of it.
Canvas: https://claude.ai/code/artifact/82dcc34a-6ce9-4752-81cc-04a73f51de25
(private to the owner; the prototype artboard is `Prototype.dc.html`).

## 1. Problem

A v3 transcode preset can name a HandBrake built-in (`preset_ref`) and append
free-form `extra_args`. Everything else (quality, audio tracks and mixdown,
subtitle behaviour, filters, dimensions) has to be hand-written as CLI flags
that nothing validates. Users with tuned HandBrake GUI exports cannot bring
them in. The old ARM Transcoder took a whole export through
`--preset-import-file`; that path was removed and never reached v3.

What the code does today (checked on `main` at `f397c06`):

- `TranscodePreset` (`packages/arm_common/arm_common/models/transcode_preset.py`)
  holds `tool`, `preset_ref`, `encoder` (a catalog id), `container`,
  `extra_args` and `preset_json`. The router writes `preset_json` on create and
  patch; nothing reads it and `TranscodePresetForm.svelte` does not show it.
- The transcoder runs
  `HandBrakeCLI -i … -o … --preset <preset_ref> [--encoder X] [extra_args]`
  (`services/transcode/arm_transcode/handbrake.py::build_handbrake_command`).
  The resolved encoder arrives in `ARM_TRANSCODE_ENCODER`; the preset arrives in
  the `/register` response.
- `vaapi_*` encoders run a separate ffmpeg engine that ignores `preset_ref`.
- The transcode image builds HandBrake 1.11.1 from source in the
  `handbrake-builder` stage with `--enable-qsv --enable-nvenc --enable-vce`.

One thing the spikes turned up about today's behaviour, recorded here because
the design builds on it: when `--encoder` names a different encoder than the
preset's own `VideoEncoder`, HandBrakeCLI removes the preset's `VideoPreset`,
`VideoTune`, `VideoProfile`, `VideoLevel` and `VideoOptionExtra` and uses that
encoder's defaults (`test/test.c`, "If the user explicitly changes a video
encoder…"). The built-in `H.265 MKV 1080p30` is `x265_10bit` / `slow` /
`main10` in 1.11.1, so `tpr_builtin_plex_1080p_h265` on the CPU fallback
(`--encoder x265`) encodes 8-bit x265 at its default speed today. This design
does not change that for existing presets.

## 2. Goals, non-goals, anti-goals

**Goals**

- Every preset key the pinned HandBrake build supports is a first-class,
  validated setting. The list of keys, their types and defaults, and the
  per-encoder value lists come from the build, so a `HANDBRAKE_VERSION` bump
  updates them without anyone editing a list.
- A preset stores validated values, never the raw import.
- A HandBrake GUI export can be imported, reviewed and saved.
- ARM keeps choosing the hardware. Settings that depend on the encoder are
  stored per encoder and checked against the encoder a task is actually given.
- The transcode preset form presents every setting. A session only selects a
  transcode preset, as today.
- Existing presets and the built-ins behave exactly as they do today.

**Non-goals**

- AMD through HandBrake (#602). AMD stays on the ffmpeg VAAPI engine.
- Audio CD (`abcde`) presets.
- Translating a value from one encoder's scale to another's ("slow" on x265 to
  something on NVENC). Each encoder keeps its own values.
- Verifying 10-bit encode support per GPU in the device probe (see section 6).
- Fixing #600 (stale output-path preview). It is in the same component tree;
  section 4.9 says how this work avoids making it worse.

**Anti-goals**

- A hand-curated list of tunables that drifts from the binary.
- Storing an opaque raw JSON blob.
- ARM losing control of hardware selection (to an imported `VideoEncoder`, or
  to anything else in the stored settings).
- AMD presets that show HandBrake settings which then silently do nothing.

## 3. Decisions

### 3.1 Made by the owner before this design (fixed)

1. First-class support for every tunable of the pinned HandBrake version,
   taken from the build.
2. Configuration is validated against that schema.
3. The raw JSON is not stored; an import is parsed, validated and discarded.
4. The preset form and the session form both present every tunable.
5. The preset form has an import for a raw HandBrake GUI export.
6. ARM picks the hardware; `VideoEncoder` only sets the codec. The `encoder`
   catalog field stays the hardware policy.
7. Encoder-specific tunables are filtered by hardware; the dispatcher re-checks
   at claim time.
8. AMD stays on ffmpeg VAAPI for this issue; the schema already carries the
   `vce_*` lists.

### 3.2 Made by the owner during this design (2026-11-12)

| # | Question | Owner's call |
|---|---|---|
| O1 | Encoder-specific values under `any_*` | **Per-encoder blocks.** One block of values per encoder the preset could land on. A missing block means that encoder's defaults. No intersection, no translation. |
| O2 | Sparse or full; fate of `preset_ref` | **Base plus explicit keys.** `preset_ref` stays as an optional base (a HandBrake built-in, or none for HandBrake's template defaults). The preset stores only keys the user set or imported. Built-ins stay `preset_ref`-only. Inherited values may move on a HandBrake bump. |
| O3 | Session form | **A session only selects a transcode preset.** Sessions are separate from transcode settings: no per-session overrides and no settings editor in the session slide-over. This narrows decision 4: every tunable is presented on the transcode preset, and a session reaches them through the preset it selects. (An earlier answer in this design chose per-session overrides; the owner withdrew it on seeing the mockup.) |
| O4 | Saved values that a new schema rejects | **Flag and fail at dispatch.** Validity is computed against the current schema on read; the preset is marked and a task using it fails at claim with the reason. Nothing is rewritten. |
| O5 | How the Backend gets the schema | **Published by the transcoder.** The Backend runs the transcode image once (like `--probe-device`), stores what it prints and serves that. |
| O6 | Bit depth | **An ARM setting inside each encoder block** (8/10/12), limited to what the schema lists for that encoder. |
| O7 | `extra_args` | **Kept, unrestricted,** appended last. |
| O8 | Layout | **HandBrake's tabs,** with a filter box and a "Changed only" toggle above them. No per-field marker for stored versus inherited values; a stored field only gains a quiet Reset link. |
| O10 | Import | **Two steps, Import then Review.** The review shows data only (labelled values, counts, short notes), no explanatory prose. |
| O11 | Filter | **Searches every tab's contents;** while it has text, each tab shows its match count. |
| O9 | Where the settings live | **In a sidebar on the existing Sessions page, Transcode presets view.** The page's main panel keeps showing the list of presets or sessions. The transcode preset editor popup is retired: the whole preset (name, tool, container, encoder, base, extra args and the HandBrake tabs) is edited in one sidebar. The session slide-over stays as it is. |

Review round (2026-11-12), all accepted by the owner:

| # | Question | Owner's call |
|---|---|---|
| R1 | A claim-time check fails for the claimed family under `any_*` | **Reroute, don't fail.** The family's devices are excluded for this task, the claim tries the other candidates, then the CPU family; the task fails only when no reachable family is valid (4.4, 4.5). |
| R2 | Bit depth when a block sets none | **Inherit before defaulting.** Block `bit_depth`, else the base's `VideoEncoder` depth when it is the same family, else 8 (4.7). |
| R3 | An import fills one family's block only, so output differs by device | **Copy bit depth.** The import writes the export's bit depth into a block for every other reachable family that supports that depth; nothing else is copied, because presets and quality scales differ per encoder. A family without that depth gets no block and the review lists it (4.6). |
| R4 | AMD-only hosts | **Say so outside the form too.** When no verified non-AMD device can serve the codec, the preset's list row and the save step say the preset encodes on CPU on this host (4.5, 4.8). |
| R5 | Hardware decode (`VideoHWDecode`) | **ARM-owned, never stored.** This issue always materialises it off. Turning it on per claimed device is a follow-up that will likely need GPU settings work (a decode probe and a per-device switch in Settings > GPUs); see section 6. |
| R6 | Common keys whose meaning depends on the encoder | **Per encoder.** `VideoMultiPass`, `VideoTurboMultiPass` and `x264UseAdvancedOptions` move into the encoder blocks, and only families that use them may hold them (rule 11): multi-pass where the schema's `multipass` flag is set, turbo where `turbo` is set, advanced options on x264 only. `VideoQualityType` stays common; a claimed family that does not support it is invalid for that task (R1 reroutes) (4.3, 4.4). |
| R7 | Schema payload to the UI | **Slim view.** `GET /api/handbrake-schema` serves keys, families, lists and built-in names only; one built-in's values come from `GET /api/handbrake-schema/builtin/{name}`. The full dump stays server side (4.2). |

### 3.3 Made in this design (mine; overrule freely)

| # | Call | Why |
|---|---|---|
| M1 | Storage is one JSONB column, `handbrake_settings`, with two parts: `common` and `encoders`. | About 100 keys that change with each HandBrake release cannot be columns without a migration per bump. |
| M2 | Drop `preset_json` and add `handbrake_settings` in one new migration, rather than repurposing the old column. | The old column may hold unvalidated junk from API clients, and its name says "raw". |
| M3 | The resolved encoder and its block reach HandBrake as CLI flags after `--preset` (`--encoder`, `--encoder-preset`, …); everything else goes in the generated preset file. | It uses HandBrake's own rule for switching encoders (section 1), so "missing block means encoder defaults" needs no ARM-side default table. Verified in spike B. |
| M4 | A preset that carries HandBrake settings never lands on an AMD VAAPI device under `any_*`; the claim skips those devices as it already skips ones that cannot write the container. | Otherwise the settings would silently do nothing there (an anti-goal). Presets without settings keep today's behaviour. |
| M5 | The transcoder re-validates with the schema baked into its own image and is the final authority. The Backend's copy is for the API and the UI. | It makes image and Backend skew safe without coordinating versions. |
| M6 | `/register` refuses a preset with settings when the transcoder does not report a schema hash (an image older than this feature). | An old image would ignore the settings without saying so. |
| M7 | What libhb does not expose (tab grouping, labels, which list constrains which key, a dozen hard-coded enums, the QSV quality range) lives in one small overlay in `arm_common`. A key the overlay does not know still appears, validated by type, under "Other". | Keeps decision 1 true at runtime: a bump needs no edit for new keys to show up. |
| M8 | Import is a stateless parse endpoint that returns a proposed preset; saving goes through the normal create. | Nothing raw is ever stored, and import reuses the one validation path. |
| M9 | Import keeps every key present in the export as an explicit value. It does not drop values that equal HandBrake's defaults. | Someone importing a tuned export expects it to stay as exported across HandBrake bumps. |
| M11 | With no settings on the preset, the transcoder builds today's command unchanged. | Zero-risk path for every existing preset and built-in. |
| M12 | With no schema loaded yet, saving settings returns 503; presets without settings save as today; dispatch is not blocked. | The transcoder still validates, and the form shows the wait with a retry. |

## 4. Design

### 4.1 Spike results

Both spikes ran against HandBrake 1.11.1 built from the tag with the
Dockerfile's flags and the `nv-codec-headers` re-pin, on a machine with no GPU.
The spike code is not committed.

**Spike A: schema from libhb.** A 170-line C helper linked against
`libhandbrake.a` (same link line as `HandBrakeCLI`) printed everything below as
one JSON document using only public libhb API.

- **Keys, types, defaults:** `hb_presets_clean()` on a preset that holds only a
  `PresetName` returns it filled with every template key at its default: 103
  keys (47 strings, 28 booleans, 22 integers, 5 lists, 1 float), plus the
  11-key `AudioList` item. This matches `preset/preset_template.json` in the
  tree, without depending on that path. Preset format version: 72.0.0
  (`hb_presets_current_version`).
- **Video encoders with no hardware present:** `hb_video_encoder_get_next()`
  only lists encoders enabled on the machine, so it must not be used. Walking
  the codec id space through `hb_video_encoder_get_from_codec()` lists all 38,
  including every `nvenc_*`, `qsv_*` and `vce_*`, each with its preset, tune,
  profile and level lists and its bit depth.
- **Quality limits:** `hb_video_quality_get_limits()` is static for everything
  except QSV. x264/x265 8-bit 0 to 51 (RF, step 0.1); x264/x265 10-bit -12 to
  51; NVENC H.264/H.265 1 to 51 (CQ, step 0.1); NVENC AV1 1 to 63; SVT-AV1 0 to
  70 (step 0.25, not 0 to 63); VCE H.264/H.265 0 to 51; VCE AV1 0 to 255.
  **QSV returns nothing without an Intel adapter** (the function leaves its
  outputs untouched). In source the range is 51 at the top and 0 or 1 at the
  bottom depending on an ICQ capability bit, step 1.
- **Audio, filters, containers:** audio encoders (28) with their mixdowns,
  sample rates, quality and compression limits; mixdowns (11); bitrates;
  dithers; framerates (19); containers (`av_mp4`, `av_mov`, `av_mkv`,
  `av_webm`); filter presets and tunes for 12 filters; and all 106 built-in
  presets (`hb_presets_builtin_get`).
- **Multi-pass support per encoder:** the helper records a `multipass` flag per
  family from `hb_video_multipass_is_supported(encoder, 0)` (average bitrate)
  and a `turbo` flag for the families libhb applies turbo to (x264, x265). In
  1.11.1 only the CPU encoders run multi-pass, and only with average bitrate;
  no NVENC, QSV or VCE family does. Confirm both flags in the builder stage
  when the helper is written.
- **Size:** 39 KB without the built-in presets, 406 KB with them.
- **Not exposed by libhb:** the accepted strings of about a dozen behaviour
  keys are `strcasecmp` chains in `libhb/preset.c` (`VideoFramerateMode`,
  `AudioTrackSelectionBehavior`, `SubtitleTrackSelectionBehavior`,
  `SubtitleBurnBehavior`, `PicturePAR`, `PicturePadMode`, `VideoColorRange`,
  `VideoPasshtruHDRDynamicMetadata`, `AudioAutomaticNamingBehavior`, and the
  integer codes of `VideoQualityType` and `PictureCropMode`). Nor does libhb
  say which filter list constrains which key (`PictureDenoisePreset` depends on
  `PictureDenoiseFilter`), or which GUI tab a key belongs to.
- **Traps:** `hb_filter_get_tunes_short_name()` segfaults for a filter with no
  tunes (use `hb_filter_param_get_tunes()`); `hb_get_version()` returns a
  snapshot string (`20260322133136-4ce99a8`) in a shallow tag clone, not
  `1.11.1`; `hb_video_encoder_get_depth()` reports 8 for `vce_av1_10bit`.

**Spike B: end-to-end import** of `handbrake-export-custom-plex-720p.json`
(format version 72, the same as 1.11.1), on a 4-second 1080p clip with 5.1 AC-3.

| Run | Input | Result |
|---|---|---|
| 1 | Rebuilt one-preset file (`VideoEncoder: nvenc_h264`), `--encoder x264` after `--preset` | rc 0. Encoder is x264, 1280x720, AAC 5.1 at 384 kbps, RF 18. **Profile High, level 3.1, default speed:** the CLI dropped `slower` / `main` / `4.0` because the encoder changed. |
| 2 | Same file with `VideoEncoder: x264` written in, no `--encoder` | rc 0. x264 `slower`, Main, level 4.0, RF 18. |
| 3 | Run 2 with `VideoPreset: slowest` (an NVENC-only name) | **rc 3**, `x264 [error]: invalid preset 'slowest'`. HandBrake does not translate or fall back. |
| 4 | File as exported, no `--encoder`, no GPU | rc 3 at encoder init. |
| 5 | Sparse file: six keys, one of them unknown | rc 0. libhb fills every missing key from its template and drops the unknown key silently. |
| 6 | File says `nvenc_h264`; CLI `--encoder x264 --encoder-preset veryfast --encoder-profile main --encoder-level 4.0 -q 22` | rc 0. x264 `veryfast`, Main, 4.0, RF 22. |
| 7 | File says `nvenc_h264`; CLI `--encoder x265_10bit` only | rc 0. HEVC Main 10, encoder defaults. |

Parsing the fixture also showed: one key unknown to 1.11.1
(`VideoColorMatrixCode`; the template has `VideoColorMatrixCodeOverride`),
twelve template keys the export omits, and `VideoQualitySlider: 18` as an
integer where the template has a float. `VideoPreset: "slower"` is valid for
`nvenc_h264` and `x264`, invalid for `qsv_h264` and `vce_h264`.

What the spikes settle: `--encoder` after `--preset` does override
`VideoEncoder`, and it also clears the five encoder-specific keys (M3 builds on
this). Encoder-specific values are not translated and an invalid one is a hard
failure, so validating against the claimed encoder is required, not optional.
Sparse presets are native to libhb (O2).

### 4.2 The schema artifact

**Generation.** A helper source file, `services/transcode/schema/hb_schema_dump.c`,
is compiled and run in the `handbrake-builder` stage after the HandBrake build.
It prints the raw dump: `schema_format` (1), `handbrake_tag` (the
`HANDBRAKE_VERSION` build arg, because of the version trap above),
`preset_version`, `preset_template`, `video_encoders`, `audio_encoders`,
`mixdowns`, `audio_bitrates`, `audio_dithers`, `video_framerates`,
`containers`, `filters`, `builtin_presets`. It does not record which encoders
are available on the build machine. The build writes it to
`/usr/share/arm/handbrake-schema.json` and the runtime stage copies it next to
the binary, so the file and the binary cannot disagree. A failed or empty dump
fails the image build.

**Shape served to the Backend and UI.** `arm_common.handbrake_schema` loads the
raw dump plus the overlay (M7) into a `HandbrakeSchema` object:

- `keys`: for each template key, its type, default, tab, group, label, and
  where its allowed values come from (a static list, a schema list such as
  `mixdowns`, a filter's presets chosen by another key, or none).
- `encoder_families`: video encoders grouped by family (`x265`, `nvenc_h265`,
  `qsv_h265`, `vce_h265`, …), each with its bit depths; per (family, depth)
  the HandBrake encoder name, preset/tune/profile/level lists and quality
  limits. Family and depth come from the encoder name's `_NNbit` suffix first
  and the libhb depth second (the `vce_av1_10bit` trap).
- `builtin_presets`: name to full preset.
- `content_hash`: SHA-256 of the canonical raw dump. This identifies a schema.

**The overlay** (`arm_common/handbrake_schema/overlay.py`, data only) holds:
tab and group per key, with a prefix rule as the fallback (`Audio*` to Audio,
`Subtitle*` to Subtitles, `Video*` to Video, `Picture*` to Dimensions unless
listed under Filters, `Chapter*` to Chapters, the rest to Summary, so
`MetadataPassthru` lands on Summary); display labels; the value-source
binding per key; the static enums listed in 4.1; the QSV quality range (1 to
51, step 1) used when the dump has none; and the ARM-owned keys that are never
stored as settings (`PresetName`, `PresetDescription`, `Type`, `Default`,
`Folder`, `FolderOpen`, `ChildrenArray`, `PresetDisabled`, `VideoEncoder`,
`FileFormat`, `VideoHWDecode` (R5)). A key missing from the overlay is still a setting: it is
validated by type and shown under "Other" on its prefix tab. An overlay entry
for a key the dump no longer has is ignored. Loading logs both lists once.

**Distribution (O5).** The transcoder gains a mode,
`python -m arm_transcode.main --dump-schema`, which prints the baked file as
one JSON line and exits 0. A new Backend module, `handbrake_schema_runner`
(a sibling of `gpu_probe_runner`, using the same container spec helpers, no
GPU passed in), runs the base transcode image in that mode:

- at boot, after the dispatcher starts;
- on `POST /api/handbrake-schema/refresh` (writer auth);
- when a transcoder registers with a schema hash that differs from the stored
  one (the image changed since boot).

The result is stored in a new table, `handbrake_schemas` (`id`, `content_hash`
unique, `handbrake_tag`, `preset_version`, `image_ref`, `raw` JSONB,
`fetched_at`); the newest row is current. The Backend keeps the loaded
`HandbrakeSchema` in memory behind a small `SchemaStore`. Storing it means a
restart has a schema before the boot run finishes. It is served in two parts
(R7), both JWT auth with `ETag` = `content_hash`:

- `GET /api/handbrake-schema`: the slim view the UI needs (`keys`,
  `encoder_families`, the audio, filter and container lists, and the built-in
  preset names). About 40 KB.
- `GET /api/handbrake-schema/builtin/{name}`: one built-in's values, used by
  the sidebar when a base preset is chosen. 404 for an unknown name.

The full dump, built-ins included (about 406 KB), never leaves the Backend;
validation and `materialise` use it in process.

**Failure and absence.** A non-zero exit or output that is not the expected
JSON is reported the way a stale probe image is: "the transcode image may
predate `--dump-schema`: rebuild or pull it". With no docker client, or before
the first successful run, there is no schema: `GET` returns 503, saving
settings returns 503 (M12), and the form shows a wait state with a retry
button. Presets without settings are unaffected.

**Version skew.** The transcode image is the source of truth for its own
binary (M5). All image variants (`base`, `-intel`, `-amd`) are built from the
same builder stage, so one release has one schema. The cases:

| Backend | Transcoder image | What happens |
|---|---|---|
| has schema S1 | same S1 | Normal. |
| has S1 | newer S2 (pulled since boot) | Register reports S2; the Backend refreshes in the background. This task is validated by the transcoder against S2. |
| has S1 | stale remote-host image with S0 | The transcoder validates against S0 and fails the task with per-key reasons if S0 rejects a value. |
| new | image older than this feature | Register carries no schema hash; a preset with settings is refused with 409 (M6) and the task fails with "transcode image predates HandBrake settings; rebuild or pull it". A preset without settings runs as today. |
| old | new image | The register response has no settings; the transcoder takes today's path (M11). |

**Tier-1 fixture.** `packages/arm_common/tests/fixtures/handbrake-schema-1.11.1.json`
is a committed copy of the raw dump, test data only; production never reads it.
`devtools/regen-handbrake-schema-fixture.sh` rebuilds the `handbrake-builder`
stage and copies the file out. Tests load it through the same
`load_schema()` as production and hand it to `SchemaStore`.

### 4.3 Storage model and migration

One new Alembic revision (the next number after `0049`):

- `transcode_presets`: drop `preset_json`; add `handbrake_settings` JSONB,
  nullable.
- create `handbrake_schemas` as in 4.2. String columns are VARCHAR; there are
  no enums here and no `CREATE TYPE`.
- Downgrade re-adds `preset_json` (nullable, empty) and drops the new column
  and table; settings are lost on downgrade and the docstring says so.

`handbrake_settings` shape, for the fixture after import:

```json
{
  "common": {
    "PictureWidth": 1280, "PictureHeight": 720, "VideoFramerateMode": "cfr",
    "AudioList": [{"AudioEncoder": "av_aac", "AudioMixdown": "5point1", "AudioBitrate": 384}]
  },
  "encoders": {
    "nvenc_h264": {
      "bit_depth": 8, "VideoPreset": "slower", "VideoProfile": "main",
      "VideoLevel": "4.0", "VideoQualitySlider": 18
    },
    "x264": { "bit_depth": 8 },
    "qsv_h264": { "bit_depth": 8 }
  }
}
```

(The `x264` and `qsv_h264` blocks hold only the copied bit depth, R3. The
export's `VideoMultiPass`, `VideoTurboMultiPass` and `x264UseAdvancedOptions`
are not stored: NVENC uses none of them, rule 11.)

- `common` holds HandBrake keys by their own names. It may not hold an
  ARM-owned key, nor an encoder-specific one.
- `encoders` is keyed by encoder family. A block may hold `bit_depth` and the
  encoder-specific keys: `VideoPreset`, `VideoTune`, `VideoProfile`,
  `VideoLevel`, `VideoOptionExtra` (the five HandBrake itself treats as
  encoder-specific), `VideoQualitySlider` (its scale differs per encoder), and
  `VideoMultiPass`, `VideoTurboMultiPass`, `x264UseAdvancedOptions` (their
  meaning differs per encoder, R6). HandBrake does not clear these last four
  on an encoder switch, so `materialise` writes them from the claimed block
  (4.7).
- Only explicit values are stored (O2). An absent key is inherited: from the
  base built-in if `preset_ref` names one, otherwise from HandBrake's template.
- `preset_ref`, `encoder`, `container` and `extra_args` keep their columns and
  meanings. `container` is the truth for the file format; `FileFormat` is never
  stored.
- `encoder: preset` ("HandBrake preset's own encoder") stays valid only with a
  `preset_ref`; its single candidate family is the base's `VideoEncoder`.

Wire schemas (`arm_common/schemas/sessions.py`): `preset_json` is removed from
the view, create and update models. `handbrake_settings: HandbrakeSettings | None`
is added to all three (a typed model with `common` and `encoders`); the view
also gains `issues: list[SettingIssue]` (`key`, `encoder`, `code`, `message`),
computed on read (O4). On PATCH, `handbrake_settings` replaces the stored
value whole; an explicit `null` clears it. The update request still has no
`media_type`.

The `sessions` table, its schemas and `overrides_json` are not touched.

### 4.4 Validation

One pure module, `arm_common.handbrake_schema.validate`, used by the Backend
at save, read and claim, and by the transcoder before encoding. It returns a
list of `SettingIssue`; it does no I/O. Each rule is its own function.

Rules for `common`:

1. The key exists in the schema's template (`unknown_key`).
2. It is not ARM-owned and not encoder-specific (`not_allowed_here`).
3. The value's type matches the template's: booleans strictly; an integer is
   accepted where the template has a float; a list of objects (`AudioList`) is
   checked item by item against the template item (`wrong_type`).
4. If the key has a value source, the value is in it (`not_in_list`):
   static enums from the overlay; schema lists (`AudioEncoder`,
   `AudioEncoderFallback`, `AudioMixdown` within the track's encoder,
   `AudioSamplerate`, `AudioBitrate`, `VideoFramerate`, dither); filter presets
   and tunes for the filter in effect after layering onto the base.
5. Numbers with schema limits are inside them (`out_of_range`).

Rules for `encoders`:

6. The family is one the preset's `encoder` catalog id can resolve to
   (`encoder_not_reachable`). For `any_<codec>`: the CPU family and every
   HandBrake GPU family of that codec in the catalog. For a pinned or
   `cpu_*` id: that one family. Reachability is by catalog, not by what is
   probed on this host, so values can be set ahead of hardware.
7. `bit_depth` is one the family has (`not_in_list`).
8. `VideoPreset`, `VideoTune`, `VideoProfile`, `VideoLevel` are in the lists
   of that (family, depth) (`not_in_list`); `VideoQualitySlider` is within its
   limits and on its step (`out_of_range`). `VideoOptionExtra` is a free string.
9. A preset pinned to a `vaapi_*` encoder may not carry settings at all
   (`engine_ignores_settings`).
10. The effective `VideoQualityType` (common, base or template) is a rate
    control the family supports (`not_supported_by_encoder`, R6). At save this
    is an issue on the family's block; at claim it makes the family invalid
    for the task (R1).
11. `VideoMultiPass` only in a block whose family has the schema's
    `multipass` flag, `VideoTurboMultiPass` only where it has `turbo`, and
    `x264UseAdvancedOptions` only in the `x264` block
    (`not_supported_by_encoder`). Multi-pass still does nothing under constant
    quality; the form shows that as a hint, not an issue (4.8).

When each runs:

| When | Where | Against | On failure |
|---|---|---|---|
| Save (create, patch) | Backend routers | all reachable families | 422 with the issue list; 503 if no schema is loaded |
| Read | Backend, building the view | all reachable families, current schema | `issues` on the view; the UI marks the preset "Needs review" (O4) |
| Claim | Dispatcher, per candidate family before a device is claimed | each candidate family, effective settings (base, preset) | an invalid family is excluded for this task and the next candidate is tried, ending with the CPU family under `any_*` (R1); the task fails with the per-family issues only when none is valid; skipped if no schema is loaded |
| Encode | Transcoder, before launching HandBrake | the one resolved family, its own baked schema | the task fails with the same issue text (M5) |

A claimed encoder whose family has no block is valid: HandBrake's defaults for
that encoder apply (O1). At claim, an inherited `VideoQualitySlider` (from the
base or the template) that falls outside a candidate encoder's range makes
that family invalid for the task (R1); the save-time `issues` flag it so the
user can set a quality in that encoder's block. A rerouted task records which
families were skipped and why in its log.

For a pinned or `cpu_*` encoder there is one candidate, so an invalid family
fails the task as before. The transcoder's own check (M5) still fails the task
outright, because by then the device is claimed.

### 4.5 Hardware filtering

- The form shows one block per reachable family (rule 6). Families whose
  device the `gpus` table has probed and verified for the codec are open and
  labelled with the device; the CPU family is always open and labelled as the
  fallback under `any_*`; the rest are collapsed with "Set values anyway".
  Availability comes from the existing `GET /api/encoders`.
- Lists and ranges in a block come from that (family, depth) in the schema.
- Under `any_*` an AMD card states that AMD devices run ffmpeg, cannot apply
  these settings, and are skipped for a preset that has any (M4).
- The dispatcher re-checks at claim (4.4), because the GPU set can change
  after a preset is saved. `gpu_claim` gains two filters beside
  `vendor_supports_container`: a preset with HandBrake settings excludes
  devices whose encoder runs the `ffmpeg_vaapi` engine (M4), and devices of a
  family the claim-time check found invalid for this task (R1). Each filter is
  its own function.
- **AMD-only hosts (R4).** When a preset has settings and no verified non-AMD
  device can serve its codec, the view carries a host note
  (`host_notes: ["encodes_on_cpu_here"]`, computed on read from the `gpus`
  table). The list row shows "Encodes on CPU on this host" and the save step
  repeats it. This is a note, not an issue: it does not mark the preset
  "Needs review".

### 4.6 Import

`POST /api/transcode-presets/import/parse` (writer auth) takes the export as a
JSON body, at most 1 MB, and returns without storing anything (M8):

```
{ "handbrake_version": {"export": "72.0.0", "schema": "72.0.0"},
  "presets": [ { "path": ["My folder"], "name": "Custom_Plex_720p",
                 "proposal": { "name", "container", "encoder", "handbrake_settings" },
                 "dropped_keys": ["VideoColorMatrixCode"],
                 "warnings": [...], "issues": [...], "importable": true } ] }
```

Steps, each a separate function: parse; flatten; map; validate.

- **Accepted inputs:** a `{"PresetList": […], "VersionMajor": …}` export, or a
  single bare preset object (libhb accepts both).
- **Multi-preset list:** every non-folder preset is returned; the UI lets the
  user pick one. **Folders** (`Folder: true` with `ChildrenArray`) are walked
  recursively; a folder is never importable itself and its name becomes the
  `path` label. An empty result is a 422.
- **Version:** a `VersionMajor` different from the schema's adds a warning and
  never blocks. An older export may use key names libhb would have upgraded;
  the Backend has no libhb, so those keys land in `dropped_keys` and the
  warning says so.
- **Unknown keys** are dropped and listed (libhb drops them too).
  ARM-owned keys are consumed, not stored.
- **`FileFormat`** maps to `container` (`av_mkv`, `av_mp4`, `av_webm`).
  `av_mov` has no ARM container: the proposal uses `mkv` and warns.
- **`VideoEncoder`** is reduced to its codec; the proposal's `encoder` is
  `any_<codec>` (decision 6). Its family and bit depth decide where the
  encoder-specific values go: `nvenc_h264` fills
  `encoders.nvenc_h264` with `bit_depth: 8` and the encoder-specific keys the
  export carries.
- **Bit depth is copied (R3).** Every other family reachable from the proposed
  `any_<codec>` gets a block holding only `bit_depth`, set to the export's
  depth, when the family lists that depth; such a block carries no other key,
  so those encoders use their own defaults for preset, profile, level and
  quality until set. A family without that depth (for example a GPU family
  with no 10-bit encoder) gets no block, and the review lists it as
  "8-bit on this encoder". The import never copies preset, tune, profile,
  level or quality across families. An encoder with no ARM codec (VP9, MPEG-4, ProRes, …) or
  no HandBrake family in the catalog (VideoToolbox, Media Foundation) makes
  that preset `importable: false` with the reason. A `vce_*` encoder imports
  its codec and common settings; its block is dropped with a warning that
  points at #602.
- **Types:** an integer where the template has a float is accepted; any other
  mismatch is an issue on that key.
- **Values invalid for their encoder or list** come back as `issues`. The form
  opens with them marked; saving is refused (422) until they are fixed.
- Every key present in the export is kept as an explicit value (M9), except
  the encoder-dependent keys the export's family does not use (rule 11:
  multi-pass and turbo on a GPU family, advanced options off x264). The review
  lists them as "Not used by <encoder>, not imported".

### 4.7 Transcoder command construction

A pure function in `arm_common.handbrake_schema`,
`materialise(schema, preset_ref, settings, family, container)`, returns
the preset-file dictionary and the CLI flags. The transcoder calls it with its
baked schema; the dispatcher calls it at claim for validation only. Writing
the temp file is a separate function in `arm_transcode`.

1. If the preset has no settings: build today's command,
   unchanged (M11).
2. Start from the base: the built-in named by `preset_ref` (looked up in the
   schema's `builtin_presets`; an unknown name fails the task with "HandBrake
   1.11.1 has no built-in preset named …"), or an empty preset when there is no
   base. libhb fills missing keys from its template on import.
3. Layer `common` from the preset.
4. Set `PresetName` to `arm`, `Type` to 1, `FileFormat` from `container`,
   `VideoHWDecode` to 0 (R5), and from the claimed family's block, where it
   sets them: `VideoQualitySlider`, `VideoMultiPass`, `VideoTurboMultiPass`
   and `x264UseAdvancedOptions` (R6). Leave the base's `VideoEncoder` and its
   five encoder-specific keys as they are.
5. Write `{"PresetList": [<that>], "VersionMajor/Minor/Micro": <schema's>}` to
   a temp file in the task's work directory.
6. Build the flags from the resolved encoder: `--encoder <name>` where the
   name is the schema's encoder for (family, depth). The depth is resolved by
   its own function (R2): the block's `bit_depth`; else the base's
   `VideoEncoder` depth when that encoder is in the same family (a base of
   `H.265 MKV 1080p30`, `x265_10bit`, keeps 10-bit on the x265 family); else
   8. Then,
   only for keys the block sets, `--encoder-preset`, `--encoder-tune`,
   `--encoder-profile`, `--encoder-level`, `--encopts`. For `encoder: preset`
   there is no `--encoder`.

```
HandBrakeCLI -i <in> -o <out> --preset-import-file <tmp> --preset arm
             [--encoder nvenc_h264 --encoder-preset slower --encoder-profile main --encoder-level 4.0]
             [extra_args]
```

`extra_args` is still split and appended last, unchecked (O7), so a flag there
wins over everything above. The form says so next to the field.

Why flags and not writing the encoder into the file (M3): if the resolved
encoder differs from the base's, HandBrake clears the base's five keys and the
block's flags, or the encoder's defaults, take over (runs 1, 6, 7). If it is
the same, the base's values stay unless a flag overrides them. Writing the
encoder into the file instead would leave libhb to fill an unset `VideoPreset`
with the template's `medium`, which x264 accepts and SVT-AV1 does not.

The ffmpeg VAAPI engine and the `abcde` and passthrough paths are untouched.

### 4.8 UI: the settings sidebar on the Sessions page

The settings live on the current Settings > Sessions page (O9). Its main
panel keeps showing the list for the selected view (Sessions, Rip presets,
Transcode presets) exactly as today. `InlinePresetDialog`, the modal that
hosts `TranscodePresetForm` today, is retired for transcode presets. Edit,
View and "+ New transcode preset" on the Transcode presets list open one
**preset sidebar**: a slide-over like the session one (`slide-over` block),
640 px wide instead of 32rem, docked right. "+ Create new transcode
preset..." in the session slide-over's select opens the same sidebar in
place of today's dialog; the session slide-over is otherwise unchanged. Rip
presets keep their dialog. Mockups: artboards "Transcode presets page: preset sidebar (Video)"
and "(Audio)".

- **Header:** "Edit transcode preset" (or View / New), an "Import HandBrake
  preset" button and Close.
- **Preset block,** above the tabs and always visible: the fields
  `TranscodePresetForm` has today (Name, Media type, Tool, Container, Encoder,
  Extra args), with "Preset ref" becoming Base preset: a select of HandBrake's
  built-in names (from the slim schema) plus "None (HandBrake defaults)".
  Choosing a base fetches that built-in's values (R7) to show what the fields
  inherit.
- The tabs below the preset block appear only when the tool is HandBrake. For
  a pinned `vaapi_*` encoder they are replaced by a note that HandBrake
  settings do not apply and only container and extra args are used.
- **Tabs (O8):** Summary, Dimensions, Filters, Video, Audio, Subtitles,
  Chapters, as in HandBrake. Each tab shows a count of values set on this
  preset and a warning glyph when it has an issue.
- **Fields are rendered from the schema,** never listed in the UI: boolean to
  a checkbox, a key with a value source to a select, a number to a number input
  with the schema's limits, a string to a text input, a list of strings
  (languages, copy mask) to a chip picker, `AudioList` to a row editor (add,
  remove, reorder; per row: encoder, mixdown, sample rate, bitrate or quality,
  gain, DRC, with the mixdown and rate lists narrowed to the row's encoder).
  Fields sit in a two-column grid inside the sidebar.
- **Stored versus inherited is not called out** (O8). A field the preset
  stores a value for shows a small Reset link and a slightly stronger border;
  Reset removes the key so the field inherits again. There is no "set here",
  "default" or "from base" label.
- **Toolbar above the tabs,** separated from them by a rule: the filter box
  and "Changed only". The filter matches labels and HandBrake key names across
  all tabs, including the per-encoder fields and the audio output tracks
  (O11). While it has text, each tab shows its number of matches (0 included,
  dimmed), and the view moves to the first tab with a match if the current
  one has none. "Changed only" narrows to stored values and combines with the
  filter. With no filter text, a tab's count is the number of values stored
  there.
- **Video tab:** "All encoders" (common keys) first; then "Per encoder", one
  card per reachable family as in 4.5, each with bit depth, preset, tune,
  profile, level, quality (labelled with the encoder's scale name and range,
  such as "CQ, 1 to 51"), multi-pass and turbo where the family has them,
  advanced options on x264 only (R6, rule 11), and extra encoder options. With
  constant quality, the multi-pass field is disabled with the hint "Applies
  with average bitrate only", as in HandBrake.
  There is no Hardware decode field (R5); the mockup's is superseded.
- **Footer:** how many sessions use the preset, Cancel, Save preset. One save
  writes the preset block and `handbrake_settings` together. With the
  `encodes_on_cpu_here` host note (R4), the footer shows "Encodes on CPU on
  this host: no verified non-AMD GPU for this codec" above the buttons.
- **Issues** from the view's `issues` show under their field; the preset's
  row in the Transcode presets list shows a "Needs review" badge. The row's
  attribute line also gains the count of HandBrake settings, and "Encodes on
  CPU on this host" when the view carries that host note (R4).
- **Built-in presets** open the sidebar read-only; Clone makes an editable copy.
- **No schema loaded:** the sidebar body shows the shared `LoadState` with the
  server's message and a Retry that calls the refresh endpoint.
- Shared components, per the standard-UI-patterns rule: `PresetSidebar`,
  `TunableField` (which owns the Reset link), `SettingsTabs`,
  `EncoderBlockCard`, `AudioTrackList`, and a `handbrakeSchema` store. UI copy uses no em
  dashes or unicode symbols; icons are `Glyph`.

**Import (decision 5, O10).** Mockup: artboard "Transcode presets page:
preset sidebar (import, review step)", and the prototype. "Import HandBrake
preset" switches the sidebar to a two-step flow:

1. **Import.** Choose a file or paste the JSON; "Read file" calls the parse
   endpoint. A parse error or an export with no presets is shown here and the
   flow does not advance.
2. **Review.** Data only: the presets found (one is preselected; several are
   a pick list with folders as a path, unimportable ones disabled with the
   reason); the encoder mapping as labelled values (encoder in the file,
   codec and bit depth, encoder in ARM, container); the encoder-specific
   values and which encoder they are stored for; the encoders the bit depth
   was copied to and any that stay 8-bit (R3); counts of settings per tab;
   then one-line notes for dropped keys, a format-version mismatch, and any
   value the encoder rejects. Back returns to step 1.

"Use these settings" returns to the tabs with the values filled and sets
container and encoder in the preset block; nothing is saved until the user
saves the preset.

### 4.9 UI: sessions

Unchanged (O3). The session slide-over keeps its transcode preset select and
shows no HandBrake settings. A session card's transcode line can show the
preset's summary as it does today. #600 is not touched by this work.

### 4.10 Backward compatibility

- Every existing row has `handbrake_settings` NULL after the migration and
  runs today's command byte for byte (M11). The seeded `tpr_builtin_*` rows
  and `seeders.py` do not change.
- `preset_json` data is discarded. Nothing ever read it.
- `preset_json` leaves the OpenAPI schema; the snapshot and `api.gen.ts` are
  regenerated in the same PR.
- An `any_*` preset without settings can still land on an AMD device and run
  ffmpeg, as now. Only presets that gain settings skip AMD (M4).
- Old images and old Backends: see the skew table in 4.2.

### 4.11 Room for #602

- The schema already lists `vce_h264`, `vce_h265`, `vce_h265_10bit`, `vce_av1`
  and `vce_av1_10bit` with presets, profiles, levels and quality limits, from a
  machine with no AMD hardware.
- Encoder blocks are keyed by family, so adding `vce_*` entries to
  `arm_common.encoders` with the `handbrake` engine makes those blocks
  reachable with no storage or validation change.
- #602 removes the M4 claim filter, the R4 host note's AMD condition and the
  import warning for `vce_*` blocks.
- The family and depth derivation already handles the `vce_av1_10bit` depth
  quirk.

### 4.12 Tests

Tier 1 stays zero-infra: no HandBrake binary, no Docker. All of it runs on the
committed schema fixture and the `Custom_Plex_720p` export fixture.

- `arm_common`: schema loading (overlay merge, unknown and vanished keys,
  family and depth grouping, QSV fallback range); each validation rule, both
  outcomes; `materialise` for no base, a built-in base, an unknown base,
  resolved encoder equal to and different from the base's,
  a missing block, 10-bit, `VideoHWDecode` forced off, the per-encoder
  multi-pass keys; rule 11 for a GPU block with multi-pass and a non-x264
  block with advanced options, and the import dropping those keys; depth resolution (block, same-family base, default 8);
  rule 10; import parse, flatten and map for the fixture, a
  multi-preset list, nested folders, a bare preset, a version mismatch, an
  unmappable encoder, `vce_*`, `av_mov`, bit depth copied to families that
  have it and skipped for one that does not.
- Backend: router create and patch (422 issue lists, 503 with no schema, whole
  replacement, null clears); `issues` on read after swapping in a schema that
  rejects a stored value; the `encodes_on_cpu_here` host note (AMD-only, mixed,
  no GPUs); the slim schema view and the built-in endpoint (hit, 404, ETag);
  the import endpoint; the
  claim-time check (valid, one family invalid and rerouted to another GPU,
  rerouted to CPU, every family invalid, pinned encoder invalid, CPU fallback
  with no block, no schema loaded); the AMD claim filter; `handbrake_schema_runner`
  with a fake docker client (success, non-zero exit, bad output, no client);
  the register guard (M6) and the hash-triggered refresh; the migration up and
  down in the e2e harness.
- Transcoder: `--dump-schema`; command construction against the argv seen in
  spike runs 2, 6 and 7; the temp-file writer; validation failure before
  launch; the unchanged legacy command when there are no settings.
- ui-neu (Vitest): field rendering per type from a schema fixture; source
  Reset; Changed only and the cross-tab filter with match counts; encoder cards by
  availability; the AMD card; the CPU-on-this-host row text and footer note;
  base preset values fetched on choice; the audio row editor; the import
  dialog flow, including the copied-bit-depth lines; the no-schema state.
- Not tier 1: the acceptance encode of the fixture on CPU and on NVENC runs on
  the dev host (the method in the dev-host validation memory entry), and the
  builder-stage dump is exercised by the image build itself.

## 5. Constraints

- Single responsibility: I/O (docker run, temp file), parsing (import, schema
  load), decisions (validate, materialise, claim filter) and side effects are
  separate functions; each rule in 4.4 and each step in 4.6 and 4.7 is its own
  function. Cognitive complexity of 15 or less (S3776); the validators are
  lookup-driven, not branch-driven.
- 100% line and branch coverage of every touched symbol.
- OpenAPI: run `devtools/regen-openapi-snapshot.sh` and
  `services/ui-neu/scripts/codegen.sh`; commit both.
- uv workspace: schema, overlay, validation, import mapping and `materialise`
  live in `arm_common`; no new third-party dependency is expected.
- ui-neu gate: `npm run check`, `npx vitest run`, `lint`, `format:check`,
  `lint:styles`.
- No Postgres enums; a new Alembic revision; existing revisions untouched.
- The dev compose template is not branched for production. No new compose
  service: the schema run is a Backend-spawned container like the probe.

## 6. Left to the builder

- The exact link line for the helper in the builder stage (the spike reused
  the `HandBrakeCLI` link command from the build log).
- The accepted strings for the hard-coded enums in 4.1, read from
  `libhb/preset.c` at the pinned tag, and the label and tab for each key.
- Whether the QSV quality floor should later come from the device probe
  instead of the overlay.
- A 10-bit block on a GPU that cannot encode 10-bit fails at encode with
  HandBrake's error. Extending `--probe-device` to verify bit depth is a
  follow-up, not part of this issue.
- Which rate-control modes (`VideoQualityType`) each family supports, for rule
  10: from libhb if the helper can read it, otherwise an overlay table.
- **Hardware decode follow-up (R5), out of scope here.** Turning
  `VideoHWDecode` on from the claimed device will probably need GPU settings
  work first. Today `--probe-device` verifies encode codecs only, and Settings
  > GPUs has no decode control. A follow-up issue should scope a decode probe
  per device and codec, a per-device decode switch, and the dispatcher setting
  `VideoHWDecode` (or `--enable-hw-decoding`) from the claimed device. File it
  when this design is approved.

(Resolved during review: `57d2964ff^:src/transcoder.py` adds nothing beyond a
global `HANDBRAKE_PRESET_FILE` passed as `--preset-import-file` with
`--preset <name>`.)
- How the two panels behave on a narrow window (the mockups show a 1600 px
  window).

## 7. Definition of done

- [ ] The image build produces the schema and bakes it; `--dump-schema` prints it.
- [ ] The Backend fetches, stores and serves the schema, and survives its absence.
- [ ] Create and patch validate settings; read reports issues.
- [ ] The fixture imports, reviews, saves, and encodes on CPU and on NVENC.
- [ ] An imported `VideoEncoder` becomes a catalog id; hardware stays ARM's choice.
- [ ] The dispatcher checks each candidate encoder, reroutes past an invalid
      family under `any_*` (CPU fallback included), and fails only when none
      is valid; a preset with settings never lands on VAAPI.
- [ ] Bit depth follows the block, then a same-family base, then 8; an import
      copies its bit depth to every reachable family that supports it.
- [ ] AMD-only hosts show "Encodes on CPU on this host" on the row and at save.
- [ ] `VideoHWDecode` is never stored and is always off; the hardware decode
      follow-up issue is filed.
- [ ] The UI gets the slim schema; built-in values come from their own endpoint.
- [ ] Presets without settings, built-ins included, run the same command as before.
- [ ] The preset sidebar presents every setting from the schema. Sessions are unchanged.
- [ ] `preset_json` is gone; snapshot and TS types regenerated.
- [ ] Coverage, complexity and the ui-neu gate pass.

## 8. Self-review

Checked for placeholders, contradictions and scope: none left open except the
items in section 6. The one deliberate departure from the issue text is M3:
the issue says the transcoder "writes the resolved encoder into the preset it
builds"; this design passes it as `--encoder` after `--preset` instead, for
the reason given in 4.7. The `superpowers` skills named in the brief were not
installed in the session that wrote this, so the brainstorming flow and its
builder check were followed by hand. Revision 2 applied a review round (R1 to
R7); a fresh builder check should run on this revision before approval.
