<script lang="ts">
	// The log terminal's search box, with its match count, clear button and
	// match-case toggle.
	import { matchLabel } from '$lib/logs/view';
	import CloseButton from '$lib/components/shared/CloseButton.svelte';

	interface Props {
		/** The query; '' filters nothing. */
		text: string;
		/** The query matches case exactly. */
		matchCase: boolean;
		/** How many lines the filters show, drawn while there is a query. */
		matches: number;
	}

	let { text = $bindable(), matchCase = $bindable(), matches }: Props = $props();
	let inputEl = $state<HTMLInputElement | null>(null);

	/** Moves focus into the query, for the "/" key. */
	export function focus(): void {
		inputEl?.focus();
	}

	function clearSearch(): void {
		text = '';
		inputEl?.focus();
	}
</script>

<div class="log-view-search">
	<span class="log-view-search-prompt" aria-hidden="true">/</span>
	<input
		type="text"
		bind:value={text}
		bind:this={inputEl}
		placeholder="Filter lines"
		aria-label="Filter lines"
		data-testid="job-log-search"
	/>
	{#if text}
		<span class="log-view-search-count" data-testid="job-log-search-count">{matchLabel(matches)}</span>
		<CloseButton label="Clear filter" class="log-view-search-clear" onclick={clearSearch} />
	{/if}
	<button
		type="button"
		class="log-view-search-case"
		aria-pressed={matchCase}
		aria-label="Match case"
		title="Match case"
		data-testid="job-log-search-case"
		onclick={() => {
			matchCase = !matchCase;
		}}>Aa</button
	>
</div>

<style>
	/* search: a composite field that grows into the leftover toolbar space */
	.log-view-search {
		flex: 1 1 140px;
		min-width: 120px;
		height: 28px;
		box-sizing: border-box;
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 0 6px 0 9px;
		border-radius: var(--radius-sm);
		border: 1px solid color-mix(in srgb, var(--color-terminal-ink) 10%, transparent);
		background: color-mix(in srgb, var(--color-terminal-ink) 4%, transparent);
	}
	.log-view-search:focus-within {
		border-color: color-mix(in srgb, var(--color-primary) 50%, transparent);
	}
	.log-view-search-prompt {
		font: 0.75rem var(--font-mono);
		color: color-mix(in srgb, var(--color-terminal-ink) 45%, transparent);
	}
	.log-view-search input {
		flex: 1;
		min-width: 0;
		border: 0;
		background: transparent;
		outline: none;
		padding: 0;
		font: 0.75rem var(--font-mono);
		color: var(--color-terminal-ink);
	}
	.log-view-search input::placeholder {
		color: color-mix(in srgb, var(--color-terminal-ink) 40%, transparent);
	}
	.log-view-search-count {
		font: 0.6875rem var(--font-mono);
		color: color-mix(in srgb, var(--color-terminal-ink) 50%, transparent);
		white-space: nowrap;
	}
	/* the shared CloseButton, shrunk to sit inside the 28px field */
	.log-view-search :global(.log-view-search-clear) {
		min-height: auto;
		height: auto;
		width: auto;
		padding: 2px 3px;
		border: 0;
		background: none;
		font-size: 13px;
		color: color-mix(in srgb, var(--color-terminal-ink) 60%, transparent);
	}
	.log-view-search-case {
		font: 600 0.6875rem var(--font-mono);
		padding: 2px 5px;
		border-radius: 3px;
		color: color-mix(in srgb, var(--color-terminal-ink) 75%, transparent);
	}
	.log-view-search-case[aria-pressed='true'] {
		background: color-mix(in srgb, var(--color-primary) 32%, transparent);
	}
</style>
