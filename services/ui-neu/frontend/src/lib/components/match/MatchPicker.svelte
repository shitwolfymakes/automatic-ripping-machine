<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import { untrack, type Snippet } from 'svelte';
	import type { MetadataCandidate } from '$lib/types/api.gen';
	import { candidateKey, mergeCandidate } from '$lib/match/match';
	import { MatchDetailsCache } from '../../stores/match-details.svelte';
	import MatchResultRow from './MatchResultRow.svelte';
	import MatchDetailPane from './MatchDetailPane.svelte';

	interface Props {
		results: MetadataCandidate[];
		query: string;
		year: string;
		providerLabel: string;
		canUse: boolean;
		useLabel: string;
		applying: boolean;
		onclose: () => void;
		onselect?: (c: MetadataCandidate, index: number) => void;
		onuse: (c: MetadataCandidate) => void;
		/** Rendered in the pane, given the selected row (details merged in). */
		children?: Snippet<[MetadataCandidate]>;
	}

	let { results, query, year, providerLabel, canUse, useLabel, applying, onclose, onselect, onuse, children }: Props =
		$props();

	let selectedIndex = $state(0);
	const cache = new MatchDetailsCache();

	let selectedRow = $derived(results[selectedIndex] ?? null);
	let selectedKey = $derived(selectedRow ? candidateKey(selectedRow) : null);
	let merged = $derived(selectedRow ? cache.merged(selectedRow) : null);

	// A new result list starts on its first row.
	$effect(() => {
		const list = results;
		untrack(() => {
			cache.reset();
			if (list.length) select(0);
		});
	});

	async function select(index: number) {
		const row = results[index];
		if (!row) return;
		selectedIndex = index;
		onselect?.(cache.merged(row), index);
		const found = await cache.load(row);
		// Report the details only if this row is still the one shown.
		if (found && selectedIndex === index && results[index] === row) onselect?.(mergeCandidate(row, found), index);
	}
</script>

<div class="match-picker">
	<div class="match-picker-head">
		<span class="match-picker-count">{results.length} {plural(results.length, 'RESULT', 'RESULTS')}</span>
		<span class="match-picker-query">"{query}"{year ? ` · ${year}` : ''} · {providerLabel}</span>
		<button type="button" class="match-picker-close" onclick={onclose}>Close</button>
	</div>
	<div class="match-picker-body">
		<div class="match-picker-list">
			{#each results as row, i (i)}
				<MatchResultRow candidate={row} selected={i === selectedIndex} onselect={() => select(i)} />
			{/each}
		</div>
		{#if merged && selectedKey}
			<div class="match-picker-pane">
				<MatchDetailPane
					candidate={merged}
					loading={!!cache.loading[selectedKey]}
					error={cache.errors[selectedKey] ?? null}
					{canUse}
					{useLabel}
					{applying}
					onuse={() => onuse(merged)}
				>
					{@render children?.(merged)}
				</MatchDetailPane>
			</div>
		{/if}
	</div>
</div>

<style>
	.match-picker {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}
	.match-picker-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
		border-bottom: 1px solid var(--color-border);
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
	}
	.match-picker-count {
		font-weight: 700;
		letter-spacing: 0.05em;
		color: var(--color-primary-text);
	}
	.match-picker-query {
		flex: 1;
		color: var(--color-text-muted);
	}
	.match-picker-close {
		color: var(--color-text-muted);
	}
	.match-picker-close:hover {
		color: var(--color-text);
	}
	.match-picker-body {
		display: grid;
		grid-template-columns: minmax(0, 45%) minmax(0, 1fr);
	}
	.match-picker-list {
		display: flex;
		max-height: 24rem;
		flex-direction: column;
		gap: 0.25rem;
		overflow-y: auto;
		border-right: 1px solid var(--color-border);
		padding: 0.5rem;
	}
	.match-picker-pane {
		padding: 0.75rem 1rem;
	}
	@media (max-width: 640px) {
		.match-picker-body {
			grid-template-columns: 1fr;
		}
		.match-picker-list {
			border-right: 0;
			border-bottom: 1px solid var(--color-border);
		}
	}
</style>
