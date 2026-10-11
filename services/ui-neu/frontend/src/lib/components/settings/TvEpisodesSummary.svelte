<script module lang="ts">
	// Companion export so the empty-episode-sources note lives beside the
	// summary it explains, without RankedListField (generic) knowing anything
	// about TV episodes. SchemaConfigForm renders the returned sentence itself.
	export function tvEpisodesEmptyNote(values: Record<string, unknown>): string | null {
		const sources = values.episode_sources;
		if (!Array.isArray(sources) || sources.length > 0) return null;
		return 'With every source off, ARM does not match episodes automatically.';
	}
</script>

<script lang="ts">
	import Glyph from '$lib/components/Glyph.svelte';
	import type { ConfigFieldMeta } from '$lib/types/api.gen';

	let { values, fields }: { values: Record<string, unknown>; fields: ConfigFieldMeta[] } = $props();

	function fieldFor(key: string): ConfigFieldMeta | undefined {
		return fields.find((f) => f.key === key);
	}

	function labelsFor(key: string): string[] {
		const field = fieldFor(key);
		const value = values[key];
		if (!Array.isArray(value)) return [];
		return (value as string[]).map((v) => field?.enum_labels?.[v] ?? v);
	}

	const discHintLabels = $derived(labelsFor('disc_hint_sources'));
	const episodeSourceLabels = $derived(labelsFor('episode_sources'));
	const tolerance = $derived(values.episode_match_tolerance_seconds);
	const autoApply = $derived(Boolean(values.episode_auto_apply));

	const discHintsValue = $derived(discHintLabels.length > 0 ? discHintLabels.join(', ') : 'None');
	const episodeSourcesValue = $derived(episodeSourceLabels.length > 0 ? episodeSourceLabels.join(', ') : 'None');
	// M2: an emptied tolerance input sends `null` through - the sub-line then
	// drops the runtime clause entirely rather than rendering "null s".
	const toleranceClause = $derived(
		typeof tolerance === 'number' && Number.isFinite(tolerance) ? `, runtime within ${tolerance} s at most` : ''
	);
	const episodeSourcesSub = $derived(
		episodeSourceLabels.length > 0 ? `In order${toleranceClause}` : 'No automatic episode matching'
	);

	const matchesValue = $derived(
		episodeSourceLabels.length === 0
			? 'Nothing to match'
			: autoApply
				? 'Apply confident matches'
				: 'Suggest every match'
	);
	const matchesSub = $derived(
		episodeSourceLabels.length === 0
			? 'Tracks keep their disc titles'
			: autoApply
				? 'Others wait for review on the job page'
				: 'Nothing is applied until reviewed on the job page'
	);
</script>

<!-- Recipe strip metrics copied from SessionCard.svelte's .session-card-recipe
     (rip -> transcode -> output), with the blue tinted surface token in place
     of that recipe's grey backdrop wash - this strip is a summary, not an
     item card, so the design calls for the info/primary tint instead. -->
<div class="tv-episodes-summary-strip" role="group" aria-label="TV episodes summary">
	<div class="tv-episodes-summary-cell">
		<span class="tv-episodes-summary-label">Disc hints</span>
		<span class="tv-episodes-summary-value">{discHintsValue}</span>
		<span class="tv-episodes-summary-sub">Season and disc number</span>
	</div>
	<Glyph name="chevron-right" class="tv-episodes-summary-separator" />
	<div class="tv-episodes-summary-cell">
		<span class="tv-episodes-summary-label">Episode sources</span>
		<span class="tv-episodes-summary-value">{episodeSourcesValue}</span>
		<span class="tv-episodes-summary-sub">{episodeSourcesSub}</span>
	</div>
	<Glyph name="chevron-right" class="tv-episodes-summary-separator" />
	<div class="tv-episodes-summary-cell">
		<span class="tv-episodes-summary-label">Matches</span>
		<span class="tv-episodes-summary-value">{matchesValue}</span>
		<span class="tv-episodes-summary-sub">{matchesSub}</span>
	</div>
</div>

<style>
	/* original (SessionCard.svelte's .session-card-recipe): grid grid-cols-1
	   divide-y divide-primary/15 rounded-md border border-primary/15
	   bg-black/10 sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:divide-x sm:divide-y-0 -
	   same 3-cell-plus-separators shape, but the blue tint token
	   (--color-info-soft) replaces the grey backdrop wash per the design's
	   rationale (this strip is not a Sessions item card). */
	.tv-episodes-summary-strip {
		display: grid;
		grid-template-columns: 1fr;
		margin-bottom: 1rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-info-soft);
		font-size: 0.75rem;
		line-height: calc(1 / 0.75);
	}
	.tv-episodes-summary-strip > :not(:last-child) {
		border-bottom: 1px solid var(--color-border);
	}
	@media (min-width: 40rem) {
		.tv-episodes-summary-strip {
			grid-template-columns: 1fr auto 1fr auto 1fr;
		}
		.tv-episodes-summary-strip > :not(:last-child) {
			border-bottom: 0;
		}
	}
	.tv-episodes-summary-cell {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		padding: 0.75rem 1rem;
	}
	.tv-episodes-summary-label {
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.025em;
		color: var(--color-text-faint);
	}
	.tv-episodes-summary-value {
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.tv-episodes-summary-sub {
		color: var(--color-text-muted);
	}
	/* the separator: hidden below the 40rem breakpoint (the strip's own
	   border-bottom hairlines carry the division between stacked cells
	   instead), a centred currentColor chevron above it, replacing Sessions'
	   legacy ">" text per the design rationale. */
	/* :global: forwarded onto Glyph's internal svg, outside this component's own template (DriveCard.svelte precedent) */
	:global(.tv-episodes-summary-separator) {
		display: none;
		color: var(--color-text-faint);
	}
	@media (min-width: 40rem) {
		/* :global: forwarded onto Glyph's internal svg, outside this component's own template (DriveCard.svelte precedent) */
		:global(.tv-episodes-summary-separator) {
			display: flex;
			align-self: center;
			justify-self: center;
		}
	}
</style>
