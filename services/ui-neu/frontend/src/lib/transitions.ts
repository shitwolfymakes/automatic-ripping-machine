import { crossfade } from 'svelte/transition';
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

// Slide + fade for block-level panels (dashboard sections, banners, list
// rows). A plain fade animates opacity only, so a panel mounting mid-page
// shoves the content below it down in a single frame — the layout snap reads
// as a "pop" even though the panel itself faded. Animating height/padding/
// margin alongside opacity lets surrounding content ease into place.
export function panel(node: Element, { duration = 200 }: { duration?: number } = {}): TransitionConfig {
	const style = getComputedStyle(node);
	const opacity = +style.opacity;
	const height = parseFloat(style.height);
	const paddingTop = parseFloat(style.paddingTop);
	const paddingBottom = parseFloat(style.paddingBottom);
	const marginTop = parseFloat(style.marginTop);
	const marginBottom = parseFloat(style.marginBottom);
	const borderTopWidth = parseFloat(style.borderTopWidth);
	const borderBottomWidth = parseFloat(style.borderBottomWidth);
	return {
		duration: reducedMotion ? 0 : duration,
		easing: cubicOut,
		css: (t) =>
			'overflow: hidden;' +
			`opacity: ${t * opacity};` +
			`height: ${t * height}px;` +
			`padding-top: ${t * paddingTop}px;` +
			`padding-bottom: ${t * paddingBottom}px;` +
			`margin-top: ${t * marginTop}px;` +
			`margin-bottom: ${t * marginBottom}px;` +
			`border-top-width: ${t * borderTopWidth}px;` +
			`border-bottom-width: ${t * borderBottomWidth}px;`
	};
}
