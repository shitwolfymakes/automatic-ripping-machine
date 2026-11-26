<script lang="ts">
	import Glyph from '$lib/components/shared/Glyph.svelte';
	interface Props {
		showCleared: boolean;
	}

	let { showCleared }: Props = $props();
</script>

<div class="panel notifications-page-empty">
	<Glyph name="bell" class="notifications-page-empty-icon" />
	<p class="notifications-page-empty-text">
		{showCleared ? 'No notifications' : 'No new notifications'}
	</p>
</div>

<style>
	.notifications-page-empty {
		text-align: center;
		padding: 1.5rem;
	}
	/* :global: set on Glyph through its class prop */
	:global(.notifications-page-empty-icon) {
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
