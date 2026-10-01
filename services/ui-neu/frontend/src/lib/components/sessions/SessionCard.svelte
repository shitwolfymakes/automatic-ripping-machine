<script lang="ts">
	import { onMount } from 'svelte';
	import type { JoinedSession } from './sessionsData.svelte';
	import { resolveSample } from './sampleTokens';
	import { encodersStore, encoderLabel } from '$lib/stores/encoders.svelte';
	import RecipeStrip from './RecipeStrip.svelte';

	interface Props {
		session: JoinedSession;
		onedit: () => void;
		onclone: () => void;
		ondelete: () => void;
	}

	let { session, onedit, onclone, ondelete }: Props = $props();

	onMount(() => {
		encodersStore.load();
	});

	// Humanise enum values for display
	function humanizeTrackSelection(v: string | null | undefined): string {
		switch (v) {
			case 'main_feature':
				return 'Main feature';
			case 'all_tracks':
				return 'All tracks';
			case 'archive':
				return 'Archive';
			case 'custom':
				return 'Custom';
			default:
				return v ?? '-';
		}
	}

	function humanizeOutputMode(v: string | null | undefined): string {
		switch (v) {
			case 'tracks':
				return 'Tracks';
			case 'iso':
				return 'ISO image';
			case 'data_copy':
				return 'File copy';
			default:
				return v ?? '-';
		}
	}

	function humanizeMediaType(v: string | null | undefined): string {
		switch (v) {
			case 'movie':
				return 'Movie';
			case 'tv':
				return 'TV';
			case 'music':
				return 'Music';
			case 'data':
				return 'Data';
			case 'iso':
				return 'ISO';
			default:
				return v ?? '-';
		}
	}

	let ripSummary = $derived(
		session.ripPreset
			? `${humanizeTrackSelection(session.ripPreset.track_selection)} | ${humanizeOutputMode(session.ripPreset.output_mode)}`
			: '-'
	);

	// Only the parts the preset sets; a passthrough preset uses the tool's own
	// encoder, so it reads "iso", not "iso | - |".
	let transcodeSummary = $derived(
		session.transcodePreset
			? [session.transcodePreset.container, encoderLabel(session.transcodePreset.encoder)]
					.filter((v) => !!v)
					.join(' | ')
			: null
	);

	let samplePath = $derived(resolveSample(session.output_path_template, session.media_type));

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
			<button onclick={onedit} class="btn btn-sm session-card-edit-btn">{session.is_builtin ? 'View' : 'Edit'}</button>
			<button onclick={onclone} class="btn btn-sm">Clone</button>
			<button onclick={ondelete} disabled={session.is_builtin} class="btn btn-danger btn-sm">Delete</button>
		</div>
	</div>

	<!-- Recipe: rip > transcode > output (shared with the setup walkthrough) -->
	<div class="session-card-recipe">
		<RecipeStrip
			cells={[
				{ label: 'Rip preset', value: session.ripPreset?.name ?? session.rip_preset_id, sub: ripSummary },
				{
					label: 'Transcode',
					value: session.transcodePreset?.name ?? null,
					sub: transcodeSummary,
					empty: 'No transcode'
				},
				{ label: 'Output path', value: samplePath, mono: true }
			]}
		/>
	</div>
</div>

<style>
	/* original: rounded-lg border border-primary/20 bg-surface shadow-xs
	   px-4 py-3 - same surface-card shape as PresetRow.svelte's .preset-row;
	   panel-section's own background/padding are for a nested form box. */
	.session-card {
		background: var(--color-surface);
		box-shadow: var(--shadow-1);
		padding: 0.75rem 1rem;
	}
	.session-card-head {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		column-gap: 1rem;
		row-gap: 0.5rem;
	}
	/* original: rounded px-2 py-0.5 text-xs font-semibold uppercase
	   tracking-wide - badge-sm's own size/tracking/padding are tuned for
	   the BUILT-IN tag look, smaller than this media pill's metrics, so
	   both are restated here (see PresetRow.svelte's identical pill). */
	.session-card-pill {
		flex-shrink: 0;
		padding: 0.125rem 0.5rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 600;
		letter-spacing: 0.025em;
	}
	.session-card-pill[data-media='movie'] {
		background: var(--color-info-soft);
		color: var(--color-on-info-soft);
	}
	.session-card-pill[data-media='tv'] {
		background: color-mix(in srgb, var(--color-accent-3) 15%, transparent);
		color: var(--color-accent-3);
	}
	.session-card-pill[data-media='music'] {
		background: var(--color-success-soft);
		color: var(--color-on-success-soft);
	}
	/* original gray-100 is within a few RGB units of this card's own
	   surface background - visually no pill box, just bold text (see
	   PresetRow.svelte's identical pill). */
	.session-card-pill[data-media='data'] {
		background: transparent;
		color: var(--color-text-secondary);
	}
	/* dark WAS visible (gray-700 at 30% alpha) - the strict token set forbids
	   a literal wash even where no dedicated neutral-grey role exists, so
	   this collapses onto --color-backdrop (a fixed-black token, unlike
	   --color-text which is near-white in dark mode and would lighten
	   rather than darken the surface) scaled down via color-mix; recorded
	   as a deviation if it pushes a screen over threshold. */
	/* token collapse: scaled backdrop stands in for the literal grey wash */
	:global(.dark) .session-card-pill[data-media='data'] {
		background: color-mix(in srgb, var(--color-backdrop) 30%, transparent);
	}
	.session-card-pill[data-media='iso'] {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.session-card-name-wrap {
		display: flex;
		min-width: 0;
		flex: 1 1 0%;
		align-items: center;
		gap: 0.5rem;
	}
	.session-card-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-text);
	}
	/* original: bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 -
	   measurably more saturated than --color-warning-soft/--color-on-warning-soft
	   (baseline bg rgb(254,243,198) vs the token's rgb(255,251,235), baseline
	   text rgb(187,77,13) vs the token's rgb(146,64,14) - both ~40 units off in
	   sRGB distance, visible at this badge's small size). The strict token set
	   forbids literal colours in components regardless; the two warning tokens
	   are used and the visible gap is recorded as a deviation. */
	.session-card-builtin {
		flex-shrink: 0;
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 700;
		letter-spacing: 0.1em;
	}
	.session-card-actions {
		display: flex;
		flex-shrink: 0;
		align-items: center;
		gap: 0.375rem;
	}
	/* original buttons: px-3 py-1 text-xs - .btn-sm's min-height/inherited
	   line-height render taller than this size (Task 7 finding, see
	   PresetRow.svelte's identical action row). */
	.session-card-actions .btn {
		min-height: 0;
		padding: 0.25rem 0.75rem;
		line-height: 1rem;
	}
	.session-card-edit-btn {
		border-color: var(--color-border-strong);
		background: var(--color-primary-tint-2);
		color: var(--color-primary);
	}
	.session-card-edit-btn:hover {
		background: var(--color-primary-tint-3);
	}
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
	.session-card-recipe {
		margin-top: 0.75rem;
	}
</style>
