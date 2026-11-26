<script lang="ts">
	import { isAdmin } from '$lib/stores/auth';

	interface Props {
		unseenCount: number;
		clearedCount: number;
		purging: boolean;
		showCleared: boolean;
		onpurge: () => void;
		ondismissall: () => unknown;
	}

	let { unseenCount, clearedCount, purging, showCleared = $bindable(), onpurge, ondismissall }: Props = $props();
</script>

<div class="notifications-page-header">
	<div class="notifications-page-header-title">
		<h1 class="page-title">Notifications</h1>
		{#if unseenCount > 0}
			<span class="badge badge-warning notifications-page-unseen-badge">{unseenCount} new</span>
		{/if}
	</div>
	<div class="notifications-page-header-actions">
		<label class="field field-row notifications-page-show-cleared">
			<input type="checkbox" bind:checked={showCleared} class="notifications-page-show-cleared-checkbox" />
			Show dismissed
		</label>
		{#if clearedCount > 0 && $isAdmin}
			<button type="button" onclick={onpurge} disabled={purging} class="btn btn-danger notifications-page-purge-btn">
				{purging ? 'Purging...' : 'Purge Cleared'}
			</button>
		{/if}
		{#if unseenCount > 0 && $isAdmin}
			<button onclick={ondismissall} class="btn notifications-page-dismiss-all-btn"> Dismiss All </button>
		{/if}
	</div>
</div>

<style>
	/* no flex-wrap: the header overflows (not wraps) on narrow viewports - the right-hand controls
	   cluster runs off the edge rather than dropping to a new line. */
	.notifications-page-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}
	/* .cluster wraps by default; the two side-groups are non-wrapping flex items-center gap-3 rows (they overflow, not wrap,
	   on narrow viewports). */
	.notifications-page-header-title,
	.notifications-page-header-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	/* the badge has no whitespace-nowrap class (unlike .badge's own
	   default); at narrow widths, squeezed by the header's justify-between,
	   its "N new" text wraps to two lines rather than widening the pill. */
	.notifications-page-unseen-badge {
		border-radius: 9999px;
		padding: 0.125rem 0.625rem;
		white-space: normal;
	}
	.notifications-page-show-cleared {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	/* the checkbox is explicitly 16px (h-4 w-4); the browser's own
	   default checkbox box is a different size and shifts the row's
	   cross-axis alignment. */
	.notifications-page-show-cleared-checkbox {
		width: 1rem;
		height: 1rem;
		border-radius: var(--radius-sm);
	}
	/* these buttons use 0.375rem vertical padding with no min-height,
	   shorter than .btn's own 0.5rem-1rem padding + 2.25rem min-height. The
	   Purge button has no visible border (text-only red, unlike btn-danger's
	   own border). */
	.notifications-page-purge-btn {
		border: 0;
		border-radius: var(--radius-lg);
		min-height: auto;
		padding: 0.375rem 0.75rem;
	}
	.notifications-page-purge-btn:hover {
		background: var(--color-danger-soft);
	}
	/* this is a ring (ring-1 ring-primary/25), not a real border - a ring is a box-shadow and doesn't
	   add to the layout box the way .btn's own 1px border does (which would make this button, and
	   the row containing it, 2px taller and shift everything below down). */
	.notifications-page-dismiss-all-btn {
		border: 0;
		box-shadow: 0 0 0 1px var(--color-border-strong);
		border-radius: var(--radius-lg);
		min-height: auto;
		padding: 0.375rem 0.75rem;
		background: var(--color-primary-tint-1);
		color: var(--color-text-secondary);
	}
</style>
