// What a setting reads as when the preset does not store it: the base preset's value, else the schema default.
// Pure functions.

import type { HandbrakeSchemaSlimView, HandbrakeSettings, SlimFamily, SlimKey } from '$lib/types/api.gen';
import type { Context } from './dependencyRules';

export type BaseValues = Record<string, unknown> | null;

const DEFAULT_DEPTH = 8;

export function commonOf(s: HandbrakeSettings): Record<string, unknown> {
	return s.common ?? {};
}

export function blockOf(s: HandbrakeSettings, family: string): Record<string, unknown> {
	return s.encoders?.[family] ?? {};
}

// The audio output tracks in effect: the preset's own list, else the base's, else none.
export function audioListValue(key: SlimKey, s: HandbrakeSettings, base: BaseValues): Record<string, unknown>[] {
	const common = commonOf(s);
	const list = key.name in common ? common[key.name] : inheritedValue(key, base);
	return Array.isArray(list) ? list : [];
}

export function inheritedValue(key: SlimKey, base: BaseValues): unknown {
	return base && key.name in base ? base[key.name] : key.default;
}

// The value of every key in effect: the preset's, else the base preset's, else the schema default.
export function panelContext(schema: HandbrakeSchemaSlimView, s: HandbrakeSettings, base: BaseValues): Context {
	return { ...Object.fromEntries(schema.keys.map((k) => [k.name, k.default])), ...base, ...commonOf(s) };
}

export function baseVideoEncoder(base: BaseValues): string | null {
	return typeof base?.VideoEncoder === 'string' ? base.VideoEncoder : null;
}

// R2: the base's VideoEncoder depth when it is this family, else 8.
export function inheritedDepth(family: SlimFamily, base: BaseValues): { depth: number; source: 'base' | 'default' } {
	const encoder = baseVideoEncoder(base);
	const variant = family.variants.find((v) => v.encoder === encoder);
	return variant ? { depth: variant.depth, source: 'base' } : { depth: DEFAULT_DEPTH, source: 'default' };
}
