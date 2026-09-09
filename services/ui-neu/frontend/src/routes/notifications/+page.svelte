<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchNotifications, dismissNotification } from '$lib/api/notifications';
	import { purgeNotifications } from '$lib/api/maintenance';
	import type { NotificationInboxView } from '$lib/types/api.gen';
	import { formatDateTime, timeAgo } from '$lib/utils/format';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { isAdmin } from '$lib/stores/auth';

	let notifications = $state<NotificationInboxView[]>([]);
	let notifsLoading = $state(true);
	let notifsError = $state<Error | null>(null);
	let dismissing = $state<Set<string>>(new Set());
	let showCleared = $state(false);
	let purging = $state(false);
	let purgeConfirmOpen = $state(false);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	let filtered = $derived(
		showCleared ? notifications : notifications.filter((n) => !n.seen)
	);

	async function load() {
		notifsLoading = true;
		notifsError = null;
		try {
			notifications = await fetchNotifications();
		} catch (e) {
			notifsError = e instanceof Error ? e : new Error('Failed to load notifications');
		} finally {
			notifsLoading = false;
		}
	}

	async function dismiss(id: string) {
		dismissing = new Set([...dismissing, id]);
		try {
			await dismissNotification(id);
			notifications = notifications.map((n) =>
				n.id === id ? { ...n, seen: true } : n
			);
		} catch {
			// next refresh will reconcile
		} finally {
			const next = new Set(dismissing);
			next.delete(id);
			dismissing = next;
		}
	}

	async function dismissAll() {
		const unseen = notifications.filter((n) => !n.seen);
		if (unseen.length === 0) return;
		const ids = unseen.map((n) => n.id);
		dismissing = new Set(ids);
		await Promise.allSettled(ids.map((id) => dismissNotification(id)));
		notifications = notifications.map((n) => ({ ...n, seen: true }));
		dismissing = new Set();
	}

	let unseenCount = $derived(notifications.filter((n) => !n.seen).length);
	let clearedCount = $derived(notifications.filter((n) => n.seen).length);

	async function handlePurge() {
		purging = true;
		purgeConfirmOpen = false;
		try {
			const result = await purgeNotifications();
			feedback = { type: 'success', message: `Purged ${result.count} cleared notification${result.count !== 1 ? 's' : ''}` };
			await load();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Purge failed' };
		}
		purging = false;
	}

	onMount(() => {
		load();
	});
</script>

<svelte:head>
	<title>ARM - Notifications</title>
</svelte:head>

<div class="stack notifications-page">
	{#if feedback}
		<div class="alert notifications-page-feedback {feedback.type === 'success' ? 'alert-success' : 'alert-danger'}">
			{feedback.message}
			<button onclick={() => { feedback = null; }} class="notifications-page-feedback-close">&times;</button>
		</div>
	{/if}

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
				<button
					type="button"
					onclick={() => (purgeConfirmOpen = true)}
					disabled={purging}
					class="btn btn-danger notifications-page-purge-btn"
				>
					{purging ? 'Purging...' : 'Purge Cleared'}
				</button>
			{/if}
			{#if unseenCount > 0 && $isAdmin}
				<button
					onclick={dismissAll}
					class="btn notifications-page-dismiss-all-btn"
				>
					Dismiss All
				</button>
			{/if}
		</div>
	</div>

	<LoadState
		data={notifications}
		loading={notifsLoading}
		error={notifsError}
		isEmpty={() => false}
		transitionKey="notifications-list"
	>
		{#snippet loadingSlot()}
			<div class="stack stack-sm">
				{#each Array(4) as _}
					<SkeletonCard lines={3} />
				{/each}
			</div>
		{/snippet}
		{#snippet ready(items)}
			{#if filtered.length === 0}
				<div class="panel notifications-page-empty">
					<svg class="notifications-page-empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
					</svg>
					<p class="notifications-page-empty-text">
						{showCleared ? 'No notifications' : 'No new notifications'}
					</p>
				</div>
			{:else}
				<div class="stack stack-sm notifications-page-list">
					{#each filtered as notif (notif.id)}
						<div class="panel notifications-page-card" data-seen={notif.seen}>
							<div class="notifications-page-card-row">
								<div class="notifications-page-card-body">
									<div class="notifications-page-card-title-row">
										{#if !notif.seen}
											<span class="notifications-page-row-dot"></span>
										{/if}
										<h3 class="notifications-page-row-title">{notif.title ?? 'Notification'}</h3>
									</div>
									{#if notif.message}
										<p class="notifications-page-row-message">{notif.message}</p>
									{/if}
									{#if notif.created_at}
										<p class="notifications-page-row-time" title={formatDateTime(notif.created_at)}>
											{timeAgo(notif.created_at)}
										</p>
									{/if}
								</div>
								{#if !notif.seen && $isAdmin}
									<button
										onclick={() => dismiss(notif.id)}
										disabled={dismissing.has(notif.id)}
										class="btn notifications-page-dismiss-btn"
									>
										{dismissing.has(notif.id) ? '...' : 'Dismiss'}
									</button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		{/snippet}
		{#snippet empty()}
			<p class="notifications-page-empty-fallback">No notifications.</p>
		{/snippet}
	</LoadState>
</div>

<style>
	/* space-y-6 (1.5rem), the .stack default gap is already 1rem short. */
	.notifications-page { gap: 1.5rem; }
	/* alert's own border isn't in the original (a plain tinted strip, no
	   border), and its padding (0.5rem 0.75rem) is a hair short of this
	   banner's own px-4 py-2.5. */
	.notifications-page-feedback { border: 0; border-radius: var(--radius-lg); padding: 0.625rem 1rem; }
	.notifications-page-feedback-close { margin-left: 0.5rem; opacity: 0.6; }
	.notifications-page-feedback-close:hover { opacity: 1; }
	/* no flex-wrap: matches the original's own overflow (not wrap) behaviour
	   on narrow viewports - the right-hand controls cluster runs off the
	   edge rather than dropping to a new line. */
	.notifications-page-header { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
	/* .cluster wraps by default; the original's two side-groups were
	   non-wrapping flex items-center gap-3 rows (they overflow, not wrap,
	   on narrow viewports). */
	.notifications-page-header-title, .notifications-page-header-actions { display: flex; align-items: center; gap: 0.75rem; }
	/* the original badge had no whitespace-nowrap class (unlike .badge's own
	   default); at narrow widths, squeezed by the header's justify-between,
	   its "N new" text wraps to two lines rather than widening the pill. */
	.notifications-page-unseen-badge { border-radius: 9999px; padding: 0.125rem 0.625rem; white-space: normal; }
	.notifications-page-show-cleared { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* the original checkbox was explicitly h-4 w-4 (16px); the browser's own
	   default checkbox box is a different size and shifts the row's
	   cross-axis alignment. */
	.notifications-page-show-cleared-checkbox { width: 1rem; height: 1rem; border-radius: var(--radius-sm); }
	/* the originals were px-3 py-1.5 (0.375rem vertical) with no min-height,
	   shorter than .btn's own 0.5rem-1rem padding + 2.25rem min-height. The
	   Purge button had no visible border (text-only red, unlike btn-danger's
	   own border). */
	.notifications-page-purge-btn { border: 0; border-radius: var(--radius-lg); min-height: auto; padding: 0.375rem 0.75rem; }
	.notifications-page-purge-btn:hover { background: var(--color-danger-soft); }
	/* the original was ring-1 ring-primary/25, not a real border - a ring is a
	   box-shadow and doesn't add to the layout box the way .btn's own 1px
	   border does (which made this button, and the row containing it, 2px
	   taller than the original and shifted everything below down). */
	.notifications-page-dismiss-all-btn { border: 0; box-shadow: 0 0 0 1px var(--color-border-strong); border-radius: var(--radius-lg); min-height: auto; padding: 0.375rem 0.75rem; background: var(--color-primary-tint-1); color: var(--color-text-secondary); }
	.notifications-page-empty { text-align: center; padding: 1.5rem; }
	.notifications-page-empty-icon { margin: 0 auto; width: 3rem; height: 3rem; color: var(--color-text-faint); }
	.notifications-page-empty-text { margin-top: 0.75rem; font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text-muted); }
	.notifications-page-empty-fallback { padding: 2rem 0; text-align: center; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* space-y-3 (0.75rem), the original's per-card gap. */
	.notifications-page-list { gap: 0.75rem; }
	/* .panel's own shadow (--shadow-1) stands in for the original's shadow-xs;
	   everything else (border-color, radius, background, padding) is .panel's
	   own default, an exact match for rounded-lg border border-primary/20
	   bg-surface p-4. */
	.notifications-page-card[data-seen="true"] { opacity: 0.6; }
	.notifications-page-card-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
	.notifications-page-card-body { min-width: 0; flex: 1 1 0%; }
	.notifications-page-card-title-row { display: flex; align-items: center; gap: 0.5rem; }
	.notifications-page-row-dot { width: 0.5rem; height: 0.5rem; flex-shrink: 0; border-radius: 9999px; background: var(--color-warning); }
	/* the original title had no explicit text-size class (font-medium
	   text-gray-900 only), so it renders at the body default: 1rem/1.5 line
	   height (24px), not a text-sm/text-xs utility. */
	.notifications-page-row-title { font-size: 1rem; line-height: 1.5rem; font-weight: 500; color: var(--color-text); }
	.notifications-page-row-message { margin-top: 0.25rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
	/* the original was text-gray-600 dark:text-gray-400; --color-text-secondary is gray-700/gray-300, so it is right in light mode but a shade too bright in dark - --color-text-muted is the role that is gray-400 there. */
	:global(.dark) .notifications-page-row-message { color: var(--color-text-muted); }
	.notifications-page-row-time { margin-top: 0.375rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	/* the original Dismiss button: rounded-lg px-3 py-1.5 text-xs font-medium
	   bg-primary/5 text-gray-600 ring-1 ring-primary/25 hover:bg-primary/10 -
	   a tinted-fill button with no visible border box (ring, not border), so
	   btn's own border is dropped and the ring approximated with a matching
	   border colour instead (rings and borders paint differently, but no ring
	   utility exists in the allowed inline families). */
	/* ring-1 ring-primary/25 in the original, not a real border - see the
	   header Dismiss All button's own note above. */
	.notifications-page-dismiss-btn { flex-shrink: 0; border: 0; box-shadow: 0 0 0 1px var(--color-border-strong); border-radius: var(--radius-lg); min-height: auto; padding: 0.375rem 0.75rem; font-size: 0.75rem; line-height: 1rem; background: var(--color-primary-tint-1); color: var(--color-text-secondary); }
</style>

<ConfirmDialog
	open={purgeConfirmOpen}
	title="Purge Notifications"
	message="Permanently delete all cleared notifications from the database? This cannot be undone."
	confirmLabel="Purge"
	variant="danger"
	onconfirm={handlePurge}
	oncancel={() => (purgeConfirmOpen = false)}
/>
