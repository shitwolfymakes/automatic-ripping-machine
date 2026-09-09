<script lang="ts">
	import { posterSrc } from '$lib/utils/poster';

	interface Props {
		url: string | null | undefined;
		alt?: string;
		class?: string;
		style?: string;
	}

	let { url, alt = '', class: className = 'poster-image h-28 w-20 shrink-0 object-cover', style: styleStr = '' }: Props = $props();

	let errored = $state(false);
	let lastUrl: string | null | undefined = url;

	// Reset error state only when the url value actually changes
	$effect(() => {
		if (url !== lastUrl) {
			lastUrl = url;
			errored = false;
		}
	});

	const showFallback = $derived(!url || errored);

	function onError() {
		errored = true;
	}
</script>

{#if showFallback}
	<!-- data-poster is the theme hook (same contract as data-progress-track):
	     schemes decorate posters through it rather than component classes. -->
	<div data-poster class="poster-image-fallback flex items-center justify-center {className}" style={styleStr || undefined}>
		<svg class="h-2/5 w-2/5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
			<circle cx="12" cy="12" r="10" />
			<circle cx="12" cy="12" r="3" />
			<circle cx="12" cy="12" r="6.5" stroke-width="0.75" opacity="0.4" />
		</svg>
	</div>
{:else}
	<img
		data-poster
		src={posterSrc(url)}
		{alt}
		class={className}
		style={styleStr || undefined}
		loading="lazy"
		onerror={onError}
	/>
{/if}

<style>
	/* Default radius (rounded-sm) for both the <img> and its fallback <div>,
	   moved here because rounded* is banned inline (spec 6.4). NOTE: a few
	   out-of-scope callers (not in Task 6's file list) still pass their own
	   rounded-* utility alongside this default class list (e.g. MusicSearch's
	   rounded-t-md poster tiles); this scoped, unlayered rule now wins that
	   contest unconditionally instead of the previous same-specificity,
	   source-order-dependent outcome. Flagged for whichever task migrates
	   those callers; see task-6-report.md. */
	.poster-image, .poster-image-fallback { border-radius: var(--radius-sm); }
	/* was bg-blue-100 text-blue-400: the info tokens (--color-info resolves to
	   --color-primary, a much more saturated blue) read too strong for this
	   icon, so the icon colour uses the blue accent token instead, which is
	   close to the original blue-400/blue-500 (--color-accent-2 is exactly
	   Tailwind's blue-500 rgb(59,130,246), blue-400 is rgb(96,165,250)). */
	.poster-image-fallback { background: var(--color-info-soft); color: var(--color-accent-2); }
</style>
