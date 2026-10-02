// Instant status refresh from `ripper.events` and `transcode.events`. A
// NOTIFIER, not a data store: it holds no job state. It subscribes once to
// the bare `ripper.events` and `transcode.events` topics, coalesces the
// job_ids seen within a debounce window, and invokes each registered
// listener once per flush with the accumulated set, plus the event types
// seen per job in that window (for listeners that care which event fired,
// e.g. job.identity_updated). Every listener (the dashboard included)
// therefore also refreshes on transcode lifecycle events, debounced. The
// name predates the transcode topic and is kept.
// Listeners re-run their own existing fetchers; polling stays untouched as
// reconciliation (WS down => exactly today's behavior).
//
// Lifecycle: pages call startRipperEvents() on mount (idempotent) and
// unregister only their own listener on unmount. The topic subscription is
// shared — a page unmounting must not sever another page's feed — so pages
// never call stopRipperEvents() (it exists for tests and symmetry).

import { wsClient, type WSEnvelope } from '$lib/api/ws';

// Coalesce bursts (rip-end emits track.completed xN + rip.completed
// back-to-back) into a single refresh.
const DEBOUNCE_MS = 300;

export type RipperEventTypes = Map<string, Set<string>>;
type Listener = (jobIds: Set<string>, eventTypes: RipperEventTypes) => void;

// eslint-disable-next-line svelte/prefer-svelte-reactivity -- notifier bookkeeping, never read reactively
const listeners = new Set<Listener>();
// eslint-disable-next-line svelte/prefer-svelte-reactivity -- notifier bookkeeping, never read reactively
let pendingJobIds = new Set<string>();
// eslint-disable-next-line svelte/prefer-svelte-reactivity -- notifier bookkeeping, never read reactively
let pendingTypes: RipperEventTypes = new Map();
let timer: ReturnType<typeof setTimeout> | null = null;
let unsubs: Array<() => void> = [];

function jobIdOf(env: WSEnvelope): string | null {
	if (env.job_id) return env.job_id;
	const fromPayload = (env.payload as { job_id?: unknown }).job_id;
	return typeof fromPayload === 'string' && fromPayload !== '' ? fromPayload : null;
}

function onEvent(env: WSEnvelope): void {
	const id = jobIdOf(env);
	if (id === null) return; // nothing to attribute — the poll covers it
	pendingJobIds.add(id);
	let types = pendingTypes.get(id);
	if (!types) {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- notifier bookkeeping, never read reactively
		types = new Set();
		pendingTypes.set(id, types);
	}
	types.add(env.event_type);
	if (timer !== null) clearTimeout(timer);
	timer = setTimeout(flush, DEBOUNCE_MS);
}

function flush(): void {
	timer = null;
	const ids = pendingJobIds;
	const types = pendingTypes;
	pendingJobIds = new Set();
	pendingTypes = new Map();
	for (const listener of listeners) {
		try {
			listener(ids, types);
		} catch (err) {
			// One page's throwing callback must not starve the others.
			console.error('ripperEvents listener failed', err);
		}
	}
}

export function startRipperEvents(): void {
	wsClient.start();
	if (unsubs.length === 0) {
		unsubs = [wsClient.subscribe('ripper.events', onEvent), wsClient.subscribe('transcode.events', onEvent)];
	}
}

export function stopRipperEvents(): void {
	for (const u of unsubs) u();
	unsubs = [];
	if (timer !== null) {
		clearTimeout(timer);
		timer = null;
	}
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- notifier bookkeeping, never read reactively
	pendingJobIds = new Set();
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- notifier bookkeeping, never read reactively
	pendingTypes = new Map();
}

export function onRipperEvent(listener: Listener): () => void {
	listeners.add(listener);
	return () => listeners.delete(listener);
}
