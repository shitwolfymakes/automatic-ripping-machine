<script lang="ts">
	interface Props {
		showCleared: boolean;
	}

	let { showCleared }: Props = $props();
</script>

<div class="panel notifications-page-empty">
	<svg class="notifications-page-empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
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

<style>
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
</style>
