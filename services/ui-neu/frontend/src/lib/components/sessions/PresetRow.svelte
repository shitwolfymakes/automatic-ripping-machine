<script lang="ts">
	import type { RipPresetView, TranscodePresetView } from '$lib/types/api.gen';

	type RipKind = { kind: 'rip'; preset: RipPresetView };
	type TranscodeKind = { kind: 'transcode'; preset: TranscodePresetView };

	interface Props {
		kind: 'rip' | 'transcode';
		preset: RipPresetView | TranscodePresetView;
		usedBy: number;
		onview: () => void;
		onedit: () => void;
		onclone: () => void;
		ondelete: () => void;
	}

	let { kind, preset, usedBy, onview, onedit, onclone, ondelete }: Props = $props();

	// ── Humanise helpers ─────────────────────────────────────────────────────

	function humanizeMediaType(v: string | null | undefined): string {
		switch (v) {
			case 'movie': return 'Movie';
			case 'tv': return 'TV';
			case 'music': return 'Music';
			case 'data': return 'Data';
			case 'iso': return 'ISO';
			default: return v ?? '-';
		}
	}

	function humanizeTrackSelection(v: string | null | undefined): string {
		switch (v) {
			case 'main_feature': return 'Main feature';
			case 'all_tracks': return 'All tracks';
			case 'archive': return 'Archive';
			case 'custom': return 'Custom';
			default: return v ?? '-';
		}
	}

	function humanizeIdentificationMode(v: string | null | undefined): string {
		switch (v) {
			case 'required': return 'ID required';
			case 'skip': return 'ID skip';
			case 'deferred_placeholder': return 'ID deferred';
			default: return v ?? '-';
		}
	}

	function humanizeOutputMode(v: string | null | undefined): string {
		switch (v) {
			case 'tracks': return 'Tracks';
			case 'iso': return 'ISO image';
			case 'data_copy': return 'File copy';
			default: return v ?? '-';
		}
	}

	function humanizeTool(v: string | null | undefined): string {
		switch (v) {
			case 'handbrake': return 'HandBrake';
			case 'abcde': return 'abcde';
			case 'none': return 'None';
			default: return v ?? '-';
		}
	}

	function humanizeContainer(v: string | null | undefined): string {
		switch (v) {
			case 'mkv': return 'MKV';
			case 'mp4': return 'MP4';
			case 'webm': return 'WebM';
			case 'flac': return 'FLAC';
			case 'mp3': return 'MP3';
			case 'ogg': return 'OGG';
			case 'iso': return 'ISO';
			case 'none': return 'None';
			default: return v ?? '-';
		}
	}

	function humanizeCodec(v: string | null | undefined): string {
		switch (v) {
			case 'h264': return 'H.264';
			case 'h265': return 'H.265';
			case 'av1': return 'AV1';
			default: return v ?? '-';
		}
	}

	function humanizeHw(v: string | null | undefined): string {
		switch (v) {
			case 'cpu_only': return 'CPU only';
			case 'any': return 'Any (HW)';
			default: return v ?? '';
		}
	}

	// ── Derived values ────────────────────────────────────────────────────────

	let summary = $derived(
		kind === 'rip'
			? (() => {
				const p = preset as RipPresetView;
				return `${humanizeTrackSelection(p.track_selection)} | ${humanizeIdentificationMode(p.identification_mode)} | ${humanizeOutputMode(p.output_mode)}`;
			})()
			: (() => {
				const p = preset as TranscodePresetView;
				return [humanizeTool(p.tool), humanizeContainer(p.container), p.codec ? humanizeCodec(p.codec) : '', humanizeHw(p.hw_preference)]
					.filter((v) => !!v)
					.join(' | ');
			})()
	);

	let deleteDisabled = $derived(preset.is_builtin || usedBy > 0);

	let deleteTitle = $derived(
		preset.is_builtin
			? 'Built-in preset: clone to edit or remove'
			: usedBy > 0
				? `Used by ${usedBy} session(s): repoint them first`
				: undefined
	);

	// ── Media pill ────────────────────────────────────────────────────────────
	// Five media-type hues (movie/tv/music/data/iso) with no dedicated block:
	// mapped onto existing tone/accent tokens rather than inventing new ones
	// (same soft-bg + accent-fg pairing PosterImage.svelte uses for its
	// fallback tile). data-media on the tag selects the pairing below.
</script>

<div class="panel-section preset-row">
	<div class="preset-row-head">
		<!-- Media type pill -->
		<span class="badge badge-sm preset-row-pill" data-media={preset.media_type}>
			{humanizeMediaType(preset.media_type)}
		</span>

		<!-- Name + BUILT-IN badge -->
		<div class="preset-row-name-wrap">
			<span class="preset-row-name">
				{preset.name}
			</span>
			{#if preset.is_builtin}
				<span
					class="badge badge-sm preset-row-builtin"
					title="Built-in presets cannot be deleted; clone to customise"
				>
					BUILT-IN
				</span>
			{/if}
		</div>

		<!-- Action buttons -->
		<div class="preset-row-actions">
			<!-- Built-ins are read-only: "View" opens a locked form; custom: "Edit" -->
			<button
				onclick={preset.is_builtin ? onview : onedit}
				class="btn btn-sm preset-row-edit-btn"
			>{preset.is_builtin ? 'View' : 'Edit'}</button>

			<button
				onclick={onclone}
				class="btn btn-sm"
			>Clone</button>

			<button
				onclick={ondelete}
				disabled={deleteDisabled}
				title={deleteTitle}
				class="btn btn-danger btn-sm"
			>Delete</button>
		</div>
	</div>

	<!-- ID + summary row -->
	<div class="preset-row-meta">
		<!-- ID -->
		<code class="mono preset-row-id">
			{preset.id}
		</code>

		<!-- One-line summary -->
		<span class="preset-row-summary">{summary}</span>

		<!-- Used by chip -->
		<span class="chip chip-sm preset-row-used-by">
			Used by {usedBy}
		</span>
	</div>
</div>

<style>
	/* original: rounded-lg border border-primary/20 bg-surface shadow-xs
	   px-4 py-3 - panel-section's background (primary-tint-1) and padding
	   (1rem all round) are for a nested form box, not this surface card. */
	.preset-row { background: var(--color-surface); box-shadow: var(--shadow-1); padding: 0.75rem 1rem; }
	.preset-row-head { display: flex; flex-wrap: wrap; align-items: flex-start; column-gap: 1rem; row-gap: 0.5rem; }
	/* original: rounded px-2 py-0.5 text-xs font-semibold uppercase
	   tracking-wide - badge-sm's own size (0.625rem)/tracking (0.06em)/
	   padding (0 0.375rem) are tuned for the BUILT-IN/RECOMMENDED tag look,
	   visibly smaller than this media pill's text-xs (0.75rem)/tracking-wide
	   (0.025em)/px-2 py-0.5, so both are restated here. */
	.preset-row-pill { flex-shrink: 0; padding: 0.125rem 0.5rem; font-size: 0.75rem; line-height: 1rem; font-weight: 600; letter-spacing: 0.025em; }
	/* soft-bg + accent/tone-fg pairing per media type, mirroring
	   PosterImage.svelte's --color-info-soft/--color-accent-2 fallback tile:
	   movie(blue)->info, tv(violet)->accent-3, music(green)->success,
	   iso(amber)->warning, data(gray)->neutral tint/secondary text. */
	.preset-row-pill[data-media="movie"] { background: var(--color-info-soft); color: var(--color-on-info-soft); }
	.preset-row-pill[data-media="tv"] { background: color-mix(in srgb, var(--color-accent-3) 15%, transparent); color: var(--color-accent-3); }
	.preset-row-pill[data-media="music"] { background: var(--color-success-soft); color: var(--color-on-success-soft); }
	/* original gray-100 (rgb 243,244,246) is within a few RGB units of this
	   card's own surface background (rgb 241,247,255) - visually no pill box
	   at all, just bold text; transparent reproduces that exactly instead of
	   introducing a visible box no available neutral token avoids. */
	.preset-row-pill[data-media="data"] { background: transparent; color: var(--color-text-secondary); }
	/* dark WAS visible (gray-700 at 30% alpha), unlike light - the strict
	   token set forbids a literal wash even where no dedicated neutral-grey
	   role exists, so this collapses onto --color-backdrop (a fixed-black
	   token, unlike --color-text which is near-white in dark mode and would
	   lighten rather than darken the surface) scaled down via color-mix
	   (see SessionCard.svelte's identical pill; recorded as a deviation if
	   it pushes a screen over threshold). */
	:global(.dark) .preset-row-pill[data-media="data"] { background: color-mix(in srgb, var(--color-backdrop) 30%, transparent); } /* token collapse: scaled backdrop stands in for the literal grey wash */
	.preset-row-pill[data-media="iso"] { background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
	.preset-row-name-wrap { display: flex; min-width: 0; flex: 1 1 0%; align-items: center; gap: 0.5rem; }
	.preset-row-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text); }
	/* original: text-xs font-bold tracking-widest bg-amber-100 text-amber-700 -
	   badge-sm's own weight (500) and tracking (0.06em) are lighter than this
	   tag's bold/tracking-widest (0.1em), so both are restated here.
	   The strict token set forbids the literal amber-100/700 values that
	   were here previously (measurably more saturated than
	   --color-warning-soft/--color-on-warning-soft); those two tokens are
	   used instead and any visible gap is recorded as a deviation. */
	.preset-row-builtin { flex-shrink: 0; background: var(--color-warning-soft); color: var(--color-on-warning-soft); padding: 0.125rem 0.375rem; font-size: 0.75rem; line-height: 1rem; font-weight: 700; letter-spacing: 0.1em; }
	.preset-row-actions { display: flex; flex-shrink: 0; align-items: center; gap: 0.375rem; }
	/* original buttons: px-3 py-1 text-xs (padding 0.75rem/0.25rem, line-height
	   1rem) - .btn-sm's own min-height (--control-h-sm, 1.75rem) and inherited
	   line-height (1.25rem from .btn) render taller than this original size
	   (Task 7 finding), so both are restated on all three action buttons. */
	.preset-row-actions .btn { min-height: 0; padding: 0.25rem 0.75rem; line-height: 1rem; }
	/* original Edit/View button: border-primary/30 bg-primary/10 text-primary -
	   a tinted-fill button, not .btn's bare outline. */
	.preset-row-edit-btn { border-color: var(--color-border-strong); background: var(--color-primary-tint-2); color: var(--color-primary); }
	.preset-row-edit-btn:hover { background: var(--color-primary-tint-3); }
	/* original Clone: border-gray-300 text-gray-600 hover:bg-gray-50
	   dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800 - a
	   genuinely neutral outlined button (see SessionCard.svelte's identical
	   button). Per the migration reference (line 70), a neutral border has no
	   token in spec 5.1 - bare `.btn` is the only outlined option, using its
	   default --color-border-strong/--color-primary-text; the collapse is
	   recorded in DEVIATIONS.md rather than approximated with a literal. */
	.preset-row-meta { margin-top: 0.5rem; display: flex; flex-wrap: wrap; align-items: center; column-gap: 1rem; row-gap: 0.25rem; font-size: 0.75rem; line-height: 1rem; }
	.preset-row-id { border-radius: var(--radius-sm); background: var(--color-primary-tint-2); padding: 0.125rem 0.375rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-secondary); }
	.preset-row-summary { color: var(--color-text-muted); }
	/* original: rounded-full border border-gray-300 px-2.5 py-0.5 text-xs
	   font-medium text-gray-600 - an outlined neutral pill, not chip's
	   tinted-fill look. */
	.preset-row-used-by { border: 1px solid var(--color-border-strong); border-radius: 9999px; background: transparent; padding: 0.125rem 0.625rem; color: var(--color-text-secondary); cursor: default; }
</style>
