import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { COLOR_SCHEMES, colorScheme, schemeLocksMode } from '../stores/colorScheme';

const DARK_ONLY_IDS = [
	'glass', 'cinema', 'gaming', 'royale', 'lcars',
	'tactical', 'craft', 'terminal', 'blockbuster', 'hollywood-video-v2'
];

describe('COLOR_SCHEMES', () => {
	it('every scheme has required fields', () => {
		for (const scheme of COLOR_SCHEMES) {
			expect(scheme.id).toBeTypeOf('string');
			expect(scheme.label).toBeTypeOf('string');
			expect(scheme.swatch).toBeTypeOf('string');
			expect(scheme.tokens).toBeTypeOf('object');
			expect(Object.keys(scheme.tokens).length).toBeGreaterThan(0);
		}
	});

	it('mode values are only light, dark, or undefined', () => {
		for (const scheme of COLOR_SCHEMES) {
			if (scheme.mode !== undefined) {
				expect(['light', 'dark']).toContain(scheme.mode);
			}
		}
	});

	it('all dark-only themes have mode: dark', () => {
		for (const id of DARK_ONLY_IDS) {
			const scheme = COLOR_SCHEMES.find((s) => s.id === id);
			expect(scheme, `scheme '${id}' should exist`).toBeDefined();
			expect(scheme!.mode, `scheme '${id}' should be dark`).toBe('dark');
		}
	});

	it('no schemes have a forceDark property', () => {
		for (const scheme of COLOR_SCHEMES) {
			expect((scheme as unknown as Record<string, unknown>).forceDark).toBeUndefined();
		}
	});

	it('has at least one scheme without mode (user-selectable theme)', () => {
		const unlocked = COLOR_SCHEMES.filter((s) => s.mode === undefined);
		expect(unlocked.length).toBeGreaterThan(0);
	});

	it('every id is unique', () => {
		const ids = COLOR_SCHEMES.map((s) => s.id);
		expect(new Set(ids).size).toBe(ids.length);
	});

	it('every scheme includes a --radius token', () => {
		for (const scheme of COLOR_SCHEMES) {
			expect(scheme.tokens['--radius'], `scheme '${scheme.id}' should have --radius`).toBeDefined();
		}
	});

	it('--radius values are valid CSS lengths', () => {
		const validPattern = /^(\d+(\.\d+)?(rem|px|em)|0)$/;
		for (const scheme of COLOR_SCHEMES) {
			const radius = scheme.tokens['--radius'];
			expect(radius, `scheme '${scheme.id}' --radius '${radius}' should be a valid CSS length`).toMatch(validPattern);
		}
	});
});

describe('schemeLocksMode', () => {
	it('returns true for a scheme with mode set', () => {
		colorScheme.set('glass');
		expect(get(schemeLocksMode)).toBe(true);
	});

	it('returns false for a scheme without mode', () => {
		colorScheme.set('blue');
		expect(get(schemeLocksMode)).toBe(false);
	});

	it('returns false for an unknown scheme id', () => {
		colorScheme.set('nonexistent');
		expect(get(schemeLocksMode)).toBe(false);
	});
});

describe('applyScheme effective-mode tokens', () => {
	const DEFAULT_SCHEME = COLOR_SCHEMES[0]; // 'blue' / Default

	// colorScheme is a plain writable store: setting it to the value it
	// already holds does not notify subscribers, so applyScheme would not
	// re-run. Force a re-apply the same way the app does when the mode
	// changes: bounce through a different id first.
	function reapply(id: string) {
		colorScheme.set(id === 'blue' ? 'sunset' : 'blue');
		colorScheme.set(id);
	}

	beforeEach(() => {
		document.documentElement.classList.remove('dark');
		document.documentElement.removeAttribute('style');
		localStorage.clear();
	});

	it('writes the dark twin of a token when the saved theme is dark', () => {
		localStorage.setItem('theme', 'dark');
		reapply(DEFAULT_SCHEME.id);
		const surface = document.documentElement.style.getPropertyValue('--color-surface').trim();
		expect(surface).toBe(DEFAULT_SCHEME.tokens['--color-surface-dark']);
	});

	it('writes the light value once the saved theme switches back to light and the scheme re-applies', () => {
		localStorage.setItem('theme', 'dark');
		reapply(DEFAULT_SCHEME.id);
		expect(document.documentElement.style.getPropertyValue('--color-surface').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-surface-dark']);

		localStorage.setItem('theme', 'light');
		reapply(DEFAULT_SCHEME.id);
		expect(document.documentElement.style.getPropertyValue('--color-surface').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-surface']);
	});

	it('flips --color-page and --color-primary-text along with --color-surface', () => {
		localStorage.setItem('theme', 'dark');
		reapply(DEFAULT_SCHEME.id);
		expect(document.documentElement.style.getPropertyValue('--color-page').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-page-dark']);
		expect(document.documentElement.style.getPropertyValue('--color-primary-text').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-primary-text-dark']);
	});

	it('still writes the legacy -dark-suffixed names unchanged', () => {
		localStorage.setItem('theme', 'dark');
		reapply(DEFAULT_SCHEME.id);
		expect(document.documentElement.style.getPropertyValue('--color-surface-dark').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-surface-dark']);
		expect(document.documentElement.style.getPropertyValue('--color-page-dark').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-page-dark']);
	});

	it('keeps --color-primary mode-invariant even though the scheme has a --color-primary-dark alias', () => {
		localStorage.setItem('theme', 'dark');
		reapply(DEFAULT_SCHEME.id);
		expect(document.documentElement.style.getPropertyValue('--color-primary').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-primary']);
		// The legacy alias itself is still written unchanged for unmigrated
		// components (e.g. `dark:text-primary-dark`).
		expect(document.documentElement.style.getPropertyValue('--color-primary-dark').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-primary-dark']);
	});

	it('does not write a -dark value for a role the scheme does not pair (e.g. --radius)', () => {
		localStorage.setItem('theme', 'dark');
		reapply(DEFAULT_SCHEME.id);
		expect(document.documentElement.style.getPropertyValue('--radius').trim())
			.toBe(DEFAULT_SCHEME.tokens['--radius']);
	});

	it('restores a saved light preference after leaving a mode-locked scheme, instead of inheriting its leftover dark class', () => {
		localStorage.setItem('theme', 'light');

		// A mode-locked scheme (lcars, mode: 'dark') forces the dark class on,
		// independent of the saved preference.
		reapply('lcars');
		expect(document.documentElement.classList.contains('dark')).toBe(true);

		// Switching to an unlocked scheme must recompute the mode from the
		// saved preference, not from the dark class lcars left behind.
		reapply('blue');
		expect(document.documentElement.classList.contains('dark')).toBe(false);
		expect(document.documentElement.style.getPropertyValue('--color-surface').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-surface']);
	});
});

describe('theme store toggling re-applies scheme tokens', () => {
	const DEFAULT_SCHEME = COLOR_SCHEMES[0]; // 'blue' / Default

	beforeEach(() => {
		document.documentElement.classList.remove('dark');
		document.documentElement.removeAttribute('style');
		localStorage.clear();
		colorScheme.set(DEFAULT_SCHEME.id);
	});

	it('toggleTheme flips --color-surface to the dark value with no colorScheme change', async () => {
		const { theme, toggleTheme } = await import('../stores/theme');
		theme.set('dark');
		theme.set('light'); // force a change notification regardless of prior test state
		expect(document.documentElement.style.getPropertyValue('--color-surface').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-surface']);

		toggleTheme();
		expect(get(theme)).toBe('dark');
		expect(document.documentElement.classList.contains('dark')).toBe(true);
		expect(document.documentElement.style.getPropertyValue('--color-surface').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-surface-dark']);
	});

	it('toggleTheme back to light flips --color-surface back to the light value', async () => {
		const { theme, toggleTheme } = await import('../stores/theme');
		theme.set('light');
		theme.set('dark'); // force a change notification regardless of prior test state
		expect(document.documentElement.style.getPropertyValue('--color-surface').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-surface-dark']);

		toggleTheme();
		expect(get(theme)).toBe('light');
		expect(document.documentElement.classList.contains('dark')).toBe(false);
		expect(document.documentElement.style.getPropertyValue('--color-surface').trim())
			.toBe(DEFAULT_SCHEME.tokens['--color-surface']);
	});

	it('does not re-apply when the active scheme locks the mode', async () => {
		colorScheme.set('lcars'); // mode: 'dark'
		const lcars = COLOR_SCHEMES.find((s) => s.id === 'lcars')!;
		const { theme, toggleTheme } = await import('../stores/theme');
		theme.set('dark');
		expect(document.documentElement.style.getPropertyValue('--color-surface').trim())
			.toBe(lcars.tokens['--color-surface']);

		// Toggling the theme store while a locked scheme is active must not
		// change the locked scheme's own tokens.
		toggleTheme();
		expect(document.documentElement.style.getPropertyValue('--color-surface').trim())
			.toBe(lcars.tokens['--color-surface']);
	});
});
