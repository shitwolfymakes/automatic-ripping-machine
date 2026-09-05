import { writable } from 'svelte/store';
import { browser } from '$app/environment';

/** Per-browser interface preferences (Settings > Interface). These describe
 *  this device, not the server, so they live in localStorage rather than
 *  Config. Every field has a default so a missing or corrupt entry is fine. */
export interface UiPrefs {
	/** Resource stats surface: sidebar panel (2xl) / bottom bar (lg). */
	showStats: boolean;
	/** Dashboard job list layout the page opens with. */
	dashboardView: 'card' | 'table';
}

const KEY = 'arm_ui_prefs';
const DEFAULTS: UiPrefs = { showStats: true, dashboardView: 'card' };

function load(): UiPrefs {
	if (!browser) return { ...DEFAULTS };
	try {
		const raw = localStorage.getItem(KEY);
		if (!raw) return { ...DEFAULTS };
		const parsed = JSON.parse(raw) as Partial<UiPrefs>;
		return {
			showStats: typeof parsed.showStats === 'boolean' ? parsed.showStats : DEFAULTS.showStats,
			dashboardView: parsed.dashboardView === 'table' ? 'table' : DEFAULTS.dashboardView
		};
	} catch {
		return { ...DEFAULTS };
	}
}

export const uiPrefs = writable<UiPrefs>(load());

if (browser) {
	uiPrefs.subscribe((value) => {
		try {
			localStorage.setItem(KEY, JSON.stringify(value));
		} catch {
			/* storage unavailable: the preference lasts for this page load */
		}
	});
}

export function setUiPref<K extends keyof UiPrefs>(key: K, value: UiPrefs[K]): void {
	uiPrefs.update((p) => ({ ...p, [key]: value }));
}
