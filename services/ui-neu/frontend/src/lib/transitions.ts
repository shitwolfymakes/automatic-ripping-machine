import { crossfade, slide } from 'svelte/transition';
import type { TransitionConfig } from 'svelte/transition';
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

// Enter/leave for block-level panels (dashboard sections, banners, cards,
// list rows): a plain fade. Panels never slide — sliding is reserved for
// user-toggled expandable content (see expand below). Centralized here so
// panel animation is tuned in one place.
export function panel(node: Element, { duration = 200 }: { duration?: number } = {}): TransitionConfig {
	const opacity = +getComputedStyle(node).opacity;
	return {
		duration: reducedMotion ? 0 : duration,
		easing: cubicOut,
		css: (t) => `opacity: ${t * opacity}`
	};
}

// User-toggled expandable content (detail sections behind a chevron, config
// sub-panels): slide open/closed. Wraps svelte's slide with the shared
// duration/easing and the reduced-motion guard the inline usages lacked.
export function expand(node: Element, { duration = 200 }: { duration?: number } = {}): TransitionConfig {
	return slide(node, { duration: reducedMotion ? 0 : duration, easing: cubicOut });
}
