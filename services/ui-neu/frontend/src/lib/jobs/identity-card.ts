import type { ConfigFieldMeta } from '$lib/types/api.gen';

/** Pure helpers behind Settings › Identification › Identity: the Preview panel
 *  rows per disc kind, the two Advanced "Ignore" boxes over
 *  `disc_hint_sources` (set semantics, default order on re-enable), and the
 *  tables that drive the card's numbered steps (disc databases, source lists,
 *  trust boxes). */

export type DiscKind = 'bluray' | 'dvd' | 'cd';
export type DiscHint = 'bd_title' | 'label';

export const DISC_KIND_LABELS: Record<DiscKind, string> = { bluray: 'Blu-ray', dvd: 'DVD', cd: 'CD' };
export const HINT_LABELS = { bd_title: 'Disc title metadata', label: 'Volume label' } as const;
export const HINT_DEFAULT_ORDER = ['bd_title', 'label'] as const;

/** The Preview's disc-kind control: the kinds it offers, in order. */
export const DISC_KINDS: readonly DiscKind[] = ['bluray', 'dvd', 'cd'];

export interface DiscDatabaseOption {
	key: string;
	label: string;
	chips: string[];
	description: string | null;
}
/** Step 2's disc databases: one checkbox row each. */
export const DISC_DATABASES: DiscDatabaseOption[] = [
	{
		key: 'thediscdb_enabled',
		label: 'TheDiscDB disc map',
		chips: ['Blu-ray', 'UHD', 'DVD'],
		description:
			"Matches the disc itself and names its titles before any online lookup. When it matches, it wins over the disc's labels, and ARM confirms the title with the first online source below."
	},
	{ key: 'crc64service_enabled', label: 'ARM community database (CRC64)', chips: ['DVD'], description: null }
];

/** Step 3's source lists: one ranked list per media kind. */
export const SOURCE_LISTS: { key: string; heading: string }[] = [
	{ key: 'movie_sources', heading: 'Movies' },
	{ key: 'episode_sources', heading: 'TV shows' }
];

/** Step 4's trust boxes: one auto-apply checkbox per media kind. */
export const TRUST_OPTIONS: { key: string; label: string }[] = [
	{ key: 'movie_auto_apply', label: 'Apply confident matches · Movies' },
	{ key: 'episode_auto_apply', label: 'Apply confident matches · TV shows' },
	{ key: 'music_auto_apply', label: 'Apply confident matches · Music' }
];

/** The Advanced ignore boxes: one per disc hint the card can switch off. */
export const IGNORE_OPTIONS: { hint: DiscHint; label: string; help: string }[] = [
	{
		hint: 'bd_title',
		label: 'Ignore the disc title metadata',
		help: "Blu-ray and UHD only. ARM won't use the title stored on the disc and identifies it from the volume label, TheDiscDB and online lookup instead."
	},
	{
		hint: 'label',
		label: 'Ignore the volume label',
		help: "ARM won't use the volume label and identifies the disc from its title metadata, TheDiscDB and online lookup instead. A DVD with no title metadata then gets no automatic title search."
	}
];

/** Step 3's "No sources on" note: true when the list at `key` is an empty array. */
export function isEmptyList(values: Record<string, unknown>, key: string): boolean {
	return Array.isArray(values[key]) && (values[key] as unknown[]).length === 0;
}

const NO_SOURCES = 'No sources on';

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

export interface PreviewSource {
	rank: number;
	label: string;
}
export interface PreviewRow {
	key: 'disc' | 'movie' | 'tv' | 'music';
	label: 'Disc' | 'Movies' | 'TV shows' | 'Music';
	sentence?: string;
	sources?: PreviewSource[];
	empty?: string;
	trust?: 'Applies confident matches' | 'Waits for review';
}

const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
const sentenceCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const joinAnd = (parts: string[]) => parts.join(' and ');

/** The Disc row: the disc's own hints this kind reads, then the disc databases switched on for it. */
function discSentence(kind: DiscKind, values: Record<string, unknown>): string {
	if (kind === 'cd') {
		const parts = [...(hintIgnored(values, 'label') ? [] : [HINT_LABELS.label]), 'Disc ID (track layout)'];
		return sentenceCase(joinAnd(parts.map(lowerFirst)));
	}
	const kindHints: readonly DiscHint[] = kind === 'bluray' ? HINT_DEFAULT_ORDER : ['label'];
	const shown = hintList(values).filter((h): h is DiscHint => (kindHints as string[]).includes(h));
	if (shown.length === 0) return 'Disc text ignored';
	const hints = sentenceCase(joinAnd(shown.map((h) => lowerFirst(HINT_LABELS[h]))));
	const dbs = [
		...(values.thediscdb_enabled ? ['TheDiscDB'] : []),
		...(kind === 'dvd' && values.crc64service_enabled ? ['the ARM community database'] : [])
	];
	return dbs.length ? `${hints}, then ${joinAnd(dbs)}` : hints;
}

function lookupRow(
	key: 'movie' | 'tv' | 'music',
	label: 'Movies' | 'TV shows' | 'Music',
	listKey: string,
	trustKey: string,
	values: Record<string, unknown>,
	fields: ConfigFieldMeta[]
): PreviewRow {
	const sources = enabledLabels(values, listKey, fields).map((l, i) => ({ rank: i + 1, label: l }));
	return {
		key,
		label,
		sources,
		...(sources.length ? {} : { empty: NO_SOURCES }),
		trust: values[trustKey] ? 'Applies confident matches' : 'Waits for review'
	};
}

/** The Preview panel's rows for one disc kind, derived live from the form's values. */
export function previewRows(kind: DiscKind, values: Record<string, unknown>, fields: ConfigFieldMeta[]): PreviewRow[] {
	const disc: PreviewRow = { key: 'disc', label: 'Disc', sentence: discSentence(kind, values) };
	if (kind === 'cd') return [disc, lookupRow('music', 'Music', 'music_sources', 'music_auto_apply', values, fields)];
	return [
		disc,
		lookupRow('movie', 'Movies', 'movie_sources', 'movie_auto_apply', values, fields),
		lookupRow('tv', 'TV shows', 'episode_sources', 'episode_auto_apply', values, fields)
	];
}
