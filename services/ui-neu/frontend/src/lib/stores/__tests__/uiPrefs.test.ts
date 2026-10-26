import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

beforeEach(() => {
	localStorage.clear();
	vi.resetModules();
});

describe('uiPrefs store', () => {
	it('defaults to stats on and card view', async () => {
		const { uiPrefs } = await import('../uiPrefs');
		expect(get(uiPrefs)).toEqual({ showStats: true, dashboardView: 'card', logWrap: true });
	});

	it('persists changes and reads them back on a fresh load', async () => {
		const { setUiPref } = await import('../uiPrefs');
		setUiPref('showStats', false);
		setUiPref('dashboardView', 'table');
		setUiPref('logWrap', false);
		expect(JSON.parse(localStorage.getItem('arm_ui_prefs')!)).toEqual({
			showStats: false,
			dashboardView: 'table',
			logWrap: false
		});
		vi.resetModules();
		const fresh = await import('../uiPrefs');
		expect(get(fresh.uiPrefs)).toEqual({ showStats: false, dashboardView: 'table', logWrap: false });
	});

	it('falls back to defaults on corrupt or partial storage', async () => {
		localStorage.setItem('arm_ui_prefs', '{not json');
		let mod = await import('../uiPrefs');
		expect(get(mod.uiPrefs)).toEqual({ showStats: true, dashboardView: 'card', logWrap: true });
		vi.resetModules();
		localStorage.setItem('arm_ui_prefs', JSON.stringify({ dashboardView: 'bogus', showStats: 'yes', logWrap: 'no' }));
		mod = await import('../uiPrefs');
		expect(get(mod.uiPrefs)).toEqual({ showStats: true, dashboardView: 'card', logWrap: true });
	});
});
