<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { MetadataCandidate } from '$lib/types/api.gen';
	import PosterImage from '$lib/components/PosterImage.svelte';
	import { formatVotes, formatYears, isSeriesKind, kindLabel, RATING_LABEL } from '$lib/utils/match';

	interface Props {
		candidate: MetadataCandidate;
		loading: boolean;
		error: string | null;
		canUse: boolean;
		useLabel: string;
		applying: boolean;
		onuse: () => void;
		children?: Snippet;
	}

	let { candidate, loading, error, canUse, useLabel, applying, onuse, children }: Props = $props();

	let facts = $derived(candidate.facts);
	let imdb = $derived(candidate.external_ids?.imdb ?? null);
	let episodes = $derived(facts?.episode_count ? `${facts.episode_count} episodes` : '');
	let sub = $derived(
		[formatYears(candidate.year, facts?.end_year, candidate.kind), kindLabel(candidate.kind), episodes]
			.filter(Boolean)
			.join(' · ')
	);
	let rows = $derived(
		[
			{ label: 'Genres', value: (facts?.genres ?? []).join(', ') },
			{ label: isSeriesKind(candidate.kind) ? 'Creator' : 'Director', value: (facts?.creators ?? []).join(', ') },
			{ label: 'Stars', value: (facts?.cast ?? []).join(', ') }
		].filter((r) => r.value)
	);
</script>

<div class="match-pane">
	{#if candidate.poster_url}
		<PosterImage url={candidate.poster_url} alt={candidate.title} class="match-pane-poster" />
	{/if}
	<div class="match-pane-body">
		<h4 class="match-pane-title">{candidate.title}</h4>
		<p class="match-pane-sub">{sub}</p>
		{#if facts?.rating != null || imdb}
			<div class="match-pane-rating">
				{#if facts?.rating != null}
					<span class={facts.rating_source === 'imdb' ? 'badge badge-imdb' : 'badge'}>
						{RATING_LABEL[facts.rating_source ?? ''] ?? 'Rating'}
					</span>
					<span>★ {facts.rating.toFixed(1)}</span>
					{#if facts.votes}<span class="match-pane-muted">{formatVotes(facts.votes)}</span>{/if}
				{/if}
				{#if imdb}<span class="match-pane-muted mono">{imdb}</span>{/if}
			</div>
		{/if}
		{#if facts?.overview}<p class="match-pane-overview">{facts.overview}</p>{/if}
		{#if rows.length}
			<dl class="match-pane-facts">
				{#each rows as row (row.label)}
					<dt>{row.label}</dt>
					<dd>{row.value}</dd>
				{/each}
			</dl>
		{/if}
		{#if loading}
			<div class="match-pane-skeleton" data-testid="match-pane-skeleton" aria-hidden="true">
				<span></span><span></span><span></span>
			</div>
		{/if}
		{#if error}<p class="field-help">{error}</p>{/if}
		<div class="match-pane-actions">
			{#if canUse}
				<button type="button" class="btn btn-primary" disabled={applying || loading} onclick={onuse}>
					{applying ? 'Applying...' : useLabel}
				</button>
			{/if}
			{#if imdb}
				<a class="btn" href="https://www.imdb.com/title/{imdb}/" target="_blank" rel="noopener noreferrer">
					Open on IMDb ↗
				</a>
			{/if}
		</div>
		{@render children?.()}
	</div>
</div>

<style>
	.match-pane {
		display: flex;
		gap: 1rem;
	}
	/* :global: also passed as PosterImage's class prop, landing on its own <img> */
	:global(.match-pane-poster) {
		width: 7rem;
		flex: none;
		align-self: flex-start;
		aspect-ratio: 2 / 3;
		border-radius: var(--radius-md);
		object-fit: cover;
	}
	.match-pane-body {
		display: flex;
		min-width: 0;
		flex: 1;
		flex-direction: column;
		gap: 0.5rem;
	}
	.match-pane-title {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.match-pane-sub,
	.match-pane-muted {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
	.match-pane-rating {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
	}
	.match-pane-overview {
		font-size: 0.875rem;
		color: var(--color-text);
	}
	.match-pane-facts {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.25rem 1rem;
		font-size: 0.8125rem;
	}
	.match-pane-facts dt {
		color: var(--color-text-muted);
	}
	.match-pane-skeleton {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}
	.match-pane-skeleton span {
		height: 0.625rem;
		border-radius: var(--radius-sm);
		background: var(--color-primary-tint-2);
	}
	.match-pane-skeleton span:nth-child(2) {
		width: 80%;
	}
	.match-pane-skeleton span:nth-child(3) {
		width: 60%;
	}
	.match-pane-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	@media (max-width: 640px) {
		.match-pane {
			flex-direction: column;
		}
	}
</style>
