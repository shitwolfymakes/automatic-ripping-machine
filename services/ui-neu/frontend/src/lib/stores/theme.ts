import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import { reapplySchemeForCurrentMode } from './color-scheme';
import { readStorage, writeStorage } from '$lib/utils/safe-storage';

function getInitialTheme(): 'light' | 'dark' {
	if (!browser) return 'dark';
	const stored = readStorage('theme');
	if (stored === 'light' || stored === 'dark') return stored;
	return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export const theme = writable<'light' | 'dark'>(getInitialTheme());

if (browser) {
	theme.subscribe((value) => {
		writeStorage('theme', value);
		document.documentElement.classList.toggle('dark', value === 'dark');
		// The active color scheme's inline tokens are written per-mode
		// (see applyScheme in colorScheme.ts); re-apply them for the mode
		// this toggle just switched to.
		reapplySchemeForCurrentMode();
	});
}

export function toggleTheme() {
	theme.update((current) => (current === 'dark' ? 'light' : 'dark'));
}
