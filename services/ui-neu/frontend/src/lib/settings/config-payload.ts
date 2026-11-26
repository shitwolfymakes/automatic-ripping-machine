// Change detection for a schema config form: which fields a save sends,
// and how the form's state follows a save or a new config.
import type { ConfigFieldMeta } from '$lib/types/api.gen';
import { HIDDEN_SECRET } from '$lib/api/config';
import { unchanged } from '$lib/jobs/unchanged';

/** The fields a save sends: each of `fields` whose value differs from
 * `baseline`. A secret the operator cleared is sent as null, and an
 * untouched, masked or empty secret is left out, so the stored one is
 * kept. */
export function buildConfigPayload(
	fields: readonly ConfigFieldMeta[],
	values: Record<string, unknown>,
	baseline: Record<string, unknown>,
	cleared: Record<string, boolean>
): Record<string, unknown> {
	const out: Record<string, unknown> = {};
	for (const f of fields) {
		const v = values[f.key];
		if (f.tier === 'secret' && cleared[f.key] && (v === '' || v == null)) {
			out[f.key] = null;
			continue;
		}
		if (f.tier === 'secret' && (v === HIDDEN_SECRET || v === '' || v == null)) continue;
		if (unchanged(v, baseline[f.key])) continue;
		out[f.key] = v;
	}
	return out;
}

/** The form's overrides and values once `payload` is saved. A saved
 * secret becomes the mask in both, as an untouched one is on load, so
 * the raw secret is kept neither as a baseline nor on screen. Any other
 * key is kept as an override with its saved value. */
export function mergeSavedPayload(
	payload: Record<string, unknown>,
	fields: readonly ConfigFieldMeta[],
	overrides: Record<string, unknown>,
	values: Record<string, unknown>
): { overrides: Record<string, unknown>; values: Record<string, unknown> } {
	const mergedOverrides = { ...overrides };
	const mergedValues = { ...values };
	for (const key of Object.keys(payload)) {
		const field = fields.find((f) => f.key === key);
		if (field?.tier === 'secret') {
			mergedOverrides[key] = HIDDEN_SECRET;
			mergedValues[key] = HIDDEN_SECRET;
		} else {
			mergedOverrides[key] = payload[key];
		}
	}
	return { overrides: mergedOverrides, values: mergedValues };
}

/** The form's values for a new `config`: each field's value from it,
 * except that a field `kept` holds keeps its edit when `config` didn't
 * change that field from `kept.config`. Pass `kept` only when the field
 * list is the one the form already showed; with null, every value comes
 * from `config`. */
export function mergeConfigValues(
	fields: readonly ConfigFieldMeta[],
	config: Record<string, unknown>,
	kept: { config: Record<string, unknown>; values: Record<string, unknown> } | null
): Record<string, unknown> {
	const next: Record<string, unknown> = {};
	for (const f of fields) {
		const v = config[f.key];
		// A new `config` (another tab's save folded in, or a reload) replaces
		// only the values it changed; an unsaved edit to any other field of
		// this form survives, since Settings keeps every config tab mounted.
		next[f.key] = kept && f.key in kept.values && unchanged(v, kept.config[f.key]) ? kept.values[f.key] : v;
	}
	return next;
}
