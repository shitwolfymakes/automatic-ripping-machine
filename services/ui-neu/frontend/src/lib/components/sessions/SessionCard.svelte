<script lang="ts">
	import type { JoinedSession } from './sessionsData.svelte';
	import { resolveSample } from './sampleTokens';

	interface Props {
		session: JoinedSession;
		onedit: () => void;
		onclone: () => void;
		ondelete: () => void;
	}

	let { session, onedit, onclone, ondelete }: Props = $props();

	// Humanise enum values for display
	function humanizeTrackSelection(v: string | null | undefined): string {
		switch (v) {
			case 'main_feature': return 'Main feature';
			case 'all_tracks': return 'All tracks';
			case 'archive': return 'Archive';
			case 'custom': return 'Custom';
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

	let ripSummary = $derived(
		session.ripPreset
			? `${humanizeTrackSelection(session.ripPreset.track_selection)} | ${humanizeOutputMode(session.ripPreset.output_mode)}`
			: '-'
	);

	// Only the parts the preset sets; a passthrough preset has no codec or
	// hardware preference, so it reads "iso", not "iso | - |".
	let transcodeSummary = $derived(
		session.transcodePreset
			? [session.transcodePreset.container, session.transcodePreset.codec, session.transcodePreset.hw_preference]
					.filter((v) => !!v)
					.join(' | ')
			: null
	);

	let samplePath = $derived(
		resolveSample(session.output_path_template, session.media_type)
	);

	// Five media-type hues (movie/tv/music/data/iso) with no dedicated block:
	// mapped onto existing tone/accent tokens, same soft-bg + accent-fg
	// pairing as PosterImage.svelte's fallback tile (see PresetRow.svelte,
	// which shares this exact pill and colour mapping).
</script>

<div class="panel-section session-card">
	<div class="session-card-head">
		<!-- Media type pill -->
		<span class="badge badge-sm session-card-pill" data-media={session.media_type}>
			{humanizeMediaType(session.media_type)}
		</span>

		<!-- Name + BUILT-IN badge -->
		<div class="session-card-name-wrap">
			<span class="session-card-name">
				{session.name}
			</span>
			{#if session.is_builtin}
				<span
					class="badge badge-sm session-card-builtin"
					title="Built-in sessions cannot be deleted; clone to customise"
				>
					BUILT-IN
				</span>
			{/if}
		</div>

		<!-- Action buttons -->
		<div class="session-card-actions">
			<button
				onclick={onedit}
				class="btn btn-sm session-card-edit-btn"
			>{session.is_builtin ? 'View' : 'Edit'}</button>
			<button
				onclick={onclone}
				class="btn btn-sm"
			>Clone</button>
			<button
				onclick={ondelete}
				disabled={session.is_builtin}
				class="btn btn-danger btn-sm"
			>Delete</button>
		</div>
	</div>

	<!-- Recipe container: rip → transcode → output, each area divided -->
	<div class="session-card-recipe">
		<!-- Rip preset -->
		<div class="session-card-recipe-cell">
			<span class="session-card-recipe-label">Rip preset</span>
			<span class="session-card-recipe-value">
				{session.ripPreset?.name ?? session.rip_preset_id}
			</span>
			<span class="session-card-recipe-sub">{ripSummary}</span>
		</div>

		<!-- Arrow -->
		<div class="session-card-recipe-arrow" aria-hidden="true">&gt;</div>

		<!-- Transcode preset -->
		<div class="session-card-recipe-cell">
			<span class="session-card-recipe-label">Transcode</span>
			{#if session.transcodePreset}
				<span class="session-card-recipe-value">
					{session.transcodePreset.name}
				</span>
				<span class="session-card-recipe-sub">{transcodeSummary}</span>
			{:else}
				<span class="session-card-recipe-empty">No transcode</span>
			{/if}
		</div>

		<!-- Arrow -->
		<div class="session-card-recipe-arrow" aria-hidden="true">&gt;</div>

		<!-- Output path sample -->
		<div class="session-card-recipe-cell">
			<span class="session-card-recipe-label">Output path</span>
			<span class="mono session-card-recipe-path">{samplePath}</span>
		</div>
	</div>
</div>

<style>
	/* original: rounded-lg border border-primary/20 bg-surface shadow-xs
	   px-4 py-3 - same surface-card shape as PresetRow.svelte's .preset-row;
	   panel-section's own background/padding are for a nested form box. */
	.session-card { background: var(--color-surface); box-shadow: var(--shadow-1); padding: 0.75rem 1rem; }
	.session-card-head { display: flex; flex-wrap: wrap; align-items: flex-start; column-gap: 1rem; row-gap: 0.5rem; }
	/* original: rounded px-2 py-0.5 text-xs font-semibold uppercase
	   tracking-wide - badge-sm's own size/tracking/padding are tuned for
	   the BUILT-IN tag look, smaller than this media pill's metrics, so
	   both are restated here (see PresetRow.svelte's identical pill). */
	.session-card-pill { flex-shrink: 0; padding: 0.125rem 0.5rem; font-size: 0.75rem; line-height: 1rem; font-weight: 600; letter-spacing: 0.025em; }
	.session-card-pill[data-media="movie"] { background: var(--color-info-soft); color: var(--color-on-info-soft); }
	.session-card-pill[data-media="tv"] { background: color-mix(in srgb, var(--color-accent-3) 15%, transparent); color: var(--color-accent-3); }
	.session-card-pill[data-media="music"] { background: var(--color-success-soft); color: var(--color-on-success-soft); }
	/* original gray-100 is within a few RGB units of this card's own
	   surface background - visually no pill box, just bold text (see
	   PresetRow.svelte's identical pill). */
	.session-card-pill[data-media="data"] { background: transparent; color: var(--color-text-secondary); }
	/* dark WAS visible (gray-700 at 30% alpha) - the strict token set forbids
	   a literal wash even where no dedicated neutral-grey role exists, so
	   this collapses onto --color-backdrop (a fixed-black token, unlike
	   --color-text which is near-white in dark mode and would lighten
	   rather than darken the surface) scaled down via color-mix; recorded
	   as a deviation if it pushes a screen over threshold. */
	:global(.dark) .session-card-pill[data-media="data"] { background: color-mix(in srgb, var(--color-backdrop) 30%, transparent); } /* token collapse: scaled backdrop stands in for the literal grey wash */
	.session-card-pill[data-media="iso"] { background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
	.session-card-name-wrap { display: flex; min-width: 0; flex: 1 1 0%; align-items: center; gap: 0.5rem; }
	.session-card-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text); }
	/* original: bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 -
	   measurably more saturated than --color-warning-soft/--color-on-warning-soft
	   (baseline bg rgb(254,243,198) vs the token's rgb(255,251,235), baseline
	   text rgb(187,77,13) vs the token's rgb(146,64,14) - both ~40 units off in
	   sRGB distance, visible at this badge's small size). The strict token set
	   forbids literal colours in components regardless; the two warning tokens
	   are used and the visible gap is recorded as a deviation. */
	.session-card-builtin { flex-shrink: 0; background: var(--color-warning-soft); color: var(--color-on-warning-soft); padding: 0.125rem 0.375rem; font-size: 0.75rem; line-height: 1rem; font-weight: 700; letter-spacing: 0.1em; }
	.session-card-actions { display: flex; flex-shrink: 0; align-items: center; gap: 0.375rem; }
	/* original buttons: px-3 py-1 text-xs - .btn-sm's min-height/inherited
	   line-height render taller than this size (Task 7 finding, see
	   PresetRow.svelte's identical action row). */
	.session-card-actions .btn { min-height: 0; padding: 0.25rem 0.75rem; line-height: 1rem; }
	.session-card-edit-btn { border-color: var(--color-border-strong); background: var(--color-primary-tint-2); color: var(--color-primary); }
	.session-card-edit-btn:hover { background: var(--color-primary-tint-3); }
	/* original Clone: border-gray-300 text-gray-600 hover:bg-gray-50
	   dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800 - a
	   genuinely neutral outlined button. Per the migration reference (line
	   70), a neutral border has no token in spec 5.1 - bare `.btn` is the
	   only outlined option, using its default --color-border-strong/
	   --color-primary-text; the collapse is recorded in DEVIATIONS.md. */
	/* original: grid grid-cols-1 divide-y divide-primary/15 rounded-md
	   border border-primary/15 bg-black/10 sm:grid-cols-[1fr_auto_1fr_auto_1fr]
	   sm:divide-x sm:divide-y-0 - a 3-cell-plus-arrows recipe strip with no
	   equivalent block (table/list-row don't fit an arrow-separated grid). */
	/* text-xs's bundled line-height (1rem/16px) must be restated - a bare
	   font-size inherits the taller Tailwind Preflight body default (1.5)
	   instead, which stacks per line across three-line cells and drifts
	   every card below the first (Task 5 lesson). */
	/* original: bg-black/10 (light) / bg-black/20 (dark). No semantic token
	   covers a literal black-alpha wash and the strict token set forbids
	   raw rgb() regardless; --color-backdrop (a fixed-black token in both
	   themes) scaled down via color-mix is the nearest equivalent (a
	   slightly different composited value than Tailwind's own output -
	   recorded as a deviation if it pushes a screen over threshold). */
	.session-card-recipe { margin-top: 0.75rem; display: grid; grid-template-columns: 1fr; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: color-mix(in srgb, var(--color-backdrop) 20%, transparent); font-size: 0.75rem; line-height: 1rem; }
	:global(.dark) .session-card-recipe { background: color-mix(in srgb, var(--color-backdrop) 33%, transparent); } /* token collapse: scaled backdrop stands in for the dark literal black/20 wash */
	.session-card-recipe > :not(:last-child) { border-bottom: 1px solid var(--color-border); }
	@media (min-width: 640px) {
		.session-card-recipe { grid-template-columns: 1fr auto 1fr auto 1fr; }
		.session-card-recipe > :not(:last-child) { border-bottom: 0; }
		.session-card-recipe > :not(:first-child) { border-left: 1px solid var(--color-border); }
	}
	.session-card-recipe-cell { display: flex; flex-direction: column; gap: 0.125rem; padding: 0.75rem 1rem; }
	.session-card-recipe-label { font-weight: 500; text-transform: uppercase; letter-spacing: 0.025em; color: var(--color-text-faint); }
	.session-card-recipe-value { font-weight: 500; color: var(--color-text-secondary); }
	.session-card-recipe-sub { color: var(--color-text-muted); }
	.session-card-recipe-empty { font-style: italic; color: var(--color-text-faint); }
	/* original: break-all (word-break: break-all), not overflow-wrap's word-
	   preferring break-word - break-all allows a mid-word split at the exact
	   column edge, which is why the original wraps at a different point. */
	.session-card-recipe-path { word-break: break-all; color: var(--color-text-secondary); }
	.session-card-recipe-arrow { display: none; align-items: center; justify-content: center; padding: 0 0.25rem; font-size: 1.125rem; font-weight: 600; color: var(--color-text-faint); }
	@media (min-width: 640px) { .session-card-recipe-arrow { display: flex; } }
</style>
