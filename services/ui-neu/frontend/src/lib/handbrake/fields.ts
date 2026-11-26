// Maps each schema key to the form field that edits it, and to the options a
// select offers. Everything comes from the slim schema; no value list lives here.

import type { HandbrakeSchemaSlimView, SlimKey } from '$lib/types/api.gen';

type FieldKind = 'checkbox' | 'select' | 'number' | 'text' | 'chips' | 'audio-list' | 'rotate' | 'pad-color';
export type TabId = 'summary' | 'dimensions' | 'filters' | 'video' | 'audio' | 'subtitles' | 'chapters';

export const TABS: readonly { id: TabId; label: string }[] = [
	{ id: 'summary', label: 'Summary' },
	{ id: 'dimensions', label: 'Dimensions' },
	{ id: 'filters', label: 'Filters' },
	{ id: 'video', label: 'Video' },
	{ id: 'audio', label: 'Audio' },
	{ id: 'subtitles', label: 'Subtitles' },
	{ id: 'chapters', label: 'Chapters' }
];

const KIND_BY_TYPE: Record<string, FieldKind> = {
	bool: 'checkbox',
	list_obj: 'audio-list',
	list_str: 'chips',
	int: 'number',
	float: 'number'
};

// Keys whose value is built from more than one control.
const KIND_BY_NAME: Record<string, FieldKind> = {
	PictureRotate: 'rotate',
	PicturePadColor: 'pad-color'
};

// A list of strings stays chips even when a source constrains it; every other
// type with a source is a select.
export function fieldKind(key: SlimKey): FieldKind {
	const byName = KIND_BY_NAME[key.name];
	if (byName) return byName;
	const byType = KIND_BY_TYPE[key.type];
	if (byType && !(byType === 'number' && key.source)) return byType;
	return key.source ? 'select' : 'text';
}

export function numberLimits(key: SlimKey): { min: number; max: number } | null {
	return key.limits ? { min: key.limits[0], max: key.limits[1] } : null;
}

type Context = Record<string, unknown>;

type OptionResolver = (key: SlimKey, ref: string, schema: HandbrakeSchemaSlimView, context: Context) => unknown[];

// ref is either a filter name or the key that selects one (PictureDenoiseFilter).
function filterFor(ref: string, schema: HandbrakeSchemaSlimView, context: Context) {
	if (schema.filters[ref]) return schema.filters[ref];
	const chosen = scalarText(context[ref]);
	return schema.filters[schema.selector_filter_aliases[chosen] ?? chosen];
}

const RESOLVERS: Record<string, OptionResolver> = {
	static: (_key, ref, schema) => schema.static_enums[ref] ?? [],
	schema_list: (_key, ref, schema) => schema.lists[ref] ?? [],
	filter_presets: (_key, ref, schema, context) => filterFor(ref, schema, context)?.presets ?? [],
	filter_tunes: (_key, ref, schema, context) => filterFor(ref, schema, context)?.tunes ?? [],
	audio_mixdowns: (_key, ref, schema, context) => schema.audio_mixdowns_by_encoder[scalarText(context[ref])] ?? []
};

export function fieldOptions(
	key: SlimKey,
	schema: HandbrakeSchemaSlimView,
	context: Context
): Array<string | number> | null {
	if (!key.source) return null;
	const resolve = RESOLVERS[key.source.kind];
	const base = resolve ? resolve(key, key.source.ref, schema, context) : [];
	const extras = (schema.source_extras[key.name] ?? []).filter((v) => !base.includes(v));
	return [...base, ...extras] as Array<string | number>;
}

// The label the schema gives an option value, else the value itself.
export function optionLabel(key: SlimKey, value: string | number): string {
	return key.option_labels?.[String(value)] ?? String(value);
}

export function keysForTab(schema: HandbrakeSchemaSlimView, tab: TabId): SlimKey[] {
	return schema.keys.filter((k) => k.tab === tab);
}

// Keys grouped by their schema group, in the order the groups first appear.
export function groupsForTab(keys: SlimKey[]): { group: string; keys: SlimKey[] }[] {
	const groups = new Map<string, SlimKey[]>();
	for (const key of keys) groups.set(key.group, [...(groups.get(key.group) ?? []), key]);
	return [...groups].map(([group, members]) => ({ group, keys: members }));
}

interface FieldViewOption {
	value: string;
	label: string;
	selected: boolean;
	// The option as the schema lists it, so a number stays a number when chosen.
	raw: string | number;
}

interface FieldView {
	kind: FieldKind;
	shown: unknown;
	inputValue: string;
	placeholder: string | undefined;
	min: number | undefined;
	max: number | undefined;
	step: number | undefined;
	options: FieldViewOption[];
	chipValues: string[];
	stored: boolean;
}

interface FieldViewInput {
	value: unknown;
	inherited: unknown;
	stored: boolean;
	options: Array<string | number> | null;
	range?: { min: number; max: number; step: number };
}

// A stored value as text; anything that is not a string, number or boolean (an object) reads as empty.
export function scalarText(value: unknown): string {
	if (typeof value === 'string') return value;
	if (typeof value === 'number' || typeof value === 'boolean') return String(value);
	return '';
}

// A select keeps a stored value its list lacks (a hand-imported preset) as one more option labelled with it.
function selectOptions(key: SlimKey, text: string, options: Array<string | number>): FieldViewOption[] {
	const listed = options.map((raw) => ({
		value: String(raw),
		label: optionLabel(key, raw),
		selected: String(raw) === text,
		raw
	}));
	const unlisted = text !== '' && !listed.some((o) => o.selected);
	return unlisted ? [...listed, { value: text, label: text, selected: true, raw: text }] : listed;
}

// What a field draws: an unstored text or number field is empty with the inherited
// value as its placeholder; a select marks the inherited value as selected.
export function fieldView(key: SlimKey, opts: FieldViewInput): FieldView {
	const shown = opts.stored ? opts.value : opts.inherited;
	const text = scalarText(shown);
	const limits = numberLimits(key);
	return {
		kind: fieldKind(key),
		shown,
		inputValue: opts.stored ? text : '',
		placeholder: opts.stored ? undefined : text,
		min: opts.range?.min ?? limits?.min,
		max: opts.range?.max ?? limits?.max,
		step: opts.range?.step,
		options: selectOptions(key, text, opts.options ?? []),
		chipValues: Array.isArray(shown) ? shown.map(String) : [],
		stored: opts.stored
	};
}
