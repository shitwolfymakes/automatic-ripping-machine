<script lang="ts">
	import { formatDateTime, timeAgo } from '$lib/utils/format';
	import { isAdmin } from '$lib/stores/auth';
	import type { NotificationInboxView } from '$lib/types/api.gen';

	interface Props {
		notif: NotificationInboxView;
		dismissing: boolean;
		ondismiss: (id: string) => unknown;
	}

	let { notif, dismissing, ondismiss }: Props = $props();
</script>

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
			<button onclick={() => ondismiss(notif.id)} disabled={dismissing} class="btn notifications-page-dismiss-btn">
				{dismissing ? '...' : 'Dismiss'}
			</button>
		{/if}
	</div>
</div>

<style>
	/* .panel's own shadow (--shadow-1) stands in for the original's shadow-xs;
	   everything else (border-color, radius, background, padding) is .panel's
	   own default, an exact match for rounded-lg border border-primary/20
	   bg-surface p-4. */
	.notifications-page-card[data-seen='true'] {
		opacity: 0.6;
	}
	.notifications-page-card-row {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
	}
	.notifications-page-card-body {
		min-width: 0;
		flex: 1 1 0%;
	}
	.notifications-page-card-title-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.notifications-page-row-dot {
		width: 0.5rem;
		height: 0.5rem;
		flex-shrink: 0;
		border-radius: 9999px;
		background: var(--color-warning);
	}
	/* the original title had no explicit text-size class (font-medium
	   text-gray-900 only), so it renders at the body default: 1rem/1.5 line
	   height (24px), not a text-sm/text-xs utility. */
	.notifications-page-row-title {
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 500;
		color: var(--color-text);
	}
	.notifications-page-row-message {
		margin-top: 0.25rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-secondary);
	}
	/* the original was text-gray-600 dark:text-gray-400; --color-text-secondary is gray-700/gray-300, so it is right in light mode but a shade too bright in dark - --color-text-muted is the role that is gray-400 there. */
	:global(.dark) .notifications-page-row-message {
		color: var(--color-text-muted);
	}
	.notifications-page-row-time {
		margin-top: 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	/* the original Dismiss button: rounded-lg px-3 py-1.5 text-xs font-medium
	   bg-primary/5 text-gray-600 ring-1 ring-primary/25 hover:bg-primary/10 -
	   a tinted-fill button with no visible border box (ring, not border), so
	   btn's own border is dropped and the ring approximated with a matching
	   border colour instead (rings and borders paint differently, but no ring
	   utility exists in the allowed inline families). */
	/* ring-1 ring-primary/25 in the original, not a real border - see the
	   header Dismiss All button's own note above. */
	.notifications-page-dismiss-btn {
		flex-shrink: 0;
		border: 0;
		box-shadow: 0 0 0 1px var(--color-border-strong);
		border-radius: var(--radius-lg);
		min-height: auto;
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		line-height: 1rem;
		background: var(--color-primary-tint-1);
		color: var(--color-text-secondary);
	}
</style>
