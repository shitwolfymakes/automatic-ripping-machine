// Which per-encoder cards a preset shows on the Video tab, in which state, and
// which fields each card holds. Mirrors the backend's reachable_families so the
// card order is the claim order. Pure functions; no I/O.

import type {
	EncoderAvailabilityView,
	HandbrakeSchemaSlimView,
	SlimFamily,
	SlimKey,
	SlimVariant
} from '$lib/types/api.gen';
import type { FilterState } from './sidebarModel';
import { fieldVisible, type Context } from './visibility';

// 'open' is a card with no hardware state to report: a pinned or base-preset family.
export type CardState = 'verified' | 'cpu-fallback' | 'collapsed' | 'open';
export interface EncoderCard {
	family: string;
	label: string;
	state: CardState;
	device: string | null;
}

// HandBrake GPU families by vendor rank (the backend's VENDOR_RANK). VAAPI runs ffmpeg, so it has none.
const GPU_FAMILY_PREFIXES = ['nvenc', 'qsv'];
// The catalog's cpu_<codec> ids run these HandBrake families (arm_common encoders _CPU_ENGINE_ENCODER).
const CPU_FAMILY: Record<string, string> = { h264: 'x264', h265: 'x265', av1: 'svt_av1' };
const CATALOG_ID = /^(any|cpu|nvenc|qsv|vaapi)_(h264|h265|av1)$/;

function parseId(encoderId: string): { kind: string; codec: string } | null {
	const match = CATALOG_ID.exec(encoderId);
	return match ? { kind: match[1], codec: match[2] } : null;
}

function hasFamily(schema: HandbrakeSchemaSlimView, name: string): boolean {
	return schema.families.some((f) => f.name === name);
}

function familyOfVariant(schema: HandbrakeSchemaSlimView, encoder: string): string[] {
	return schema.families.filter((f) => f.variants.some((v) => v.encoder === encoder)).map((f) => f.name);
}

function reachableFamilies(
	encoderId: string,
	presetRef: string | null,
	schema: HandbrakeSchemaSlimView,
	baseVideoEncoder: string | null
): string[] {
	if (encoderId === 'preset') {
		return presetRef === null || baseVideoEncoder === null ? [] : familyOfVariant(schema, baseVideoEncoder);
	}
	const id = parseId(encoderId);
	if (id === null || id.kind === 'vaapi') return [];
	if (id.kind === 'any') {
		const gpu = GPU_FAMILY_PREFIXES.map((p) => `${p}_${id.codec}`).filter((f) => hasFamily(schema, f));
		return [...gpu, CPU_FAMILY[id.codec]];
	}
	return [id.kind === 'cpu' ? CPU_FAMILY[id.codec] : encoderId];
}

function cardFor(family: string, anyCodec: boolean, availability: EncoderAvailabilityView[]): EncoderCard {
	const entry = availability.find((a) => a.id === family);
	const label = entry?.label ?? family;
	if (entry?.available) return { family, label, state: 'verified', device: entry.label };
	if (!anyCodec) return { family, label, state: 'open', device: null };
	const isCpu = Object.values(CPU_FAMILY).includes(family);
	return { family, label, state: isCpu ? 'cpu-fallback' : 'collapsed', device: null };
}

const STATUS_LINES: Record<Exclude<CardState, 'verified'>, string> = {
	'cpu-fallback': 'Fallback when no GPU is free',
	collapsed: 'No verified device',
	open: ''
};

// The card's hardware status, shown beside its title. '' when it has none to report.
export function cardStatusLine(card: EncoderCard): string {
	return card.state === 'verified' ? `Verified on ${card.device}` : STATUS_LINES[card.state];
}

export const ALL_ENCODERS_LINE = 'These apply whichever device runs the encode.';

export function perEncoderLine(encoderLabel: string): string {
	return `${encoderLabel} can land on the encoders below. Each keeps its own speed preset, profile, level and quality, because the values differ between them.`;
}

export function encoderCards(
	encoderId: string,
	presetRef: string | null,
	schema: HandbrakeSchemaSlimView,
	availability: EncoderAvailabilityView[],
	baseVideoEncoder: string | null
): EncoderCard[] {
	const anyCodec = parseId(encoderId)?.kind === 'any';
	const families = reachableFamilies(encoderId, presetRef, schema, baseVideoEncoder);
	return families.map((family) => cardFor(family, anyCodec, availability));
}

// Block keys that only some families have (R6, rule 11): HandBrake's multi-pass
// and turbo flags, and advanced options on x264 only.
const FAMILY_GATES: Record<string, (family: SlimFamily) => boolean> = {
	VideoMultiPass: (f) => f.multipass,
	VideoTurboMultiPass: (f) => f.turbo,
	x264UseAdvancedOptions: (f) => f.name === 'x264',
	x264Option: (f) => f.name === 'x264'
};
// Display order only; which keys are block keys comes from the schema. A key not listed here follows the rest.
const DISPLAY_RANK = [
	'VideoPreset',
	'VideoTune',
	'VideoProfile',
	'VideoLevel',
	'VideoQualitySlider',
	'VideoMultiPass',
	'VideoTurboMultiPass',
	'x264UseAdvancedOptions',
	'x264Option',
	'VideoOptionExtra'
];

function rank(name: string): number {
	const at = DISPLAY_RANK.indexOf(name);
	return at === -1 ? DISPLAY_RANK.length : at;
}

// The family's block keys (the schema's encoder-specific keys it can take), in display order.
export function blockFields(schema: HandbrakeSchemaSlimView, family: SlimFamily): SlimKey[] {
	const names = schema.encoder_specific_keys.filter((name) => FAMILY_GATES[name]?.(family) ?? true);
	return names
		.map((name) => schema.keys.find((k) => k.name === name))
		.filter((k): k is SlimKey => k !== undefined)
		.sort((a, b) => rank(a.name) - rank(b.name));
}

// A card for a device the host cannot verify stays collapsed until the user expands it, or it stores a value.
export function cardOpen(card: EncoderCard, block: Record<string, unknown>, expanded: boolean): boolean {
	return expanded || card.state !== 'collapsed' || Object.keys(block).length > 0;
}

export const BIT_DEPTH_FIELD = { name: 'bit_depth', label: 'Bit depth' };

// The variant a card edits: the block's bit depth, else the inherited one; the family's first variant
// when no variant has that depth.
export function cardVariant(family: SlimFamily, block: Record<string, unknown>, inheritedDepth: number): SlimVariant {
	const depth = typeof block.bit_depth === 'number' ? block.bit_depth : inheritedDepth;
	return family.variants.find((v) => v.depth === depth) ?? family.variants[0];
}

// A block key as the card shows it. The variant supplies the preset, tune, profile and level lists, so those
// render as selects though the schema names no source; the quality label names the variant's scale.
export function cardKey(key: SlimKey, variant: SlimVariant): SlimKey {
	if (key.name in VARIANT_LISTS) return { ...key, source: { kind: 'variant', ref: key.name } };
	if (key.name === 'VideoOptionExtra') return { ...key, label: 'Extra encoder options' };
	if (key.name !== 'VideoQualitySlider') return key;
	const q = variant.quality;
	return { ...key, label: `Quality (${q.name}, ${q.low} to ${q.high})` };
}

// The names of the inputs a card shows, bit depth first. The filter matches the labels the card shows,
// and the block's values override the panel context.
export function visibleCardFields(
	schema: HandbrakeSchemaSlimView,
	family: SlimFamily,
	variant: SlimVariant,
	block: Record<string, unknown>,
	ctx: Context,
	f: FilterState
): string[] {
	const cardCtx = { ...ctx, ...block };
	const keys = [BIT_DEPTH_FIELD, ...blockFields(schema, family).map((k) => cardKey(k, variant))];
	return keys.filter((k) => fieldVisible(k.name, k.label, f, block[k.name] !== undefined, cardCtx)).map((k) => k.name);
}

// The block keys whose choices come from the encoder variant, and which variant list holds them.
export const VARIANT_LISTS: Record<string, keyof SlimVariant> = {
	VideoPreset: 'presets',
	VideoTune: 'tunes',
	VideoProfile: 'profiles',
	VideoLevel: 'levels'
};

// What a variant-list key resolves to when the block stores nothing: the base preset's value when the base
// runs this variant, else the schema default if the variant offers it, else the variant's first value.
export function blockDefault(key: SlimKey, variant: SlimVariant, base: Record<string, unknown> | null): string | null {
	const list = VARIANT_LISTS[key.name];
	if (!list) return null;
	const values = variant[list] as string[];
	const fromBase = base?.VideoEncoder === variant.encoder ? base[key.name] : undefined;
	return (
		[fromBase, key.default].find((v): v is string => typeof v === 'string' && values.includes(v)) ?? values[0] ?? null
	);
}

export function showsAmdNote(encoderId: string, availability: EncoderAvailabilityView[]): boolean {
	return parseId(encoderId)?.kind === 'any' && availability.some((a) => a.vendor === 'vaapi' && a.available);
}
