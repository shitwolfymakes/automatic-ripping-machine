// The Settings page's loaded settings: the data, its loading and error
// state, and the writes that keep it in step with what the forms save.
import { fetchSettings, saveArmConfig } from '$lib/api/settings';
import type { SettingsData } from '$lib/api/settings';
import { foldSavedConfig } from '$lib/utils/settings-sections';

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

	// An on/off setting that saves on change (no Save button), such as the
	// notifications master switch: settings.config flips at once so the page
	// follows it, the key is PATCHed alone, and a failed save rolls it back.
	toggleSetting = async (key: string, next: boolean): Promise<void> => {
		if (!this.settings || this.isSaving(key)) return;
		const prev = Boolean((this.settings.config as Record<string, unknown> | undefined)?.[key]);
		this.#setConfig(key, next);
		this.savingKeys = [...this.savingKeys, key];
		try {
			await saveArmConfig({ [key]: next });
		} catch {
			this.#setConfig(key, prev);
		} finally {
			this.savingKeys = this.savingKeys.filter((k) => k !== key);
		}
	};

	#setConfig(key: string, value: boolean): void {
		if (!this.settings) return;
		this.settings = { ...this.settings, config: { ...this.settings.config, [key]: value } };
	}

	// A form's saved values are folded back into `settings.config`, so every
	// other tab sees them: the Identity card's "Needs ... key" chip reads the
	// keys from it, and a form diffs its next save against it.
	foldSaved = (payload: Record<string, unknown>): void => {
		if (!this.settings) return;
		this.settings = foldSavedConfig(this.settings, payload);
	};
}
