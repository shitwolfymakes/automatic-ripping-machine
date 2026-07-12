import { crossfade } from 'svelte/transition';
import { cubicOut } from 'svelte/easing';

const reducedMotion =
	globalThis.window?.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

export const [send, receive] = crossfade({
	duration: reducedMotion ? 0 : 200,
	easing: cubicOut,
	// Without a fallback, a receive() with no matching send() (e.g. the first
	// render after a page load, where the loading phase never painted) skips
	// the transition entirely and content pops in. Fall back to a plain fade
	// so fresh page loads ease in instead of snapping.
	fallback(node) {
		void node;
		return {
			duration: reducedMotion ? 0 : 200,
			easing: cubicOut,
			css: (t) => `opacity: ${t}`
		};
	}
});

export const fadeIn = { duration: reducedMotion ? 0 : 150, easing: cubicOut };
export const fadeOut = { duration: reducedMotion ? 0 : 150, easing: cubicOut };
