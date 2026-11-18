// The Settings page's loaded settings: the data, its loading and error
// state, and the writes that keep it in step with what the forms save.
import { fetchSettings, saveArmConfig } from '$lib/api/settings';
import type { SettingsData } from '$lib/api/settings';
import { foldSavedConfig } from '$lib/settings/sections';

export class LoadedSettings {
	settings = $state<SettingsData | null>(null);
	loading = $state(true);
	error = $state<Error | null>(null);
	notifSaving = $state(false);

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

	// The notifications master toggle auto-saves on change (no Save button): PATCH
	// immediately, optimistically flip settings.config so the channels UI shows/
	// hides at once, and roll back on failure.
	toggleNotifications = async (next: boolean): Promise<void> => {
		if (!this.settings || this.notifSaving) return;
		const prev = Boolean(this.settings.config?.notifications_enabled);
		this.settings = { ...this.settings, config: { ...this.settings.config, notifications_enabled: next } };
		this.notifSaving = true;
		try {
			await saveArmConfig({ notifications_enabled: next });
		} catch {
			this.settings = { ...this.settings, config: { ...this.settings.config, notifications_enabled: prev } };
		} finally {
			this.notifSaving = false;
		}
	};

	// A form's saved values are folded back into `settings.config`, so every
	// other tab sees them: the Identity card's "Needs ... key" chip reads the
	// keys from it, and a form diffs its next save against it.
	foldSaved = (payload: Record<string, unknown>): void => {
		if (!this.settings) return;
		this.settings = foldSavedConfig(this.settings, payload);
	};
}
