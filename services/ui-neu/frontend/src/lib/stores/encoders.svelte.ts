// Shared, fetch-once cache of the GET /api/encoders catalog (arm_common's
// encoder ids/labels/availability). Consumed by the transcode preset form's
// picker (which needs the full list, loading and error state) and by the
// preset/session list rows that only need a saved encoder id's display
// label. A module-level singleton, like resources.svelte.ts/config.ts: every
// caller shares one cached fetch instead of each list row fetching its own
// copy.

import { fetchEncoders } from '$lib/api/encoders';
import type { EncoderAvailabilityView } from '$lib/types/api.gen';

export const PRESET_ENCODER_ID = 'preset';

let encoders = $state<EncoderAvailabilityView[]>([]);
let loading = $state(false);
let error = $state<Error | null>(null);
let inFlight: Promise<void> | null = null;

// Idempotent: a cache hit or an already-running fetch both return without
// issuing a second request. A failed fetch leaves the cache empty so the
// next call (e.g. reopening the form) retries.
async function load(): Promise<void> {
	if (encoders.length > 0) return;
	if (inFlight) {
		await inFlight;
		return;
	}
	loading = true;
	error = null;
	inFlight = (async () => {
		try {
			encoders = await fetchEncoders();
		} catch (e) {
			error = e instanceof Error ? e : new Error(String(e));
		} finally {
			loading = false;
			inFlight = null;
		}
	})();
	await inFlight;
}

export const encodersStore = {
	get list(): EncoderAvailabilityView[] {
		return encoders;
	},
	get loading(): boolean {
		return loading;
	},
	get error(): Error | null {
		return error;
	},
	load
};

/** Display label for a saved preset's encoder id: '' for the tool's own
 * encoder (nothing to add), the cached catalog label once it has loaded,
 * and the raw id otherwise (unknown id, or the cache hasn't loaded yet). */
export function encoderLabel(id: string | null | undefined): string {
	if (!id || id === PRESET_ENCODER_ID) return '';
	return encoders.find((e) => e.id === id)?.label ?? id;
}
