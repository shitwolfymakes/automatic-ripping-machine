<script lang="ts">
	import type { Snippet } from 'svelte';

	// One status-dot row in System health's lists, with a name and a detail
	// the caller passes in.
	let {
		testid,
		status,
		label,
		children
	}: {
		testid: string;
		status: string;
		label: string;
		children: Snippet;
	} = $props();
</script>

<li class="list-row list-row-compact health-check-row" data-testid={testid} data-status={status}>
	<span class="status-dot" data-status={status}></span>
	<span class="health-check-row-label">{label}</span>
	<span class="health-check-row-detail">{@render children()}</span>
</li>

<style>
	/* list-row is a grid whose column template the owning list sets; these
	   rows are a simple inline label/status/detail line, not a data grid. */
	.health-check-row {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		cursor: default;
	}
	.health-check-row-label {
		width: 10rem;
		flex-shrink: 0;
		color: var(--color-text);
		font-size: 0.875rem;
	}
	/* the detail text inherits the list's own text-sm (0.875rem)
	   context, not panel-hint's smaller 0.75rem. */
	.health-check-row-detail {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
</style>
