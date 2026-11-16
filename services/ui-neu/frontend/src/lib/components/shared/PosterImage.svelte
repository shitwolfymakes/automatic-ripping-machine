<script lang="ts">
	import { fade } from 'svelte/transition';
	import { fadeIn } from '$lib/ui/transitions';
	import { posterSrc } from '$lib/match/poster';

	interface Props {
		url: string | null | undefined;
		alt?: string;
		class?: string;
	}

	let { url, alt = '', class: className = 'poster-image h-28 w-20 shrink-0 object-cover' }: Props = $props();

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

	// The poster stays transparent until it has downloaded, then fades in, so
	// it never paints top-down or pops in after the page. Keyed by url, so a
	// new poster on the same element fades in again.
	let loadedUrl = $state<string | null | undefined>(null);
	const loaded = $derived(loadedUrl === url);

	function onError() {
		errored = true;
	}

	// A poster from the browser cache shows at once instead of fading in again
	// on every visit. Lazy images have not started loading when they mount, so
	// img.complete cannot tell; a load landing within CACHED_LOAD_MS of the
	// poster appearing did not touch the network.
	const CACHED_LOAD_MS = 50;
	let shownAt = 0;
	let instant = $state(false);

	// Re-runs per url (it reads it), so a new poster on the same element is
	// timed from when its url arrived.
	function markShown(_img: HTMLImageElement) {
		void url;
		shownAt = performance.now();
	}

	function onLoad() {
		instant = performance.now() - shownAt < CACHED_LOAD_MS;
		loadedUrl = url;
	}
</script>

{#if showFallback}
	<!-- data-poster is the theme hook (same contract as data-progress-track):
	     schemes decorate posters through it rather than component classes. -->
	<div data-poster class="poster-image-fallback flex items-center justify-center {className}" in:fade={fadeIn}>
		<svg
			class="h-2/5 w-2/5"
			fill="none"
			stroke="currentColor"
			viewBox="0 0 24 24"
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		>
			<circle cx="12" cy="12" r="10" />
			<circle cx="12" cy="12" r="3" />
			<circle cx="12" cy="12" r="6.5" stroke-width="0.75" opacity="0.4" />
		</svg>
	</div>
{:else}
	<img
		data-poster
		data-loaded={loaded}
		data-instant={instant}
		src={posterSrc(url)}
		{alt}
		class={className}
		loading="lazy"
		onerror={onError}
		onload={onLoad}
		{@attach markShown}
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
	.poster-image,
	.poster-image-fallback {
		border-radius: var(--radius-sm);
	}
	/* was bg-blue-100 text-blue-400: the info tokens (--color-info resolves to
	   --color-primary, a much more saturated blue) read too strong for this
	   icon, so the icon colour uses the blue accent token instead, which is
	   close to the original blue-400/blue-500 (--color-accent-2 is exactly
	   Tailwind's blue-500 rgb(59,130,246), blue-400 is rgb(96,165,250)). */
	/* Opacity only: the image box is sized by its class, so nothing moves. */
	img {
		transition: opacity var(--motion-fast) var(--ease);
	}
	img[data-loaded='false'] {
		opacity: 0;
	}
	img[data-instant='true'] {
		transition: none;
	}
	.poster-image-fallback {
		background: var(--color-info-soft);
		color: var(--color-accent-2);
	}
</style>
