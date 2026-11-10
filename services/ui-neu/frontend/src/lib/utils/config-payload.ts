// Change detection for a schema config form: which fields a save sends,
// and how the form's state follows a save or a new config.
import type { ConfigFieldMeta } from '$lib/types/api.gen';
import { HIDDEN_SECRET } from '$lib/api/config';
import { unchanged } from '$lib/utils/unchanged';

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
