import { crossfade } from 'svelte/transition';
import type { TransitionConfig } from 'svelte/transition';
import { cubicOut } from 'svelte/easing';

const reducedMotion =
	globalThis.window?.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

export const [send, receive] = crossfade({
	duration: reducedMotion ? 0 : 200,
	easing: cubicOut
});

export const fadeIn = { duration: reducedMotion ? 0 : 150, easing: cubicOut };
export const fadeOut = { duration: reducedMotion ? 0 : 150, easing: cubicOut };

// Small conditionally-rendered elements (feedback messages, badges, inline
// warnings, revealed rows): quick fade-in on appear. Use as `in:reveal` ONLY.
export function reveal(node: Element, { duration = 150 }: { duration?: number } = {}): TransitionConfig {
	const opacity = +getComputedStyle(node).opacity;
	return {
		duration: reducedMotion ? 0 : duration,
		easing: cubicOut,
		css: (t) => `opacity: ${t * opacity}`
	};
}
