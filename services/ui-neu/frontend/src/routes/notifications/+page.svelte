<script lang="ts">
	import { onMount } from 'svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import InboxHeader from '$lib/components/inbox/InboxHeader.svelte';
	import NotificationCard from '$lib/components/inbox/NotificationCard.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
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

	<InboxHeader
		unseenCount={inbox.unseenCount}
		clearedCount={inbox.clearedCount}
		purging={inbox.purging}
		bind:showCleared
		onpurge={() => (purgeConfirmOpen = true)}
		ondismissall={inbox.dismissAll}
	/>

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
