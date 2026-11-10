// What a schema config field shows when it can't be edited.
import type { ConfigFieldMeta } from '$lib/types/api.gen';

/** The text a read-only field shows: True or False for a bool, a ranked
 * list's values by their labels joined with ", ", or any other value as
 * it is. An empty list, or a missing value, shows "-". */
export function readOnlyValue(field: ConfigFieldMeta, value: unknown): string {
	if (field.type === 'bool') return value ? 'True' : 'False';
	if (field.type === 'ranked') {
		return (Array.isArray(value) ? (value as string[]) : []).map((v) => field.enum_labels?.[v] ?? v).join(', ') || '-';
	}
	return String(value ?? '-');
}
