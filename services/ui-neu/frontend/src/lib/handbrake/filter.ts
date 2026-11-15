// The settings filter box and "Changed only" toggle: which keys match, and how
// many each tab holds so the tab strip can show it.

import type { HandbrakeSchemaSlimView, HandbrakeSettings, SlimKey } from '$lib/types/api.gen';
import { TABS, type TabId } from './fields';
import { storedCount } from './settingsEdit';

type Candidate = { name: string; label: string; tab: TabId; stored: boolean };

export function textMatches(name: string, label: string, text: string): boolean {
	const needle = text.trim().toLowerCase();
	return name.toLowerCase().includes(needle) || label.toLowerCase().includes(needle);
}

export function matchesFilter(key: SlimKey, text: string): boolean {
	return textMatches(key.name, key.label, text);
}

function audioItemHas(settings: HandbrakeSettings, name: string): boolean {
	const list = settings.common?.AudioList;
	return Array.isArray(list) && list.some((item) => item !== null && typeof item === 'object' && name in item);
}

function blockNames(settings: HandbrakeSettings): Set<string> {
	return new Set(Object.values(settings.encoders ?? {}).flatMap((block) => Object.keys(block)));
}

// Every key a tab could show: the schema keys, the audio output track keys,
// and encoder block keys the schema does not list (bit_depth).
function candidates(schema: HandbrakeSchemaSlimView, settings: HandbrakeSettings): Candidate[] {
	const common = settings.common ?? {};
	const blocks = blockNames(settings);
	const fromSchema = schema.keys.map((k) => ({
		name: k.name,
		label: k.label,
		tab: k.tab as TabId,
		stored: k.name in common || blocks.has(k.name)
	}));
	const fromAudio = schema.audio_item_keys.map((k) => ({
		name: k.name,
		label: k.label,
		tab: 'audio' as TabId,
		stored: audioItemHas(settings, k.name)
	}));
	const known = new Set(schema.keys.map((k) => k.name));
	const orphans = [...blocks]
		.filter((name) => !known.has(name))
		.map((name) => ({ name, label: name, tab: 'video' as TabId, stored: true }));
	return [...fromSchema, ...fromAudio, ...orphans];
}

function emptyCounts(): Record<TabId, number> {
	return Object.fromEntries(TABS.map((t) => [t.id, 0])) as Record<TabId, number>;
}

export function tabMatchCounts(
	schema: HandbrakeSchemaSlimView,
	settings: HandbrakeSettings,
	text: string,
	changedOnly: boolean
): Record<TabId, number> {
	const counts = emptyCounts();
	if (text.trim() === '') {
		for (const t of TABS) counts[t.id] = storedCount(settings, t.id, schema);
		return counts;
	}
	for (const c of candidates(schema, settings)) {
		if (textMatches(c.name, c.label, text) && (!changedOnly || c.stored)) counts[c.tab] += 1;
	}
	return counts;
}

// Stay on the current tab when it has a match; otherwise the first that does.
export function firstTabWithMatch(counts: Record<TabId, number>, current: TabId): TabId {
	if (counts[current] > 0) return current;
	return TABS.find((t) => counts[t.id] > 0)?.id ?? current;
}
