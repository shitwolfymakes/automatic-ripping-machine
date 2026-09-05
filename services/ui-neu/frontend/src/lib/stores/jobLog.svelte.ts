// Per-job log feed: one-shot NDJSON snapshot (fetchJobLog) plus an optional
// live tail over the shared WS connection (topic `logs.{job_id}`, event_type
// `log.line`). One instance per mounted view (JobLogPanel, /logs/[job_id]) —
// unlike the module-level rips/resources stores, this is a factory so each
// caller gets its own subscription lifecycle.

import { fetchJobLog, toLogEntry, type LogEntry } from '$lib/api/logs';

export function sortByTime(list: LogEntry[]): LogEntry[] {
	return list
		.map((e, i) => ({ e, i, t: e.timestamp ? Date.parse(e.timestamp) : Number.NaN }))
		.sort((a, b) => {
			if (Number.isNaN(a.t) || Number.isNaN(b.t) || a.t === b.t) return a.i - b.i;
			return a.t - b.t;
		})
		.map((x) => x.e);
}
import { wsClient, type WSEnvelope } from '$lib/api/ws';

const MAX_LIVE_ENTRIES = 2000;

export interface JobLogOptions {
	limit?: number;
}

export function createJobLog(jobId: string, { limit = 200 }: JobLogOptions = {}) {
	let entries = $state<LogEntry[]>([]);
	let loading = $state(false);
	let error = $state<Error | null>(null);
	let live = $state(false);
	let unsub: (() => void) | null = null;

	// Bumped on every live-appended line while a load() is in flight, so the
	// fetch's resolution (which can race a WS line arriving first) prepends
	// onto whatever arrived meanwhile instead of clobbering it.
	let liveArrivedDuringLoad = false;

	async function load(): Promise<void> {
		loading = true;
		error = null;
		liveArrivedDuringLoad = false;
		try {
			// The per-job file is appended in tailer arrival order across the
			// backend, ripper and transcoder files, so a snapshot interleaves
			// services out of time order. Sort by timestamp (stable; undated
			// lines keep their place). Live lines arrive in real time already.
			const fetched = sortByTime(await fetchJobLog(jobId, limit));
			entries = liveArrivedDuringLoad ? [...fetched, ...entries] : fetched;
		} catch (e) {
			error = e instanceof Error ? e : new Error(String(e));
		} finally {
			loading = false;
		}
	}

	function onEnvelope(env: WSEnvelope): void {
		if (env.event_type !== 'log.line') return;
		liveArrivedDuringLoad = true;
		const next = entries.slice();
		next.push(toLogEntry(env.payload));
		if (next.length > MAX_LIVE_ENTRIES) next.splice(0, next.length - MAX_LIVE_ENTRIES);
		entries = next;
	}

	function start(): void {
		if (unsub !== null) return; // idempotent
		unsub = wsClient.subscribe(`logs.${jobId}`, onEnvelope);
		live = true;
	}

	function stop(): void {
		if (unsub !== null) {
			unsub();
			unsub = null;
		}
		live = false;
	}

	return {
		get entries() {
			return entries;
		},
		get loading() {
			return loading;
		},
		get error() {
			return error;
		},
		get live() {
			return live;
		},
		load,
		start,
		stop
	};
}

export type JobLogStore = ReturnType<typeof createJobLog>;
