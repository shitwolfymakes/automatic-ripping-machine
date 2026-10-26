<script lang="ts">
	import type { MetadataCandidate } from '$lib/types/api.gen';
	import PosterImage from '$lib/components/PosterImage.svelte';
	import { formatYears, kindLabel } from '$lib/utils/match';

	interface Props {
		candidate: MetadataCandidate;
		selected: boolean;
		onselect: () => void;
	}

	let { candidate, selected, onselect }: Props = $props();

	let sub = $derived(
		[formatYears(candidate.year, candidate.facts?.end_year, candidate.kind), kindLabel(candidate.kind)]
			.filter(Boolean)
			.join(' · ')
	);
	let cast = $derived((candidate.facts?.cast ?? []).slice(0, 2).join(', '));
	let rating = $derived(candidate.facts?.rating ?? null);
</script>

<button type="button" class="match-row" aria-pressed={selected} onclick={onselect}>
	{#if candidate.poster_url}
		<PosterImage url={candidate.poster_url} alt="" class="match-row-thumb" />
	{:else}
		<span class="match-row-thumb match-row-thumb-empty" aria-hidden="true"></span>
	{/if}
	<span class="match-row-text">
		<span class="match-row-title">{candidate.title}</span>
		<span class="match-row-sub">{sub}</span>
		{#if cast}<span class="match-row-cast">{cast}</span>{/if}
	</span>
	{#if rating != null}<span class="match-row-rating">★ {rating.toFixed(1)}</span>{/if}
</button>

<style>
	.match-row {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 0.75rem;
		border: 1px solid transparent;
		border-radius: var(--radius-md);
		padding: 0.5rem;
		text-align: left;
		transition: border-color var(--motion-fast) var(--ease);
	}
	.match-row:hover {
		border-color: var(--color-border-strong);
	}
	.match-row[aria-pressed='true'] {
		border-color: var(--color-primary);
		background: var(--color-primary-tint-1);
	}
	/* :global: also passed as PosterImage's class prop, landing on its own <img> */
	:global(.match-row-thumb) {
		width: 2.25rem;
		height: 3.25rem;
		flex: none;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	.match-row-thumb-empty {
		background: var(--color-primary-tint-2);
	}
	.match-row-text {
		display: flex;
		min-width: 0;
		flex: 1;
		flex-direction: column;
	}
	.match-row-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.match-row-sub,
	.match-row-cast {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.match-row-cast {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.match-row-rating {
		flex: none;
		font-size: 0.8125rem;
		color: var(--color-text);
	}
</style>
