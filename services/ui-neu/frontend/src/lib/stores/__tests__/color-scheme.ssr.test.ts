import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { COLOR_SCHEMES } from '$lib/themes/builtin-schemes';

vi.mock('$app/environment', () => ({ browser: false }));
vi.mock('$lib/api/themes', () => ({
	fetchThemes: vi.fn(),
	fetchTheme: vi.fn()
}));

const fetchMock = vi.fn();

beforeEach(() => {
	vi.clearAllMocks();
	vi.resetModules();
	vi.stubGlobal('fetch', fetchMock);
	fetchMock.mockResolvedValue({ ok: true, text: async () => 'x{}' });
	document.documentElement.removeAttribute('style');
	document.documentElement.className = '';
	delete document.documentElement.dataset.scheme;
});

describe('colorScheme store outside the browser', () => {
	it('starts on the default scheme and does not subscribe or touch the DOM', async () => {
		const { colorScheme } = await import('$lib/stores/color-scheme');

		expect(get(colorScheme)).toBe(COLOR_SCHEMES[0].id);
		expect(fetchMock).not.toHaveBeenCalled();
		expect(document.documentElement.dataset.scheme).toBeUndefined();
	});

	it('reapplySchemeForCurrentMode returns without writing tokens', async () => {
		const { reapplySchemeForCurrentMode } = await import('$lib/stores/color-scheme');

		reapplySchemeForCurrentMode();

		expect(document.documentElement.getAttribute('style')).toBeNull();
	});

	it('loadThemeCss caches the CSS but applies no scheme to the DOM', async () => {
		const { loadThemeCss } = await import('$lib/stores/color-scheme');

		await loadThemeCss('blue');

		expect(fetchMock).toHaveBeenCalledWith('/themes/blue.css');
		expect(document.documentElement.dataset.scheme).toBeUndefined();
		expect(document.getElementById('arm-theme-css')).toBeNull();
	});
});
