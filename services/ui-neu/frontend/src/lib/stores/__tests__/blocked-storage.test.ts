import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';

// With site storage blocked, reading `localStorage` itself throws a
// SecurityError. The stores and the API client must still load and work,
// falling back to their defaults and keeping values for this page load.

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/api/themes', () => ({ fetchThemes: vi.fn(() => Promise.resolve([])) }));

const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');

beforeEach(() => {
	vi.resetModules();
	Object.defineProperty(globalThis, 'localStorage', {
		configurable: true,
		get() {
			throw new DOMException('The operation is insecure.', 'SecurityError');
		}
	});
	document.documentElement.classList.remove('dark');
});

afterEach(() => {
	if (original) Object.defineProperty(globalThis, 'localStorage', original);
});

describe('with site storage blocked', () => {
	it('the theme store loads with the OS preference and toggles', async () => {
		const { theme, toggleTheme } = await import('../theme');
		expect(get(theme)).toBe('light');
		toggleTheme();
		expect(get(theme)).toBe('dark');
		expect(document.documentElement.classList.contains('dark')).toBe(true);
	});

	it('the color scheme store loads with the default scheme and switches', async () => {
		const { colorScheme } = await import('../color-scheme');
		const { DEFAULT_SCHEME, COLOR_SCHEMES } = await import('$lib/themes/builtin-schemes');
		expect(get(colorScheme)).toBe(DEFAULT_SCHEME.id);
		const other = COLOR_SCHEMES.find((s) => s.id !== DEFAULT_SCHEME.id && !s.mode)!;
		colorScheme.set(other.id);
		expect(document.documentElement.dataset.scheme).toBe(other.id);
	});

	it('applying an unlocked scheme follows the OS preference', async () => {
		const { applySchemeToDocument } = await import('$lib/themes/apply-scheme');
		const { DEFAULT_SCHEME } = await import('$lib/themes/builtin-schemes');
		expect(() => applySchemeToDocument(DEFAULT_SCHEME, '')).not.toThrow();
		expect(document.documentElement.classList.contains('dark')).toBe(false);
	});

	it('the API token lasts for this page load', async () => {
		const { getToken, setToken, clearToken } = await import('$lib/api/client');
		expect(getToken()).toBeNull();
		setToken('tok');
		expect(getToken()).toBe('tok');
		clearToken();
		expect(getToken()).toBeNull();
	});

	it('the signed-in role lasts for this page load', async () => {
		const { applyLogin, logoutLocal, persistedRole, role } = await import('../auth');
		applyLogin({ access_token: 'tok', expires_at: '', password_must_change: false, role: 'admin' });
		expect(persistedRole()).toBe('admin');
		expect(get(role)).toBe('admin');
		logoutLocal();
		expect(persistedRole()).toBeNull();
	});
});
