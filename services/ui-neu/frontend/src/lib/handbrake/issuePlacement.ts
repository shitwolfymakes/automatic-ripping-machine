// Which save issues a rendered input shows, and how the sidebar banner names the rest.
// An issue counts as placed only when the panel renders its input with no filter: a field
// another setting hides, a card the encoder cannot reach or a collapsed card leaves it unplaced.

import type { HandbrakeSchemaSlimView, SettingIssue } from '$lib/types/api.gen';
import { BIT_DEPTH_FIELD } from './encoderCards';
import { TABS } from './fields';
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

function renderedSlots(input: PanelInput | null): Set<string> {
	if (!input) return new Set();
	return new Set(TABS.flatMap((t) => tabSlots(visibleTab({ ...input, filter: UNFILTERED }, t.id))));
}

function isPlaced(i: SettingIssue, slots: Set<string>): boolean {
	const encoder = i.encoder ?? null;
	return (encoder === null && PRESET_FIELDS.has(i.key)) || slots.has(slot(encoder, i.key));
}

// Issues no rendered input shows; the sidebar lists these in its banner. `input` is null while the
// settings panel is not shown.
export function unplacedIssues(issues: SettingIssue[], input: PanelInput | null): SettingIssue[] {
	const slots = renderedSlots(input);
	return issues.filter((i) => !isPlaced(i, slots));
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
