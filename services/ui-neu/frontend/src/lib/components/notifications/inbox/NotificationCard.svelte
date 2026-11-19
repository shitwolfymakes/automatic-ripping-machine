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
	/* .panel's own shadow (--shadow-1) is used as is; everything else (border-color, radius,
	   background, padding) is .panel's own default. */
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
	/* the title has no explicit text-size class, so it renders at the body default: 1rem with a 1.5
	   line height (24px). */
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
	/* the wanted colour is gray-600 in light mode and gray-400 in dark; --color-text-secondary is gray-700/gray-300, so it is right in light mode but a shade too bright in dark - --color-text-muted is the role that is gray-400 there. */
	:global(.dark) .notifications-page-row-message {
		color: var(--color-text-muted);
	}
	.notifications-page-row-time {
		margin-top: 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	/* the Dismiss button is a tinted-fill button with no visible border box (ring, not border), so
	   btn's own border is dropped and the ring approximated with a matching
	   border colour instead (rings and borders paint differently, but no ring
	   utility exists in the allowed inline families). */
	/* ring-1 ring-primary/25, not a real border - see the
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
