import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const deleteThemeMock = vi.fn();
vi.mock('$lib/api/themes', () => ({
	deleteTheme: (...a: unknown[]) => deleteThemeMock(...a)
}));

const loadThemesMock = vi.fn();
vi.mock('$lib/stores/color-scheme', async () => {
	const { writable } = await import('svelte/store');
	return { colorScheme: writable('blue'), loadThemesFromApi: (...a: unknown[]) => loadThemesMock(...a) };
});

import { get } from 'svelte/store';
import { colorScheme } from '$lib/stores/color-scheme';
import { UserThemes } from '$lib/stores/user-themes.svelte';

let confirmSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
	deleteThemeMock.mockReset().mockResolvedValue(undefined);
	loadThemesMock.mockReset().mockResolvedValue(undefined);
	colorScheme.set('blue');
	confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
});

afterEach(() => {
	confirmSpy.mockRestore();
});

describe('UserThemes', () => {
	it('starts without feedback', () => {
		expect(new UserThemes().feedback).toBeNull();
	});

	it('does nothing when the confirmation is declined', async () => {
		confirmSpy.mockReturnValue(false);
		const themes = new UserThemes();
		themes.feedback = { type: 'error', message: 'old' };
		await themes.deleteTheme('t1', 'Mine');
		expect(confirmSpy).toHaveBeenCalledWith('Delete user theme "Mine"?');
		expect(deleteThemeMock).not.toHaveBeenCalled();
		expect(themes.feedback).toEqual({ type: 'error', message: 'old' });
	});

	it('resets the scheme to blue when the deleted theme was selected', async () => {
		colorScheme.set('t1');
		const themes = new UserThemes();
		await themes.deleteTheme('t1', 'Mine');
		expect(deleteThemeMock).toHaveBeenCalledWith('t1');
		expect(loadThemesMock).toHaveBeenCalled();
		expect(get(colorScheme)).toBe('blue');
		expect(themes.feedback).toEqual({ type: 'success', message: 'Theme "Mine" deleted' });
	});

	it('keeps the scheme when another theme is deleted', async () => {
		colorScheme.set('t2');
		const themes = new UserThemes();
		await themes.deleteTheme('t1', 'Mine');
		expect(get(colorScheme)).toBe('t2');
		expect(themes.feedback).toEqual({ type: 'success', message: 'Theme "Mine" deleted' });
	});

	it('clears an earlier feedback while the delete runs', async () => {
		let release!: () => void;
		deleteThemeMock.mockReturnValue(new Promise<void>((r) => (release = r)));
		const themes = new UserThemes();
		themes.feedback = { type: 'error', message: 'old' };
		const pending = themes.deleteTheme('t1', 'Mine');
		expect(themes.feedback).toBeNull();
		release();
		await pending;
	});

	it('shows the error message when the delete fails with an Error', async () => {
		deleteThemeMock.mockRejectedValue(new Error('nope'));
		const themes = new UserThemes();
		await themes.deleteTheme('t1', 'Mine');
		expect(themes.feedback).toEqual({ type: 'error', message: 'nope' });
	});

	it('shows a fallback message when the delete fails with a non-Error', async () => {
		deleteThemeMock.mockRejectedValue('boom');
		const themes = new UserThemes();
		await themes.deleteTheme('t1', 'Mine');
		expect(themes.feedback).toEqual({ type: 'error', message: 'Delete failed' });
	});

	it('shows the error and keeps the scheme when the reload fails', async () => {
		colorScheme.set('t1');
		loadThemesMock.mockRejectedValue(new Error('reload failed'));
		const themes = new UserThemes();
		await themes.deleteTheme('t1', 'Mine');
		expect(get(colorScheme)).toBe('t1');
		expect(themes.feedback).toEqual({ type: 'error', message: 'reload failed' });
	});
});
