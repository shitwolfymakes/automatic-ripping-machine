import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/settings', () => ({
	fetchSettings: vi.fn(),
	saveArmConfig: vi.fn()
}));

import { fetchSettings, saveArmConfig } from '$lib/api/settings';
import type { SettingsData } from '$lib/api/settings';
import { LoadedSettings } from '../loadedSettings.svelte';

const mockFetch = vi.mocked(fetchSettings);
const mockSave = vi.mocked(saveArmConfig);

function settingsData(config: Record<string, unknown> = {}): SettingsData {
	return {
		config,
		schema: { groups: [{ name: 'Keys', fields: [{ key: 'tmdb_api_key', tier: 'secret' }] }] },
		infra: {},
		arm_config: {}
	} as unknown as SettingsData;
}

async function loadedWith(config: Record<string, unknown> = {}) {
	mockFetch.mockResolvedValue(settingsData(config));
	const loaded = new LoadedSettings();
	await loaded.load();
	return loaded;
}

beforeEach(() => {
	vi.resetAllMocks();
});

describe('LoadedSettings', () => {
	it('starts with no settings, loading and no error', () => {
		const loaded = new LoadedSettings();
		expect(loaded.settings).toBeNull();
		expect(loaded.loading).toBe(true);
		expect(loaded.error).toBeNull();
		expect(loaded.isSaving('notifications_enabled')).toBe(false);
	});

	describe('load', () => {
		it('stores the fetched settings and stops loading', async () => {
			const data = settingsData({ a: 1 });
			mockFetch.mockResolvedValue(data);
			const loaded = new LoadedSettings();
			await loaded.load();
			expect(loaded.settings).toEqual(data);
			expect(loaded.loading).toBe(false);
			expect(loaded.error).toBeNull();
		});

		it('keeps an Error from the fetch', async () => {
			const err = new Error('boom');
			mockFetch.mockRejectedValue(err);
			const loaded = new LoadedSettings();
			await loaded.load();
			expect(loaded.error).toBe(err);
			expect(loaded.settings).toBeNull();
			expect(loaded.loading).toBe(false);
		});

		it('wraps a non-Error rejection as Failed to load settings', async () => {
			mockFetch.mockRejectedValue('nope');
			const loaded = new LoadedSettings();
			await loaded.load();
			expect(loaded.error).toBeInstanceOf(Error);
			expect(loaded.error?.message).toBe('Failed to load settings');
		});

		it('clears an earlier error and shows loading while it fetches', async () => {
			mockFetch.mockRejectedValueOnce(new Error('first'));
			const loaded = new LoadedSettings();
			await loaded.load();
			expect(loaded.error).not.toBeNull();

			let resolve!: (v: SettingsData) => void;
			mockFetch.mockReturnValueOnce(new Promise<SettingsData>((r) => (resolve = r)));
			const pending = loaded.load();
			expect(loaded.error).toBeNull();
			expect(loaded.loading).toBe(true);
			resolve(settingsData());
			await pending;
			expect(loaded.loading).toBe(false);
			expect(loaded.error).toBeNull();
		});
	});

	describe('foldSaved', () => {
		it('does nothing when no settings are loaded', () => {
			const loaded = new LoadedSettings();
			loaded.foldSaved({ a: 1 });
			expect(loaded.settings).toBeNull();
		});

		it('folds the saved values into config and masks a secret', async () => {
			const loaded = await loadedWith({ keep: 'x' });
			loaded.foldSaved({ a: 1, tmdb_api_key: 'secret' });
			expect(loaded.settings?.config).toEqual({ keep: 'x', a: 1, tmdb_api_key: '<hidden>' });
		});
	});

	describe('saveSetting', () => {
		it('saves a string value, showing it at once, and rolls it back when the save fails', async () => {
			const loaded = await loadedWith({ miss_media_type: 'movie' });
			mockSave.mockRejectedValueOnce(new Error('fail'));
			const failing = loaded.saveSetting('miss_media_type', 'tv');
			expect(loaded.settings?.config.miss_media_type).toBe('tv');
			await failing;
			expect(mockSave).toHaveBeenCalledWith({ miss_media_type: 'tv' });
			expect(loaded.settings?.config.miss_media_type).toBe('movie');
			mockSave.mockResolvedValueOnce(undefined as never);
			await loaded.saveSetting('miss_media_type', 'tv');
			expect(loaded.settings?.config.miss_media_type).toBe('tv');
			expect(loaded.isSaving('miss_media_type')).toBe(false);
		});
	});

	describe('toggleSetting', () => {
		const KEY = 'notifications_enabled';

		it('sends nothing when no settings are loaded', async () => {
			const loaded = new LoadedSettings();
			await loaded.toggleSetting(KEY, true);
			expect(mockSave).not.toHaveBeenCalled();
			expect(loaded.isSaving(KEY)).toBe(false);
		});

		it('saves on, showing the new value and the key as saving while pending', async () => {
			const loaded = await loadedWith({ notifications_enabled: false });
			let resolve!: () => void;
			mockSave.mockReturnValue(new Promise<never>((r) => (resolve = r as () => void)));
			const pending = loaded.toggleSetting(KEY, true);
			expect(loaded.settings?.config.notifications_enabled).toBe(true);
			expect(loaded.isSaving(KEY)).toBe(true);
			resolve();
			await pending;
			expect(mockSave).toHaveBeenCalledWith({ notifications_enabled: true });
			expect(loaded.settings?.config.notifications_enabled).toBe(true);
			expect(loaded.isSaving(KEY)).toBe(false);
		});

		it('saves off', async () => {
			const loaded = await loadedWith({ notifications_enabled: true });
			mockSave.mockResolvedValue(undefined as never);
			await loaded.toggleSetting(KEY, false);
			expect(mockSave).toHaveBeenCalledWith({ notifications_enabled: false });
			expect(loaded.settings?.config.notifications_enabled).toBe(false);
		});

		it('rolls back to the previous value when the save fails', async () => {
			const loaded = await loadedWith({ notifications_enabled: true });
			mockSave.mockRejectedValue(new Error('fail'));
			await loaded.toggleSetting(KEY, false);
			expect(loaded.settings?.config.notifications_enabled).toBe(true);
			expect(loaded.isSaving(KEY)).toBe(false);
		});

		it('rolls back to off when the config had no value', async () => {
			const loaded = await loadedWith({});
			mockSave.mockRejectedValue(new Error('fail'));
			await loaded.toggleSetting(KEY, true);
			expect(loaded.settings?.config.notifications_enabled).toBe(false);
		});

		it('ignores a second call for the same key while its save is in flight', async () => {
			const loaded = await loadedWith({ notifications_enabled: false });
			let resolve!: () => void;
			mockSave.mockReturnValue(new Promise<never>((r) => (resolve = r as () => void)));
			const first = loaded.toggleSetting(KEY, true);
			await loaded.toggleSetting(KEY, false);
			expect(mockSave).toHaveBeenCalledTimes(1);
			expect(loaded.settings?.config.notifications_enabled).toBe(true);
			resolve();
			await first;
		});

		it('saves another key while one is in flight', async () => {
			const loaded = await loadedWith({ notifications_enabled: false, auto_transcode_on_idle: false });
			let resolve!: () => void;
			mockSave.mockReturnValueOnce(new Promise<never>((r) => (resolve = r as () => void)));
			mockSave.mockResolvedValueOnce(undefined as never);
			const first = loaded.toggleSetting(KEY, true);
			await loaded.toggleSetting('auto_transcode_on_idle', true);
			expect(mockSave).toHaveBeenLastCalledWith({ auto_transcode_on_idle: true });
			expect(loaded.isSaving('auto_transcode_on_idle')).toBe(false);
			expect(loaded.isSaving(KEY)).toBe(true);
			resolve();
			await first;
		});
	});
});
