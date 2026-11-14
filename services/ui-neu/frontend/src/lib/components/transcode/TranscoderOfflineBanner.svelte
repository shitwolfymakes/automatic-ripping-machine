<script lang="ts">
	import { fade } from 'svelte/transition';
	import { fadeIn, fadeOut } from '$lib/transitions';
</script>

<div in:fade={fadeIn} out:fade={fadeOut} class="flex items-center gap-3 panel-section transcoder-page-offline-banner">
	<div class="shrink-0 transcoder-page-offline-dot"></div>
	<div>
		<p class="transcoder-page-offline-title">Transcoder Offline</p>
		<p class="transcoder-page-offline-subtitle">
			The transcoder service is not responding. Transcoding features are unavailable.
		</p>
	</div>
</div>

<style>
	.transcoder-page-offline-dot {
		height: 0.75rem;
		width: 0.75rem;
		border-radius: 9999px;
		background: var(--color-text-faint);
	}
	.transcoder-page-offline-title {
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.transcoder-page-offline-subtitle {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	/* panel-section's own background is a translucent primary tint, which
	   only matches the original's DARK-mode bg-page/5 half of its pair; the
	   original LIGHT mode was the flat --color-page - same gap as the
	   NotificationsTab precedent from Task 9 */
	.transcoder-page-offline-banner {
		background: var(--color-page);
	}
</style>
