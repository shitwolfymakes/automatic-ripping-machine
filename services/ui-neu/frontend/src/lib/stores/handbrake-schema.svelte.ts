// Shared cache of GET /api/handbrake-schema, the slim view the preset sidebar
// renders from. `unavailable` covers the 503 "No HandBrake schema loaded yet"
// state (and any other failed load); retry() asks the backend to refresh first.

import { fetchHandbrakeSchema, refreshHandbrakeSchema } from '$lib/api/handbrake-schema';
import type { HandbrakeSchemaSlimView } from '$lib/types/api.gen';
import { errorMessage } from '$lib/utils/errors';

type SchemaState = 'idle' | 'loading' | 'ready' | 'unavailable';

let state = $state<SchemaState>('idle');
let schema = $state<HandbrakeSchemaSlimView | null>(null);
let error = $state<string | null>(null);

async function load(): Promise<void> {
	state = 'loading';
	error = null;
	try {
		schema = await fetchHandbrakeSchema();
		state = 'ready';
	} catch (e) {
		schema = null;
		error = errorMessage(e, String(e));
		state = 'unavailable';
	}
}

// The refresh error, or null when the refresh worked or could not be asked.
async function refreshError(): Promise<string | null> {
	try {
		const result = await refreshHandbrakeSchema();
		return result.ok ? null : result.error;
	} catch {
		return null;
	}
}

async function retry(): Promise<void> {
	const failure = await refreshError();
	await load();
	if (state === 'unavailable' && failure) error = failure;
}

function reset(): void {
	state = 'idle';
	schema = null;
	error = null;
}

export const handbrakeSchema = {
	get state() {
		return state;
	},
	get schema() {
		return schema;
	},
	get error() {
		return error;
	},
	load,
	retry,
	reset
};
