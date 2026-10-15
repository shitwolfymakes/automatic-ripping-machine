import type { ConfigFieldMeta } from '$lib/types/api.gen';
import type { RecipeCell } from '$lib/components/sessions/RecipeStrip.svelte';

/** Pure helpers behind Settings › Identification › Identity: the summary strip
 *  text per disc kind and the two Advanced "Ignore" boxes over
 *  `disc_hint_sources` (set semantics, default order on re-enable). */

export type DiscKind = 'bluray' | 'dvd' | 'cd';
export type DiscHint = 'bd_title' | 'label';

export const DISC_KIND_LABELS: Record<DiscKind, string> = { bluray: 'Blu-ray', dvd: 'DVD', cd: 'CD' };
export const HINT_LABELS = { bd_title: 'Disc title metadata', label: 'Volume label' } as const;
export const HINT_DEFAULT_ORDER = ['bd_title', 'label'] as const;

const DISC_DB_LABELS = {
	thediscdb_enabled: 'TheDiscDB disc map',
	crc64service_enabled: 'ARM community database (CRC64)'
} as const;
const NO_SOURCES = 'No sources on';
const SEP = ' · ';

function hintList(values: Record<string, unknown>): string[] {
	const v = values.disc_hint_sources;
	return Array.isArray(v) ? (v as string[]) : [...HINT_DEFAULT_ORDER];
}

export function hintIgnored(values: Record<string, unknown>, hint: DiscHint): boolean {
	return !hintList(values).includes(hint);
}

/** Returns the new disc_hint_sources with `hint` present (ignored=false) or absent, keeping the other entry and the default order. */
export function withHintIgnored(values: Record<string, unknown>, hint: DiscHint, ignored: boolean): string[] {
	const current = hintList(values);
	if (ignored) return current.filter((h) => h !== hint);
	const present = new Set([...current, hint]);
	return HINT_DEFAULT_ORDER.filter((h) => present.has(h));
}

/** The labels (`enum_labels`) of the entries switched on in a ranked list, in rank order. */
export function enabledLabels(values: Record<string, unknown>, key: string, fields: ConfigFieldMeta[]): string[] {
	const v = values[key];
	if (!Array.isArray(v)) return [];
	const labels = fields.find((f) => f.key === key)?.enum_labels;
	return (v as string[]).map((s) => labels?.[s] ?? s);
}

const sources = (values: Record<string, unknown>, key: string, fields: ConfigFieldMeta[]) =>
	enabledLabels(values, key, fields).join(', ') || NO_SOURCES;
const trust = (values: Record<string, unknown>, key: string) =>
	values[key] ? 'Apply confident matches' : 'Waits for review';

function discCell(kind: DiscKind, values: Record<string, unknown>): RecipeCell {
	const label = 'On the disc';
	const on = (h: DiscHint) => !hintIgnored(values, h);
	if (kind === 'cd') {
		const parts = [...(on('label') ? [HINT_LABELS.label] : []), 'Disc ID (track layout)'];
		return { label, value: parts.join(', '), sub: 'CD-TEXT planned' };
	}
	const kindHints: readonly DiscHint[] = kind === 'bluray' ? HINT_DEFAULT_ORDER : ['label'];
	const shown = hintList(values).filter((h): h is DiscHint => (kindHints as string[]).includes(h));
	if (shown.length === 0) return { label, value: 'Disc text ignored', sub: 'See Advanced' };
	return { label, value: shown.map((h) => HINT_LABELS[h]).join(', '), sub: 'ARM reads all of these' };
}

function databaseCell(kind: DiscKind, values: Record<string, unknown>): RecipeCell {
	const label = 'Disc database';
	if (kind === 'cd') return { label, value: 'Not used for CDs' };
	const keys =
		kind === 'dvd' ? (['thediscdb_enabled', 'crc64service_enabled'] as const) : (['thediscdb_enabled'] as const);
	const on = keys.filter((k) => Boolean(values[k])).map((k) => DISC_DB_LABELS[k]);
	return { label, value: on.join(', ') || 'Off', sub: "A match wins over the disc's labels" };
}

/** The summary strip's four cells for one disc kind, derived live from the form's values. */
export function stripCells(kind: DiscKind, values: Record<string, unknown>, fields: ConfigFieldMeta[]): RecipeCell[] {
	const lookup =
		kind === 'cd'
			? `Music: ${sources(values, 'music_sources', fields)}`
			: `Movies: ${sources(values, 'movie_sources', fields)}${SEP}TV shows: ${sources(values, 'episode_sources', fields)}`;
	const trusted =
		kind === 'cd'
			? `Music: ${trust(values, 'music_auto_apply')}`
			: `Movies: ${trust(values, 'movie_auto_apply')}${SEP}TV shows: ${trust(values, 'episode_auto_apply')}`;
	return [
		discCell(kind, values),
		databaseCell(kind, values),
		{ label: 'Online lookup', value: lookup, sub: 'Tried top to bottom; the first confident match wins' },
		{ label: 'Trust', value: trusted, sub: 'Others wait for review on the job page' }
	];
}
