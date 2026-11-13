// How the draft changes when the tool, the encoder or the base preset does.
// Pure functions; the sidebar component does the I/O.

import type { HandbrakeSchemaSlimView, TranscodeTool } from '$lib/types/api.gen';
import { baseVideoEncoder } from './base-values';
import type { Draft, PresetField } from './draft';
import { PRESET_ENCODER_ID } from './encoder-availability';
import { encoderCards } from './encoder-cards';
import { pruneUnreachable } from './settings-edit';

// The built-in presets loaded so far, by name.
export type Bases = Record<string, Record<string, unknown>>;

const LOCKED_TOOLS = new Set<TranscodeTool>(['abcde', 'none']);

// abcde and none run their own encoder, so a codec encoder would 422.
export function onToolChange(d: Draft, tool: TranscodeTool): Draft {
	return { ...d, tool, encoder: LOCKED_TOOLS.has(tool) ? PRESET_ENCODER_ID : d.encoder };
}

// Drops the blocks of families the new encoder can never reach (Review Focus 4).
export function onEncoderChange(
	d: Draft,
	encoderId: string,
	schema: HandbrakeSchemaSlimView,
	baseEncoder: string | null = null
): Draft {
	const reachable = encoderCards(encoderId, d.preset_ref, schema, [], baseEncoder).map((c) => c.family);
	return { ...d, encoder: encoderId, settings: pruneUnreachable(d.settings, reachable) };
}

function baseEncoderOf(bases: Bases, presetRef: string | null): string | null {
	return baseVideoEncoder(presetRef === null ? null : (bases[presetRef] ?? null));
}

// The preset encoder reaches only its base's family, so a new base drops the blocks it no longer reaches.
// A base whose values have not loaded cannot be resolved yet; its blocks stay until it loads.
export function onBaseChange(
	d: Draft,
	presetRef: string | null,
	schema: HandbrakeSchemaSlimView | null,
	bases: Bases
): Draft {
	const next = { ...d, preset_ref: presetRef };
	if (!schema || d.encoder !== PRESET_ENCODER_ID) return next;
	if (presetRef !== null && !(presetRef in bases)) return next;
	return onEncoderChange(next, PRESET_ENCODER_ID, schema, baseEncoderOf(bases, presetRef));
}

// One preset-block edit; `bases` holds the built-in presets loaded so far, by name. Without a schema the
// blocks cannot be pruned, so an encoder change only sets the id.
export function applyField(
	d: Draft,
	field: PresetField,
	value: string,
	schema: HandbrakeSchemaSlimView | null,
	bases: Bases
): Draft {
	if (field === 'tool') return onToolChange(d, value as TranscodeTool);
	if (field === 'encoder') {
		return schema ? onEncoderChange(d, value, schema, baseEncoderOf(bases, d.preset_ref)) : { ...d, encoder: value };
	}
	if (field === 'preset_ref') return onBaseChange(d, value || null, schema, bases);
	return { ...d, [field]: value };
}
