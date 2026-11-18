<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import type { ImageCache } from '$lib/stores/image-cache.svelte';

	interface Props {
		cache: ImageCache;
	}

	let { cache }: Props = $props();
</script>

<div class="panel settings-page-panel-wide">
	<div class="flex items-center justify-between">
		<div>
			<h3 class="settings-page-panel-title settings-page-panel-title-flush">Image Cache</h3>
			<p class="settings-page-description mt-1">
				{#if cache.loading}Loading...
				{:else if cache.stats}{cache.stats.count} cached {plural(cache.stats.count, 'image')} ({cache.stats.size_mb}
					MB)
				{:else}Unable to load cache stats
				{/if}
			</p>
		</div>
		<button
			type="button"
			onclick={() => (cache.confirmOpen = true)}
			disabled={cache.busy || !cache.stats?.count}
			class="btn btn-danger btn-sm settings-page-clear-cache-btn"
		>
			Clear Cache
		</button>
	</div>
	{#if cache.feedback}
		<p class="mt-2 settings-page-feedback" data-error={cache.feedback.type !== 'success'}>
			{cache.feedback.message}
		</p>
	{/if}
</div>

<style>
	/* the section-card h3s in Themes were text-base font-semibold (1rem/
	   1.5rem), distinct from .panel-title's uppercase eyebrow look. */
	.settings-page-panel-title {
		margin-bottom: 0.25rem;
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-text);
	}
	/* Dark Mode's and Image Cache's h3 had no mb-1 in the original (only
	   Color Scheme's and User Themes' did). */
	.settings-page-panel-title-flush {
		margin-bottom: 0;
	}
	/* the original Clear Cache button had no border at all
	   (text-red-600 hover:bg-red-500/10), not btn-danger's outlined look. */
	.settings-page-clear-cache-btn {
		border-color: transparent;
	}
	.settings-page-clear-cache-btn:hover {
		background: var(--color-danger-soft);
	}
	/* most "muted description under a heading" paragraphs on this page were
	   text-sm (0.875rem/1.25rem), not panel-hint's 0.75rem - panel-hint is
	   sized for a note under a form control, a visibly smaller role. */
	.settings-page-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.settings-page-feedback {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.settings-page-feedback[data-error='true'] {
		color: var(--color-danger);
	}
	/* the Themes tab's four cards were p-6 (1.5rem) in the original, not
	   .panel's own p-4 (1rem) default. */
	.settings-page-panel-wide {
		padding: 1.5rem;
	}
</style>
