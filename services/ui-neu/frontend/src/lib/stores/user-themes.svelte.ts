// The Settings page's user themes: deleting one and the feedback line it
// leaves behind.
import { get } from 'svelte/store';
import { colorScheme, loadThemesFromApi } from '$lib/stores/color-scheme';
import { deleteTheme as deleteThemeApi } from '$lib/api/themes';
import { errorMessage } from '$lib/utils/errors';

export class UserThemes {
	feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	deleteTheme = async (id: string, label: string): Promise<void> => {
		if (!confirm(`Delete user theme "${label}"?`)) return;
		this.feedback = null;
		try {
			await deleteThemeApi(id);
			await loadThemesFromApi();
			if (get(colorScheme) === id) colorScheme.set('blue');
			this.feedback = { type: 'success', message: `Theme "${label}" deleted` };
		} catch (e) {
			this.feedback = { type: 'error', message: errorMessage(e, 'Delete failed') };
		}
	};
}
