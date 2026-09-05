import { describe, it, expect, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/environment', () => ({ browser: false }));

import { theme, toggleTheme } from '../stores/theme';

describe('theme store', () => {
	it('initial value is dark when browser is false', () => {
		expect(get(theme)).toBe('dark');
	});

	it('toggleTheme flips dark to light', () => {
		theme.set('dark');
		toggleTheme();
		expect(get(theme)).toBe('light');
	});

	it('toggleTheme flips light to dark', () => {
		theme.set('light');
		toggleTheme();
		expect(get(theme)).toBe('dark');
	});

	it('toggleTheme round-trips correctly', () => {
		theme.set('dark');
		toggleTheme();
		toggleTheme();
		expect(get(theme)).toBe('dark');
	});
});

describe('colorScheme - theme fetch dedup', () => {
	it('concurrent loadThemeCss calls for a built-in id only fetch its static CSS once', async () => {
		// Built-in themes load their CSS from the frontend's static assets
		// (/themes/{id}.css). The in-flight guard must dedup concurrent calls
		// (loadThemesFromApi + the subscribe handler racing on page load).
		const mockFetch = vi.fn((url: string) =>
			Promise.resolve({ ok: true, text: () => Promise.resolve('body{}') })
		);
		vi.stubGlobal('fetch', mockFetch);

		try {
			const { loadThemeCss } = await import('$lib/stores/colorScheme');

			await Promise.all([loadThemeCss('blue'), loadThemeCss('blue')]);

			const cssCalls = mockFetch.mock.calls.filter(
				([url]) => typeof url === 'string' && url === '/themes/blue.css'
			);
			expect(cssCalls.length).toBe(1);
		} finally {
			vi.unstubAllGlobals();
		}
	});

	it('writes fetched built-in CSS to localStorage for later reuse', async () => {
		vi.resetModules();
		const mockFetch = vi.fn((url: string) => {
			if (url === '/themes/blue.css') {
				return Promise.resolve({ ok: true, text: () => Promise.resolve('body { background: blue; }') });
			}
			return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
		});
		vi.stubGlobal('fetch', mockFetch);
		const setItem = vi.spyOn(Storage.prototype, 'setItem');

		try {
			const mod = await import('$lib/stores/colorScheme');
			await mod.loadThemeCss('blue');

			expect(setItem).toHaveBeenCalledWith(
				'theme-cache-v1-blue',
				'body { background: blue; }'
			);
		} finally {
			vi.unstubAllGlobals();
		}
	});
});
