// The rules behind a ranked source list in Settings: which entries are on, in
// what order, and the API key an entry still needs.
import type { ConfigFieldMeta } from '$lib/types/api.gen';

/** The config key an entry needs and does not have yet, or null when it needs
 *  none or the key is set. */
export function missingKey(field: ConfigFieldMeta, config: Record<string, unknown>, value: string): string | null {
	const key = field.enum_requires?.[value];
	if (!key) return null;
	const current = config[key];
	return typeof current === 'string' && current.trim() !== '' ? null : key;
}
