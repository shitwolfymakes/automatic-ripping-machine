// Which save issues a rendered input shows, where Save sends focus for them, and how the
// sidebar banner names the rest.
// An issue counts as placed only when the panel renders its input with no filter: a field
// another setting hides, a card the encoder cannot reach or a collapsed card leaves it unplaced.
// Form order is the preset block, then the tabs in strip order, each in render order.

import type { HandbrakeSchemaSlimView, SettingIssue } from '$lib/types/api.gen';
import type { FieldErrors } from '$lib/utils/formValidation';
import { BIT_DEPTH_FIELD } from './encoder-cards';
import { TABS, type TabId } from './fields';
import { visibleTab, type TabVisible, type VisibleInput } from './filter';

export type PanelInput = Omit<VisibleInput, 'filter'>;

// In the preset block's render order.
const PRESET_FIELDS = ['name', 'media_type', 'tool', 'container', 'encoder', 'preset_ref', 'extra_args'];
const UNFILTERED = { text: '', changedOnly: false };
const TRACK_ITEM = /^AudioList\[(\d+)\]\.(.+)$/;

function slot(encoder: string | null, key: string): string {
	return `${encoder ?? ''}|${key}`;
}

// The issue keys of one tab's inputs, in render order.
function tabSlots(v: TabVisible): string[] {
	const rows = v.rows.map((r) => slot(null, r.key.name));
	const tracks = v.tracks.flatMap((keys, i) => keys.map((k) => slot(null, `AudioList[${i}].${k.name}`)));
	const cards = v.cards.filter((c) => c.open).flatMap((c) => c.fields.map((f) => slot(c.family.name, f)));
	return [...rows, ...tracks, ...cards];
}

// The issue keys of every rendered input in form order; the preset block's alone while the panel is not shown.
function formSlots(input: PanelInput | null): string[] {
	const preset = PRESET_FIELDS.map((k) => slot(null, k));
	if (!input) return preset;
	return [...preset, ...TABS.flatMap((t) => tabSlots(visibleTab({ ...input, filter: UNFILTERED }, t.id)))];
}

function issueSlot(i: SettingIssue): string {
	return slot(i.encoder ?? null, i.key);
}

// Issues no rendered input shows; the sidebar lists these in its banner. `input` is null while the
// settings panel is not shown.
export function unplacedIssues(issues: SettingIssue[], input: PanelInput | null): SettingIssue[] {
	if (issues.length === 0) return [];
	const slots = new Set(formSlots(input));
	return issues.filter((i) => !slots.has(issueSlot(i)));
}

// Issues a rendered input shows, in form order: the complement of unplacedIssues.
export function placedIssues(issues: SettingIssue[], input: PanelInput | null): SettingIssue[] {
	if (issues.length === 0) return [];
	const order = formSlots(input);
	return issues
		.map((issue) => ({ issue, rank: order.indexOf(issueSlot(issue)) }))
		.filter((r) => r.rank >= 0)
		.sort((a, b) => a.rank - b.rank)
		.map((r) => r.issue);
}

/** Where a placed issue's input lives: its element id, and the tab to open first (null outside the tabs). */
export interface IssueTarget {
	id: string;
	tab: TabId | null;
}

function encoderInputId(encoder: string, key: string): string {
	return key === BIT_DEPTH_FIELD.name ? `${encoder}-bit-depth` : `${encoder}-tunable-${key}`;
}

function keyTab(keys: { name: string; tab: string }[] | undefined, name: string): TabId | null {
	return (keys?.find((k) => k.name === name)?.tab as TabId | undefined) ?? null;
}

// The ids follow the inputs: tp-<field> in the preset block, <family>-bit-depth and
// <family>-tunable-<key> in an encoder card (the Video tab), audio-<track>-tunable-<key> in a
// track and tunable-<key> for a common key.
export function issueTarget(i: SettingIssue, schema: HandbrakeSchemaSlimView | null): IssueTarget {
	if (i.encoder) return { id: encoderInputId(i.encoder, i.key), tab: 'video' };
	if (PRESET_FIELDS.includes(i.key)) return { id: `tp-${i.key.replaceAll('_', '-')}`, tab: null };
	const track = TRACK_ITEM.exec(i.key);
	if (track) return { id: `audio-${track[1]}-tunable-${track[2]}`, tab: keyTab(schema?.audio_item_keys, track[2]) };
	return { id: `tunable-${i.key}`, tab: keyTab(schema?.keys, i.key) };
}

/** The target of the first issue, in form order, that a rendered input shows; null when none does. */
export function firstIssueTarget(issues: SettingIssue[], input: PanelInput | null): IssueTarget | null {
	const first = placedIssues(issues, input)[0];
	return first ? issueTarget(first, input?.schema ?? null) : null;
}

/** The messages of the issues on preset-block fields, keyed by input id; the first issue per field wins. */
export function presetBlockMessages(issues: SettingIssue[]): FieldErrors {
	const messages: FieldErrors = {};
	for (const i of issues) {
		if (i.encoder || !PRESET_FIELDS.includes(i.key)) continue;
		const { id } = issueTarget(i, null);
		messages[id] ??= i.message;
	}
	return messages;
}

function trackLabel(schema: HandbrakeSchemaSlimView, index: string, name: string): string | null {
	const key = schema.audio_item_keys.find((k) => k.name === name);
	return key ? `Audio track ${Number(index) + 1} ${key.label}` : null;
}

function issueLabel(i: SettingIssue, schema: HandbrakeSchemaSlimView): string | null {
	const track = TRACK_ITEM.exec(i.key);
	if (track) return trackLabel(schema, track[1], track[2]);
	const key = [...schema.keys, BIT_DEPTH_FIELD].find((k) => k.name === i.key);
	if (!key) return null;
	return i.encoder ? `${key.label} (${i.encoder})` : key.label;
}

// The banner line: the setting's label, then the message; the message alone when no setting matches.
export function unplacedText(i: SettingIssue, schema: HandbrakeSchemaSlimView | null): string {
	const label = schema ? issueLabel(i, schema) : null;
	return label ? `${label}: ${i.message}` : i.message;
}
