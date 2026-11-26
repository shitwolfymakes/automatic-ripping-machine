import '@testing-library/jest-dom/vitest';

// jsdom doesn't implement Element.animate — stub it for Svelte transitions
// (slide, fade, etc.) that use the Web Animations API.
if (typeof Element.prototype.animate !== 'function') {
	Element.prototype.animate = function () {
		return {
			cancel: () => {},
			finish: () => {},
			pause: () => {},
			play: () => {},
			onfinish: null
		} as unknown as Animation;
	};
}

// jsdom doesn't implement window.matchMedia — stub it for stores that
// check prefers-color-scheme on the client side.
Object.defineProperty(globalThis, 'matchMedia', {
	writable: true,
	value: (query: string) => ({
		matches: false,
		media: query,
		onchange: null,
		addListener: () => {},
		removeListener: () => {},
		addEventListener: () => {},
		removeEventListener: () => {},
		dispatchEvent: () => false
	})
});

// The Sessions area's list filters live in a module-level store so they
// outlast a list; clear them between tests so no test inherits another's.
import { afterEach } from 'vitest';
import { resetListFilters } from '$lib/stores/session-list-filters.svelte';
afterEach(() => resetListFilters());
