import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/settings', () => ({
	fetchSettings: vi.fn(),
	saveArmConfig: vi.fn()
}));

import { fetchSettings, saveArmConfig } from '$lib/api/settings';
import type { SettingsData } from '$lib/api/settings';
import { LoadedSettings } from '../loaded-settings.svelte';

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
		expect(loaded.notifSaving).toBe(false);
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

	describe('toggleNotifications', () => {
		it('sends nothing when no settings are loaded', async () => {
			const loaded = new LoadedSettings();
			await loaded.toggleNotifications(true);
			expect(mockSave).not.toHaveBeenCalled();
			expect(loaded.notifSaving).toBe(false);
		});

		it('saves on, showing the new value and notifSaving while pending', async () => {
			const loaded = await loadedWith({ notifications_enabled: false });
			let resolve!: () => void;
			mockSave.mockReturnValue(new Promise<never>((r) => (resolve = r as () => void)));
			const pending = loaded.toggleNotifications(true);
			expect(loaded.settings?.config.notifications_enabled).toBe(true);
			expect(loaded.notifSaving).toBe(true);
			resolve();
			await pending;
			expect(mockSave).toHaveBeenCalledWith({ notifications_enabled: true });
			expect(loaded.settings?.config.notifications_enabled).toBe(true);
			expect(loaded.notifSaving).toBe(false);
		});

		it('saves off', async () => {
			const loaded = await loadedWith({ notifications_enabled: true });
			mockSave.mockResolvedValue(undefined as never);
			await loaded.toggleNotifications(false);
			expect(mockSave).toHaveBeenCalledWith({ notifications_enabled: false });
			expect(loaded.settings?.config.notifications_enabled).toBe(false);
		});

		it('rolls back to the previous value when the save fails', async () => {
			const loaded = await loadedWith({ notifications_enabled: true });
			mockSave.mockRejectedValue(new Error('fail'));
			await loaded.toggleNotifications(false);
			expect(loaded.settings?.config.notifications_enabled).toBe(true);
			expect(loaded.notifSaving).toBe(false);
		});

		it('rolls back to off when the config had no value', async () => {
			const loaded = await loadedWith({});
			mockSave.mockRejectedValue(new Error('fail'));
			await loaded.toggleNotifications(true);
			expect(loaded.settings?.config.notifications_enabled).toBe(false);
		});

		it('ignores a second call while a save is in flight', async () => {
			const loaded = await loadedWith({ notifications_enabled: false });
			let resolve!: () => void;
			mockSave.mockReturnValue(new Promise<never>((r) => (resolve = r as () => void)));
			const first = loaded.toggleNotifications(true);
			await loaded.toggleNotifications(false);
			expect(mockSave).toHaveBeenCalledTimes(1);
			expect(loaded.settings?.config.notifications_enabled).toBe(true);
			resolve();
			await first;
		});
	});
});
