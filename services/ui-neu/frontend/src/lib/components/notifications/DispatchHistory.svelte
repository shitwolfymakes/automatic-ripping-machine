<script lang="ts">
	import type { DispatchRow } from '$lib/types/notifications';
	import Glyph from '$lib/components/Glyph.svelte';

	let { rows }: { rows: DispatchRow[] } = $props();
</script>

{#if rows.length === 0}
	<p class="dispatch-history-empty">No sends yet.</p>
{:else}
	<ul class="stack stack-sm dispatch-history-list">
		{#each rows as row (row.id)}
			<li class="dispatch-history-row" data-status={row.status}>
				<span class="dispatch-history-icon">
					{#if row.status === 'success'}
						<Glyph name="check" />
					{:else if row.status === 'failed'}
						<Glyph name="warning" />
					{:else}
						<Glyph name="clock" />
					{/if}
				</span>
				<span class="dispatch-history-key">{row.event_key}</span>
				<span class="dispatch-history-time">{row.created_at ?? ''}</span>
				{#if row.last_error}
					<span class="dispatch-history-error">| {row.last_error}</span>
				{/if}
			</li>
		{/each}
	</ul>
{/if}

<style>
	.dispatch-history-empty { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* Tailwind's space-y-1 (0.25rem) is tighter than .stack-sm (0.5rem). */
	.dispatch-history-list { gap: 0.25rem; }
	.dispatch-history-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
	.dispatch-history-icon { color: var(--color-text-faint); }
	.dispatch-history-row[data-status="success"] .dispatch-history-icon { color: var(--color-status-success); }
	.dispatch-history-row[data-status="failed"] .dispatch-history-icon { color: var(--color-status-error); }
	.dispatch-history-key { font-weight: 500; }
	.dispatch-history-time { color: var(--color-text-faint); }
	.dispatch-history-error { color: var(--color-status-error); }
</style>
