<script lang="ts">
	// The Match episodes tab's status line: what the panel is doing, the
	// source on screen and its standing, and how many tracks are placed.
	// The panel's action buttons pass in as `actions`.
	import type { Snippet } from 'svelte';
	import type { PanelState } from '../../episodes/episode-model';

	interface Props {
		view: PanelState;
		/** The first load is still running. */
		loading: boolean;
		sourceLabel: string | null;
		/** The rows are shown, so the placed count is too. */
		showCount: boolean;
		placed: number;
		total: number;
		actions: Snippet;
	}
	let { view, loading, sourceLabel, showCount, placed, total, actions }: Props = $props();
</script>

<div class="episode-panel-status" role="status">
	<span class="eyebrow">Episodes</span>
	{#if view === 'matching'}
		<span class="episode-panel-text">Matching episodes...</span>
	{:else if loading}
		<span class="episode-panel-text">Loading episodes...</span>
	{:else}
		{#if sourceLabel}<span class="chip chip-sm chip-info">{sourceLabel}</span>{/if}
		{#if view === 'unsure'}
			<span class="chip chip-sm chip-warning">Guess</span>
		{:else if view === 'nomatch'}
			<span class="chip chip-sm">No match</span>
		{/if}
		{#if showCount}
			<span class="episode-panel-count">{placed} of {total} tracks placed</span>
		{/if}
	{/if}
	<span class="episode-panel-status-actions">
		{@render actions()}
	</span>
</div>

<style>
	.episode-panel-status {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.episode-panel-status-actions {
		display: flex;
		gap: 0.5rem;
		margin-left: auto;
	}
	.episode-panel-count,
	.episode-panel-text {
		font-size: 0.875rem;
		color: var(--color-text-secondary);
	}
</style>
