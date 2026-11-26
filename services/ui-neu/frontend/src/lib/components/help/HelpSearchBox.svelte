<script lang="ts">
	import type { DocsSearchHit } from '$lib/help/api';

	interface Props {
		query: string;
		hits: DocsSearchHit[];
		onsearch: (value: string) => void;
	}

	let { query, hits, onsearch }: Props = $props();
</script>

<input
	type="search"
	class="field-control"
	placeholder="Search help"
	aria-label="Search help"
	autocomplete="off"
	value={query}
	oninput={(e) => onsearch(e.currentTarget.value)}
/>
{#if query.trim()}
	<div class="panel panel-compact help-results">
		{#each hits as hit (hit.id)}
			<a class="nav-item" href={hit.href}>{hit.title}</a>
		{:else}
			<p class="help-empty">No matches</p>
		{/each}
	</div>
{/if}

<style>
	.help-empty {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
