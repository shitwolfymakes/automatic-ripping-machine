// The schema config form's API key checks (Settings > Metadata > API
// keys): each field's running flag and its last result.
import type { KeyCheckResponse } from '$lib/types/api.gen';
import { checkApiKey } from '$lib/api/settings';
import { HIDDEN_SECRET } from '$lib/api/config';
import { KEY_CHECK_NAMES } from '$lib/utils/settings-sections';
import { errorMessage } from '$lib/utils/errors';

/**
 * The key a check sends: the field's value when the operator typed a new
 * one, or undefined, so the backend checks the saved key, for a value
 * that isn't a string, is empty or masked, or equals the saved one.
 */
export function keyToTest(value: unknown, saved: unknown): string | undefined {
	if (typeof value !== 'string' || value === '' || value === HIDDEN_SECRET) return undefined;
	if (value === saved) return undefined;
	return value;
}

export class KeyChecks {
	/** Fields whose check is running, by field key. */
	running = $state<Record<string, boolean>>({});
	/** Each field's last check result, by field key. */
	results = $state<Record<string, KeyCheckResponse | null>>({});

	/**
	 * Checks the field's key with its service, sending `key` when given.
	 * Does nothing for a field with no key check.
	 */
	run = async (fieldKey: string, key: string | undefined): Promise<void> => {
		const name = KEY_CHECK_NAMES[fieldKey];
		if (!name) return;
		this.running = { ...this.running, [fieldKey]: true };
		try {
			const result = await checkApiKey(name, key);
			this.results = { ...this.results, [fieldKey]: result };
		} catch (e) {
			this.results = {
				...this.results,
				[fieldKey]: {
					name,
					status: 'error',
					detail: errorMessage(e, 'check failed'),
					checked_at: null
				}
			};
		} finally {
			this.running = { ...this.running, [fieldKey]: false };
		}
	};
}
