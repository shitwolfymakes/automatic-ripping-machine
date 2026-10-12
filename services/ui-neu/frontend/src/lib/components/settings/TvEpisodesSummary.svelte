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
	import RecipeStrip, { type RecipeCell } from '$lib/components/sessions/RecipeStrip.svelte';
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

	const cells = $derived<RecipeCell[]>([
		{ label: 'Disc hints', value: discHintsValue, sub: 'Season and disc number' },
		{ label: 'Episode sources', value: episodeSourcesValue, sub: episodeSourcesSub },
		{ label: 'Matches', value: matchesValue, sub: matchesSub }
	]);
</script>

<div class="tv-episodes-summary" role="group" aria-label="TV episodes summary">
	<RecipeStrip tone="info" {cells} />
</div>

<style>
	.tv-episodes-summary {
		margin-bottom: 1rem;
	}
</style>
