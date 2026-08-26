// Instant status refresh from `ripper.events`. A NOTIFIER, not a data store:
// it holds no job state. It subscribes once to the bare `ripper.events`
// topic, coalesces the job_ids seen within a debounce window, and invokes
// each registered listener once per flush with the accumulated set.
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

type Listener = (jobIds: Set<string>) => void;

const listeners = new Set<Listener>();
let pendingJobIds = new Set<string>();
let timer: ReturnType<typeof setTimeout> | null = null;
let unsub: (() => void) | null = null;

function jobIdOf(env: WSEnvelope): string | null {
	if (env.job_id) return env.job_id;
	const fromPayload = (env.payload as { job_id?: unknown }).job_id;
	return typeof fromPayload === 'string' && fromPayload !== '' ? fromPayload : null;
}

function onEvent(env: WSEnvelope): void {
	const id = jobIdOf(env);
	if (id === null) return; // nothing to attribute — the poll covers it
	pendingJobIds.add(id);
	if (timer !== null) clearTimeout(timer);
	timer = setTimeout(flush, DEBOUNCE_MS);
}

function flush(): void {
	timer = null;
	const ids = pendingJobIds;
	pendingJobIds = new Set();
	for (const listener of listeners) {
		try {
			listener(ids);
		} catch (err) {
			// One page's throwing callback must not starve the others.
			console.error('ripperEvents listener failed', err);
		}
	}
}

export function startRipperEvents(): void {
	wsClient.start();
	if (unsub === null) {
		unsub = wsClient.subscribe('ripper.events', onEvent);
	}
}

export function stopRipperEvents(): void {
	if (unsub !== null) {
		unsub();
		unsub = null;
	}
	if (timer !== null) {
		clearTimeout(timer);
		timer = null;
	}
	pendingJobIds = new Set();
}

export function onRipperEvent(listener: Listener): () => void {
	listeners.add(listener);
	return () => listeners.delete(listener);
}
