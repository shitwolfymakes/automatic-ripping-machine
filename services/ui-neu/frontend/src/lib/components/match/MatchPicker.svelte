<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import type { MetadataCandidate } from '$lib/types/api.gen';
	import { fetchMatchDetails, type MatchProvider } from '$lib/api/jobs';
	import { candidateKey, detailsId, isSeriesKind, mergeCandidate } from '$lib/utils/match';
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
		children?: Snippet;
	}

	let { results, query, year, providerLabel, canUse, useLabel, applying, onclose, onselect, onuse, children }: Props =
		$props();

	let selectedIndex = $state(0);
	// Fetched details by candidate key; errors by key. Kept for the life of
	// this result list, so going back to a row costs no second call.
	let details = $state<Record<string, MetadataCandidate>>({});
	let errors = $state<Record<string, string>>({});
	let loading = $state<Record<string, boolean>>({});

	let selectedRow = $derived(results[selectedIndex] ?? null);
	let selectedKey = $derived(selectedRow ? candidateKey(selectedRow) : null);
	let merged = $derived(
		selectedRow && selectedKey && details[selectedKey] ? mergeCandidate(selectedRow, details[selectedKey]) : selectedRow
	);

	// A new result list starts on its first row.
	$effect(() => {
		const list = results;
		untrack(() => {
			details = {};
			errors = {};
			loading = {};
			if (list.length) select(0);
		});
	});

	async function select(index: number) {
		const row = results[index];
		if (!row) return;
		selectedIndex = index;
		const key = candidateKey(row);
		onselect?.(details[key] ? mergeCandidate(row, details[key]) : row, index);
		const id = detailsId(row);
		if (!row.provider || !id || details[key] || loading[key]) return;
		loading = { ...loading, [key]: true };
		const { [key]: _drop, ...rest } = errors;
		errors = rest;
		try {
			const resp = await fetchMatchDetails(row.provider as MatchProvider, isSeriesKind(row.kind) ? 'tv' : 'movie', id);
			const found = resp.candidates[0];
			if (found) {
				details = { ...details, [key]: found };
				// Report the details only if this row is still the one shown.
				if (selectedIndex === index && results[index] === row) onselect?.(mergeCandidate(row, found), index);
			} else {
				errors = { ...errors, [key]: resp.detail ?? 'No details found.' };
			}
		} catch (e) {
			errors = { ...errors, [key]: e instanceof Error ? e.message : 'Could not load details' };
		} finally {
			loading = { ...loading, [key]: false };
		}
	}
</script>

<div class="match-picker">
	<div class="match-picker-head">
		<span class="match-picker-count">{results.length} {results.length === 1 ? 'RESULT' : 'RESULTS'}</span>
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
					loading={!!loading[selectedKey]}
					error={errors[selectedKey] ?? null}
					{canUse}
					{useLabel}
					{applying}
					onuse={() => onuse(merged)}
				>
					{@render children?.()}
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
