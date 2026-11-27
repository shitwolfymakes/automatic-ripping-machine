// The Settings page's loaded settings: the data, its loading and error
// state, and the writes that keep it in step with what the forms save.
import { SvelteMap } from 'svelte/reactivity';
import { fetchSettings, saveArmConfig } from '$lib/api/settings';
import type { SettingsData } from '$lib/api/settings';
import { foldSavedConfig } from '$lib/settings/sections';

export class LoadedSettings {
	settings = $state<SettingsData | null>(null);
	loading = $state(true);
	error = $state<Error | null>(null);
	savingKeys = $state<string[]>([]);

	load = async (): Promise<void> => {
		this.loading = true;
		this.error = null;
		try {
			this.settings = await fetchSettings();
		} catch (e) {
			this.error = e instanceof Error ? e : new Error('Failed to load settings');
		} finally {
			this.loading = false;
		}
	};

	isSaving = (key: string): boolean => this.savingKeys.includes(key);

	// The latest value of a key changed while its save was in flight, saved
	// once that save settles.
	#queued = new SvelteMap<string, unknown>();

	// A setting that saves on change (no Save button), such as the notifications
	// master switch or a Defaults choice: settings.config takes the value at once
	// so the page follows it, and the key is PATCHed alone. A change made while
	// the key is saving is queued and only the latest goes out after; a failed
	// last save rolls config back to the last value the server took.
	saveSetting = async (key: string, value: unknown): Promise<void> => {
		if (!this.settings) return;
		const saved = (this.settings.config as Record<string, unknown> | undefined)?.[key] ?? false;
		this.#setConfig(key, value);
		if (this.isSaving(key)) {
			this.#queued.set(key, value);
			return;
		}
		this.savingKeys = [...this.savingKeys, key];
		await this.#saveLatest(key, value, saved);
		this.savingKeys = this.savingKeys.filter((k) => k !== key);
	};

	async #saveLatest(key: string, value: unknown, saved: unknown): Promise<void> {
		let next = value;
		let lastSaved = saved;
		for (;;) {
			const ok = await saveArmConfig({ [key]: next }).then(
				() => true,
				() => false
			);
			if (ok) lastSaved = next;
			if (!this.#queued.has(key)) {
				if (!ok) this.#setConfig(key, lastSaved);
				return;
			}
			next = this.#queued.get(key);
			this.#queued.delete(key);
		}
	}

	// An on/off setting: a save of the boolean.
	toggleSetting = (key: string, next: boolean): Promise<void> => this.saveSetting(key, next);

	// Only called once settings have loaded, and they are never cleared after that.
	#setConfig(key: string, value: unknown): void {
		const settings = this.settings as SettingsData;
		this.settings = { ...settings, config: { ...settings.config, [key]: value } };
	}

	// A form's saved values are folded back into `settings.config`, so every
	// other tab sees them: the Identity card's "Needs ... key" chip reads the
	// keys from it, and a form diffs its next save against it.
	foldSaved = (payload: Record<string, unknown>): void => {
		if (!this.settings) return;
		this.settings = foldSavedConfig(this.settings, payload);
	};
}
