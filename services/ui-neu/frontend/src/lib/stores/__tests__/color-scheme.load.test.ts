import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';
import { COLOR_SCHEMES } from '$lib/themes/builtin-schemes';

vi.mock('$app/environment', () => ({ browser: true }));

const fetchThemes = vi.fn();
const fetchTheme = vi.fn();
vi.mock('$lib/api/themes', () => ({
	fetchThemes: (...args: unknown[]) => fetchThemes(...args),
	fetchTheme: (...args: unknown[]) => fetchTheme(...args)
}));

const fetchMock = vi.fn();

/** Reply to the built-in CSS fetch: a map of id -> css, anything else is a 404. */
function serveBuiltinCss(files: Record<string, string>) {
	fetchMock.mockImplementation(async (url: string) => {
		const id = decodeURIComponent(url.replace('/themes/', '').replace('.css', ''));
		const css = files[id];
		return css === undefined ? { ok: false, text: async () => '' } : { ok: true, text: async () => css };
	});
}

async function freshModule() {
	vi.resetModules();
	const mod = await import('$lib/stores/color-scheme');
	await mod.loadThemeCss(get(mod.colorScheme));
	return mod;
}

function styleEl() {
	return document.getElementById('arm-theme-css') as HTMLStyleElement | null;
}

const root = document.documentElement;

beforeEach(() => {
	vi.clearAllMocks();
	localStorage.clear();
	root.className = '';
	root.removeAttribute('style');
	delete root.dataset.scheme;
	styleEl()?.remove();
	fetchThemes.mockResolvedValue([]);
	fetchTheme.mockResolvedValue({ css: '' });
	serveBuiltinCss({});
	vi.stubGlobal('fetch', fetchMock);
	vi.stubGlobal(
		'matchMedia',
		vi.fn(() => ({ matches: false }))
	);
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('applyScheme with a light-locked scheme', () => {
	it('removes the dark class and ignores a saved dark preference', async () => {
		localStorage.setItem('theme', 'dark');
		const { colorScheme } = await freshModule();
		root.classList.add('dark');

		colorScheme.set('library-archive');
		await vi.waitFor(() => expect(root.dataset.scheme).toBe('library-archive'));

		expect(root.classList.contains('dark')).toBe(false);
	});
});

describe('reapplySchemeForCurrentMode', () => {
	it('falls back to the default scheme when the active id matches no scheme', async () => {
		fetchTheme.mockRejectedValue(new Error('not found'));
		const { colorScheme, reapplySchemeForCurrentMode } = await freshModule();
		colorScheme.set('ghost');
		await vi.waitFor(() => expect(fetchTheme).toHaveBeenCalledWith('ghost'));
		root.removeAttribute('style');

		reapplySchemeForCurrentMode();

		const primary = COLOR_SCHEMES[0].tokens['--color-primary'];
		expect(root.style.getPropertyValue('--color-primary')).toBe(primary);
	});

	it('leaves the tokens alone for a mode-locked scheme', async () => {
		const { colorScheme, reapplySchemeForCurrentMode } = await freshModule();
		colorScheme.set('library-archive');
		await vi.waitFor(() => expect(root.dataset.scheme).toBe('library-archive'));
		root.removeAttribute('style');

		reapplySchemeForCurrentMode();

		expect(root.getAttribute('style')).toBeNull();
	});
});

describe('theme CSS injection', () => {
	it('creates the style element, reuses it on a re-apply, then removes it for a scheme without CSS', async () => {
		serveBuiltinCss({ blue: 'a{}', sunset: 'b{}' });
		const { colorScheme, loadThemeCss } = await freshModule();
		const first = styleEl();
		expect(first?.parentElement).toBe(document.head);
		expect(first?.textContent).toBe('a{}');

		await loadThemeCss('blue');
		expect(styleEl()).toBe(first);

		// Switching to a scheme whose CSS is not cached yet drops the style
		// element first; it is recreated once the CSS arrives.
		colorScheme.set('sunset');
		await loadThemeCss('sunset');
		expect(styleEl()?.textContent).toBe('b{}');

		serveBuiltinCss({});
		colorScheme.set('forest');
		await loadThemeCss('forest');
		expect(styleEl()).toBeNull();
	});

	it('uses the CSS carried by the scheme itself', async () => {
		const { colorScheme } = await freshModule();
		colorScheme.set('stealth-ops');
		await vi.waitFor(() => expect(styleEl()?.textContent).toContain('[data-scheme="stealth-ops"]'));
	});
});

describe('fetchBuiltinCss', () => {
	it('gives no CSS for a non-ok response', async () => {
		const { allSchemes } = await freshModule();

		expect(fetchMock).toHaveBeenCalledWith('/themes/blue.css');
		expect(get(allSchemes).find((s) => s.id === 'blue')?.css).toBeUndefined();
		expect(styleEl()).toBeNull();
	});
});

describe('loadThemesFromApi', () => {
	it('overlays API themes on the built-ins, merging tokens over a built-in of the same id', async () => {
		fetchThemes.mockResolvedValue([
			{ id: 'blue', label: 'My Blue', swatch: '#111', tokens: { '--extra': '1' }, builtin: true },
			{ id: 'mine', label: 'Mine', swatch: '#222', tokens: { '--only': '2' } }
		]);
		const { loadThemesFromApi, allSchemes } = await freshModule();

		await loadThemesFromApi();

		const schemes = get(allSchemes);
		const blue = schemes.find((s) => s.id === 'blue');
		expect(blue?.label).toBe('My Blue');
		expect(blue?.tokens['--extra']).toBe('1');
		expect(blue?.tokens['--color-primary']).toBe(COLOR_SCHEMES[0].tokens['--color-primary']);
		expect(blue?.builtin).toBe(true);
		const mine = schemes.find((s) => s.id === 'mine');
		expect(mine?.tokens).toEqual({ '--only': '2' });
		expect(mine?.builtin).toBe(false);
		expect(schemes.find((s) => s.id === 'sunset')?.builtin).toBe(true);
		expect(schemes).toHaveLength(COLOR_SCHEMES.length + 1);
	});

	it('treats a null theme list as empty', async () => {
		fetchThemes.mockResolvedValue(null);
		const { loadThemesFromApi, allSchemes } = await freshModule();

		await loadThemesFromApi();

		const schemes = get(allSchemes);
		expect(schemes).toHaveLength(COLOR_SCHEMES.length);
		expect(schemes.every((s) => s.builtin === true)).toBe(true);
	});

	it('keeps the built-ins when fetchThemes rejects', async () => {
		fetchThemes.mockRejectedValue(new Error('down'));
		const { loadThemesFromApi, allSchemes } = await freshModule();
		const before = get(allSchemes);

		await loadThemesFromApi();

		expect(get(allSchemes)).toEqual(before);
		expect(get(allSchemes)).toHaveLength(COLOR_SCHEMES.length);
	});
});

describe('loadThemeCss', () => {
	it('re-applies a cached id with its CSS without fetching again', async () => {
		serveBuiltinCss({ blue: 'a{}' });
		const { loadThemeCss, allSchemes } = await freshModule();
		expect(fetchMock).toHaveBeenCalledTimes(1);
		styleEl()?.remove();

		await loadThemeCss('blue');

		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(styleEl()?.textContent).toBe('a{}');
		expect(get(allSchemes).find((s) => s.id === 'blue')?.css).toBe('a{}');
	});

	it('does nothing for a cached id that matches no scheme', async () => {
		fetchTheme.mockResolvedValue({ css: 'g{}' });
		const { colorScheme, loadThemeCss } = await freshModule();
		colorScheme.set('ghost');
		await loadThemeCss('ghost');
		expect(fetchTheme).toHaveBeenCalledTimes(1);
		styleEl()?.remove();
		root.dataset.scheme = 'untouched';

		await loadThemeCss('ghost');

		expect(fetchTheme).toHaveBeenCalledTimes(1);
		expect(root.dataset.scheme).toBe('untouched');
		expect(styleEl()).toBeNull();
	});

	it('shares one fetch between concurrent calls for the same id', async () => {
		let release: (v: { css: string }) => void = () => {};
		fetchTheme.mockReturnValue(new Promise((resolve) => (release = resolve)));
		const { loadThemeCss } = await freshModule();

		const first = loadThemeCss('shared');
		const second = loadThemeCss('shared');
		release({ css: 's{}' });
		await Promise.all([first, second]);

		expect(fetchTheme).toHaveBeenCalledTimes(1);
	});
});
