<script lang="ts">
	import { onMount } from 'svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import NotificationCard from '$lib/components/inbox/NotificationCard.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { NotificationInbox } from '$lib/stores/notificationInbox.svelte';

	const inbox = new NotificationInbox();
	let showCleared = $state(false);
	let purgeConfirmOpen = $state(false);

	let filtered = $derived(showCleared ? inbox.rows : inbox.rows.filter((n) => !n.seen));

	function handlePurge() {
		purgeConfirmOpen = false;
		inbox.purge();
	}

	onMount(() => {
		inbox.load();
	});
</script>

<svelte:head>
	<title>ARM - Notifications</title>
</svelte:head>

<div class="stack notifications-page">
	{#if inbox.feedback}
		<div
			class="alert notifications-page-feedback {inbox.feedback.type === 'success' ? 'alert-success' : 'alert-danger'}"
		>
			{inbox.feedback.message}
			<button onclick={inbox.clearFeedback} class="notifications-page-feedback-close">&times;</button>
		</div>
	{/if}

	<div class="notifications-page-header">
		<div class="notifications-page-header-title">
			<h1 class="page-title">Notifications</h1>
			{#if inbox.unseenCount > 0}
				<span class="badge badge-warning notifications-page-unseen-badge">{inbox.unseenCount} new</span>
			{/if}
		</div>
		<div class="notifications-page-header-actions">
			<label class="field field-row notifications-page-show-cleared">
				<input type="checkbox" bind:checked={showCleared} class="notifications-page-show-cleared-checkbox" />
				Show dismissed
			</label>
			{#if inbox.clearedCount > 0 && $isAdmin}
				<button
					type="button"
					onclick={() => (purgeConfirmOpen = true)}
					disabled={inbox.purging}
					class="btn btn-danger notifications-page-purge-btn"
				>
					{inbox.purging ? 'Purging...' : 'Purge Cleared'}
				</button>
			{/if}
			{#if inbox.unseenCount > 0 && $isAdmin}
				<button onclick={inbox.dismissAll} class="btn notifications-page-dismiss-all-btn"> Dismiss All </button>
			{/if}
		</div>
	</div>

	<LoadState data={inbox.rows} loading={inbox.loading} error={inbox.error} isEmpty={() => false}>
		{#snippet loadingSlot()}
			<div class="stack stack-sm">
				{#each Array(4) as _, i (i)}
					<SkeletonCard lines={3} />
				{/each}
			</div>
		{/snippet}
		{#snippet ready(_items)}
			{#if filtered.length === 0}
				<div class="panel notifications-page-empty">
					<svg
						class="notifications-page-empty-icon"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
						stroke-width="1.5"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
						/>
					</svg>
					<p class="notifications-page-empty-text">
						{showCleared ? 'No notifications' : 'No new notifications'}
					</p>
				</div>
			{:else}
				<div class="stack stack-sm notifications-page-list">
					{#each filtered as notif (notif.id)}
						<NotificationCard {notif} dismissing={inbox.dismissing.has(notif.id)} ondismiss={inbox.dismiss} />
					{/each}
				</div>
			{/if}
		{/snippet}
	</LoadState>
</div>

<ConfirmDialog
	open={purgeConfirmOpen}
	title="Purge Notifications"
	message="Permanently delete all cleared notifications from the database? This cannot be undone."
	confirmLabel="Purge"
	variant="danger"
	onconfirm={handlePurge}
	oncancel={() => (purgeConfirmOpen = false)}
/>

<style>
	/* space-y-6 (1.5rem), the .stack default gap is already 1rem short. */
	.notifications-page {
		gap: 1.5rem;
	}
	/* alert's own border isn't in the original (a plain tinted strip, no
	   border), and its padding (0.5rem 0.75rem) is a hair short of this
	   banner's own px-4 py-2.5. */
	.notifications-page-feedback {
		border: 0;
		border-radius: var(--radius-lg);
		padding: 0.625rem 1rem;
	}
	.notifications-page-feedback-close {
		margin-left: 0.5rem;
		opacity: 0.6;
	}
	.notifications-page-feedback-close:hover {
		opacity: 1;
	}
	/* no flex-wrap: matches the original's own overflow (not wrap) behaviour
	   on narrow viewports - the right-hand controls cluster runs off the
	   edge rather than dropping to a new line. */
	.notifications-page-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}
	/* .cluster wraps by default; the original's two side-groups were
	   non-wrapping flex items-center gap-3 rows (they overflow, not wrap,
	   on narrow viewports). */
	.notifications-page-header-title,
	.notifications-page-header-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	/* the original badge had no whitespace-nowrap class (unlike .badge's own
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
	/* the original checkbox was explicitly h-4 w-4 (16px); the browser's own
	   default checkbox box is a different size and shifts the row's
	   cross-axis alignment. */
	.notifications-page-show-cleared-checkbox {
		width: 1rem;
		height: 1rem;
		border-radius: var(--radius-sm);
	}
	/* the originals were px-3 py-1.5 (0.375rem vertical) with no min-height,
	   shorter than .btn's own 0.5rem-1rem padding + 2.25rem min-height. The
	   Purge button had no visible border (text-only red, unlike btn-danger's
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
	/* the original was ring-1 ring-primary/25, not a real border - a ring is a
	   box-shadow and doesn't add to the layout box the way .btn's own 1px
	   border does (which made this button, and the row containing it, 2px
	   taller than the original and shifted everything below down). */
	.notifications-page-dismiss-all-btn {
		border: 0;
		box-shadow: 0 0 0 1px var(--color-border-strong);
		border-radius: var(--radius-lg);
		min-height: auto;
		padding: 0.375rem 0.75rem;
		background: var(--color-primary-tint-1);
		color: var(--color-text-secondary);
	}
	.notifications-page-empty {
		text-align: center;
		padding: 1.5rem;
	}
	.notifications-page-empty-icon {
		margin: 0 auto;
		width: 3rem;
		height: 3rem;
		color: var(--color-text-faint);
	}
	.notifications-page-empty-text {
		margin-top: 0.75rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text-muted);
	}
	/* space-y-3 (0.75rem), the original's per-card gap. */
	.notifications-page-list {
		gap: 0.75rem;
	}
</style>
