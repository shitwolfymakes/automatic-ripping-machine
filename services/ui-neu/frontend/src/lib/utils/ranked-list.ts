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

/** Which way a move takes an entry: up a rank or down one. */
export type RankDirection = 'up' | 'down';

/** The entries switched on: known and without repeats, in rank order. */
export function rankedSelected(value: unknown, known: readonly string[]): string[] {
	return Array.isArray(value)
		? (value as string[]).filter((v, i, all) => known.includes(v) && all.indexOf(v) === i)
		: [];
}

/** The entries switched on, then the rest of the known entries. */
export function rankedRows(selected: readonly string[], known: readonly string[]): string[] {
	return [...selected, ...known.filter((v) => !selected.includes(v))];
}

/** The list with `value` swapped with its neighbour in `dir`, or null when
 *  `value` is not on the list or is already at that end. */
export function swapRank(selected: readonly string[], value: string, dir: RankDirection): string[] | null {
	const i = selected.indexOf(value);
	const j = dir === 'up' ? i - 1 : i + 1;
	if (i < 0 || j < 0 || j >= selected.length) return null;
	const next = [...selected];
	[next[i], next[j]] = [next[j], next[i]];
	return next;
}
