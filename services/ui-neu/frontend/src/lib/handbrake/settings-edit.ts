// Pure edits of a preset's HandBrake settings. Every function returns a new
// object and leaves its input alone, so callers can hold the old value as undo.

import type { HandbrakeSchemaSlimView, HandbrakeSettings } from '$lib/types/api.gen';
import type { TabId } from './fields';

type Block = Record<string, unknown>;
type Settings = { common: Block; encoders: Record<string, Block> };

function normalise(s: HandbrakeSettings): Settings {
	return { common: s.common ?? {}, encoders: s.encoders ?? {} };
}

function without(block: Block, key: string): Block {
	const rest = { ...block };
	delete rest[key];
	return rest;
}

export function setCommon(s: HandbrakeSettings, key: string, value: unknown): HandbrakeSettings {
	const n = normalise(s);
	return { ...n, common: { ...n.common, [key]: value } };
}

export function resetCommon(s: HandbrakeSettings, key: string): HandbrakeSettings {
	const n = normalise(s);
	return { ...n, common: without(n.common, key) };
}

export function setBlock(s: HandbrakeSettings, family: string, key: string, value: unknown): HandbrakeSettings {
	const n = normalise(s);
	return { ...n, encoders: { ...n.encoders, [family]: { ...n.encoders[family], [key]: value } } };
}

// Removes the key, and the whole block once nothing is left in it.
export function resetBlock(s: HandbrakeSettings, family: string, key: string): HandbrakeSettings {
	const n = normalise(s);
	const rest = without(n.encoders[family] ?? {}, key);
	const encoders = { ...n.encoders };
	if (Object.keys(rest).length === 0) delete encoders[family];
	else encoders[family] = rest;
	return { ...n, encoders };
}

// Drops the blocks of encoders the host cannot reach any more.
export function pruneUnreachable(s: HandbrakeSettings, reachable: string[]): HandbrakeSettings {
	const n = normalise(s);
	const kept = Object.entries(n.encoders).filter(([family]) => reachable.includes(family));
	return { ...n, encoders: Object.fromEntries(kept) };
}

// The wire value: nothing stored at all is null, not an empty shell.
export function toPayload(s: HandbrakeSettings): HandbrakeSettings | null {
	const n = normalise(s);
	const blocks = Object.entries(n.encoders).filter(([, block]) => Object.keys(block).length > 0);
	if (Object.keys(n.common).length === 0 && blocks.length === 0) return null;
	return { common: n.common, encoders: Object.fromEntries(blocks) };
}

export function storedCount(s: HandbrakeSettings, tab: TabId, schema: HandbrakeSchemaSlimView): number {
	const n = normalise(s);
	const inTab = new Set(schema.keys.filter((k) => k.tab === tab).map((k) => k.name));
	const common = Object.keys(n.common).filter((name) => inTab.has(name)).length;
	if (tab !== 'video') return common;
	return common + Object.values(n.encoders).reduce((sum, block) => sum + Object.keys(block).length, 0);
}
