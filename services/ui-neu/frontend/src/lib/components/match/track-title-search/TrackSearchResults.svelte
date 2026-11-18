<script lang="ts">
	// The track title override's result cards.
	import type { MetadataCandidate } from '$lib/types/api.gen';
	import PosterImage from '../../shared/PosterImage.svelte';

	interface Props {
		/** The search's results; the first 8 are drawn. */
		results: MetadataCandidate[];
		/** A card was clicked. */
		onselect: (result: MetadataCandidate) => void;
	}

	let { results, onselect }: Props = $props();
</script>

<div class="flex flex-wrap items-stretch gap-1.5">
	{#each results.slice(0, 8) as result, i (i)}
		<button
			onclick={() => onselect(result)}
			class="flex min-w-0 flex-1 items-center gap-1.5 track-title-search-result"
			title="{result.title}{result.year ? ` (${result.year})` : ''}"
		>
			{#if result.poster_url}
				<PosterImage url={result.poster_url} class="h-10 w-7 shrink-0 track-title-search-result-poster" />
			{/if}
			<div class="min-w-0">
				<p class="truncate track-title-search-result-title">{result.title}</p>
				<p class="truncate track-title-search-result-year">{result.year ?? ''}</p>
			</div>
		</button>
	{/each}
</div>

<style>
	.track-title-search-result {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		padding: 0.25rem 0.375rem;
		text-align: left;
		transition: border-color var(--motion-fast) var(--ease);
	}
	.track-title-search-result:hover {
		border-color: var(--color-border-strong);
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.track-title-search-result-poster) {
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	.track-title-search-result-title {
		font-size: 10px;
		font-weight: 500;
		color: var(--color-text);
	}
	.track-title-search-result-year {
		font-size: 9px;
		color: var(--color-text-muted);
	}
</style>
