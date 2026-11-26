// Pure helpers for HandBrake's AudioList: one object per output audio track.
// Every helper returns new arrays and objects; nothing here mutates its input.

import type { HandbrakeSchemaSlimView, SettingIssue, SlimKey } from '$lib/types/api.gen';
import { fieldOptions, scalarText } from './fields';
import type { FilterState } from './visibility';
import { fieldVisible, type Context } from './dependency-rules';

export type AudioItem = Record<string, unknown>;

// Row layout: encoder, mixdown, sample rate, bitrate, quality, gain, DRC.
// Any other audio item key follows these.
const ROW_ORDER = [
	'AudioEncoder',
	'AudioMixdown',
	'AudioSamplerate',
	'AudioBitrate',
	'AudioTrackQualityEnable',
	'AudioTrackQuality',
	'AudioTrackGainSlider',
	'AudioTrackDRCSlider'
];

const ENCODER = 'AudioEncoder';
const MIXDOWN = 'AudioMixdown';
const SAMPLERATE = 'AudioSamplerate';

function itemKey(schema: HandbrakeSchemaSlimView, name: string): SlimKey | undefined {
	return schema.audio_item_keys.find((k) => k.name === name);
}

// The template item: every audio item key at its schema default.
export function addTrack(list: AudioItem[], schema: HandbrakeSchemaSlimView): AudioItem[] {
	const template = Object.fromEntries(schema.audio_item_keys.map((k) => [k.name, k.default]));
	return [...list, template];
}

export function removeTrack(list: AudioItem[], index: number): AudioItem[] {
	return list.filter((_, i) => i !== index);
}

// An index that would leave the list returns an unchanged copy.
export function moveTrack(list: AudioItem[], index: number, dir: -1 | 1): AudioItem[] {
	const target = index + dir;
	if (index < 0 || index >= list.length || target < 0 || target >= list.length) return [...list];
	const next = [...list];
	[next[index], next[target]] = [next[target], next[index]];
	return next;
}

export function setTrackField(list: AudioItem[], index: number, name: string, value: unknown): AudioItem[] {
	return list.map((item, i) => (i === index ? { ...item, [name]: value } : item));
}

// Dropping the key lets the row fall back to the schema default.
export function clearTrackField(list: AudioItem[], index: number, name: string): AudioItem[] {
	return list.map((item, i) => {
		if (i !== index) return item;
		const { [name]: _dropped, ...rest } = item;
		return rest;
	});
}

// The row's encoder, or the schema default encoder when the row does not set one.
export function rowEncoder(item: AudioItem, schema: HandbrakeSchemaSlimView): string {
	const set = item[ENCODER];
	if (set != null) return scalarText(set);
	return scalarText(itemKey(schema, ENCODER)?.default);
}

// Mixdowns the encoder accepts, from the schema's per-encoder table.
export function mixdownsFor(schema: HandbrakeSchemaSlimView, encoder: string): string[] {
	const key = itemKey(schema, MIXDOWN);
	return (key ? (fieldOptions(key, schema, { [ENCODER]: encoder }) ?? []) : []).map(String);
}

// The slim view carries one sample rate list for every encoder, so no row narrows it.
export function samplerates(schema: HandbrakeSchemaSlimView): string[] {
	const key = itemKey(schema, SAMPLERATE);
	return (key ? (fieldOptions(key, schema, {}) ?? []) : []).map(String);
}

// Audio item keys in row order; unknown extras trail.
export function rowKeys(schema: HandbrakeSchemaSlimView): SlimKey[] {
	const rank = (k: SlimKey) => {
		const at = ROW_ORDER.indexOf(k.name);
		return at === -1 ? ROW_ORDER.length : at;
	};
	return [...schema.audio_item_keys].sort((a, b) => rank(a) - rank(b));
}

// The fields one track shows, in the order of `keys`. The track's own values, then the item defaults,
// override the panel context, so a track's quality toggle decides between its bitrate and its quality.
export function visibleTrackKeys(keys: SlimKey[], track: AudioItem, ctx: Context, f: FilterState): SlimKey[] {
	const trackCtx = { ...ctx, ...Object.fromEntries(keys.map((k) => [k.name, k.default])), ...track };
	return keys.filter((k) => fieldVisible(k.name, k.label, f, track[k.name] !== undefined, trackCtx));
}

// Options for one field of one row: mixdowns follow the row's encoder.
export function rowOptions(
	key: SlimKey,
	item: AudioItem,
	schema: HandbrakeSchemaSlimView
): Array<string | number> | null {
	if (key.name === MIXDOWN) return mixdownsFor(schema, rowEncoder(item, schema));
	if (key.name === SAMPLERATE) return samplerates(schema);
	return fieldOptions(key, schema, item);
}

export function rowIssue(issues: SettingIssue[], index: number, name: string): SettingIssue | undefined {
	return issues.find((i) => i.key === `AudioList[${index}].${name}`);
}

// The track list's element id: the focus target of a whole-list issue, named like a common key's input.
export const AUDIO_LIST_ID = 'tunable-AudioList';

export function listIssues(issues: SettingIssue[]): SettingIssue[] {
	return issues.filter((i) => i.key === 'AudioList');
}
