// Which save issues a rendered input shows, where Save sends focus for them, and how the
// sidebar banner names the rest.
// An issue counts as placed only when the panel renders its input with no filter: a field
// another setting hides, a card the encoder cannot reach or a collapsed card leaves it unplaced.

import type { HandbrakeSchemaSlimView, SettingIssue } from '$lib/types/api.gen';
import type { FieldErrors } from '$lib/utils/formValidation';
import { BIT_DEPTH_FIELD } from './encoderCards';
import { TABS, type TabId } from './fields';
import { visibleTab, type TabVisible, type VisibleInput } from './filter';

export type PanelInput = Omit<VisibleInput, 'filter'>;

const PRESET_FIELDS = new Set(['name', 'media_type', 'tool', 'preset_ref', 'container', 'encoder', 'extra_args']);
const UNFILTERED = { text: '', changedOnly: false };
const TRACK_ITEM = /^AudioList\[(\d+)\]\.(.+)$/;

function slot(encoder: string | null, key: string): string {
	return `${encoder ?? ''}|${key}`;
}

// The issue keys of one tab's inputs. Bit depth has no issue line, so it places nothing.
function tabSlots(v: TabVisible): string[] {
	const rows = v.rows.map((r) => slot(null, r.key.name));
	const tracks = v.tracks.flatMap((keys, i) => keys.map((k) => slot(null, `AudioList[${i}].${k.name}`)));
	const cards = v.cards
		.filter((c) => c.open)
		.flatMap((c) => c.fields.filter((f) => f !== BIT_DEPTH_FIELD.name).map((f) => slot(c.family.name, f)));
	return [...rows, ...tracks, ...cards];
}

function renderedSlots(issues: SettingIssue[], input: PanelInput | null): Set<string> {
	if (!input || issues.length === 0) return new Set();
	return new Set(TABS.flatMap((t) => tabSlots(visibleTab({ ...input, filter: UNFILTERED }, t.id))));
}

function isPlaced(i: SettingIssue, slots: Set<string>): boolean {
	const encoder = i.encoder ?? null;
	return (encoder === null && PRESET_FIELDS.has(i.key)) || slots.has(slot(encoder, i.key));
}

// Issues no rendered input shows; the sidebar lists these in its banner. `input` is null while the
// settings panel is not shown.
export function unplacedIssues(issues: SettingIssue[], input: PanelInput | null): SettingIssue[] {
	const slots = renderedSlots(issues, input);
	return issues.filter((i) => !isPlaced(i, slots));
}

// Issues a rendered input shows: the complement of unplacedIssues.
export function placedIssues(issues: SettingIssue[], input: PanelInput | null): SettingIssue[] {
	const slots = renderedSlots(issues, input);
	return issues.filter((i) => isPlaced(i, slots));
}

/** Where a placed issue's input lives: its element id, and the tab to open first (null outside the tabs). */
export interface IssueTarget {
	id: string;
	tab: TabId | null;
}

function keyTab(keys: { name: string; tab: string }[] | undefined, name: string): TabId | null {
	return (keys?.find((k) => k.name === name)?.tab as TabId | undefined) ?? null;
}

// The ids follow the inputs: tp-<field> in the preset block, <family>-tunable-<key> in an encoder
// card (the Video tab), audio-<track>-tunable-<key> in a track and tunable-<key> for a common key.
export function issueTarget(i: SettingIssue, schema: HandbrakeSchemaSlimView | null): IssueTarget {
	if (i.encoder) return { id: `${i.encoder}-tunable-${i.key}`, tab: 'video' };
	if (PRESET_FIELDS.has(i.key)) return { id: `tp-${i.key.replaceAll('_', '-')}`, tab: null };
	const track = TRACK_ITEM.exec(i.key);
	if (track) return { id: `audio-${track[1]}-tunable-${track[2]}`, tab: keyTab(schema?.audio_item_keys, track[2]) };
	return { id: `tunable-${i.key}`, tab: keyTab(schema?.keys, i.key) };
}

/** The target of the first issue a rendered input shows; null when none does. */
export function firstIssueTarget(issues: SettingIssue[], input: PanelInput | null): IssueTarget | null {
	const first = placedIssues(issues, input)[0];
	return first ? issueTarget(first, input?.schema ?? null) : null;
}

/** The messages of the issues on preset-block fields, keyed by input id; the first issue per field wins. */
export function presetBlockMessages(issues: SettingIssue[]): FieldErrors {
	const messages: FieldErrors = {};
	for (const i of issues) {
		if (i.encoder || !PRESET_FIELDS.has(i.key)) continue;
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
