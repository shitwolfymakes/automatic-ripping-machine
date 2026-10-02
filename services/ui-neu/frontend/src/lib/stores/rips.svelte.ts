// Live rip progress, keyed by job_id. Components read
// `ripProgress.value[jobId]?.progress_pct` to render the bar and
// `?.eta_seconds` for the ETA. The backend publishes on
// `ripper.progress.{job_id}` with `{track_id, progress_pct}`; ETA is computed
// here on the receiving side (matches the legacy UI's approach).
//
// Ported from the removed Vue UI's Pinia rips store into ui-neu's Svelte-5
// runes idiom (module-level $state, like lib/stores/toast.svelte.ts).

import { wsClient, type WSEnvelope } from '$lib/api/ws';
import { formatBytes } from '$lib/utils/format';

interface RipperProgressPayload {
	track_id: string;
	progress_pct: number;
	// Present on byte copies (the full-disc dump of an ISO or data disc).
	bytes_done?: number | null;
	bytes_total?: number | null;
	rate_bps?: number | null;
}

interface RipBaseline {
	// Anchored on the first tick of a given track, used to compute pct/sec.
	trackId: string;
	atMs: number;
	atPct: number;
}

export interface RipLiveProgress {
	track_id: string;
	progress_pct: number;
	// Null until we've seen ≥1 follow-up tick for the same track and the
	// signal is past the masking threshold. Resets to null when the track
	// changes. A byte copy that reports its rate gets an ETA straight away.
	eta_seconds: number | null;
	bytes_done: number | null;
	bytes_total: number | null;
	rate_bps: number | null;
}

// Mask early per-track samples — the first tick has no rate yet, and the
// second can mislead if the drive stalls briefly. Matches the legacy
// "wait a bit before showing ETA" behaviour.
const ETA_MIN_ELAPSED_MS = 5_000;
const ETA_MIN_DELTA = 0.5;

// Module-level rune state. `.value` is read in components for reactivity.
export const ripProgress = $state<{ value: Record<string, RipLiveProgress> }>({ value: {} });

// Non-reactive bookkeeping — kept off the rune so reads stay clean.
const baselines: Record<string, RipBaseline> = {};
const unsubs: Record<string, () => void> = {};

export function startWS(): void {
	wsClient.start();
}

export function stopWS(): void {
	for (const id of Object.keys(unsubs)) {
		unsubs[id]();
		delete unsubs[id];
	}
	for (const id of Object.keys(baselines)) delete baselines[id];
	ripProgress.value = {};
}

/**
 * Subscribe to `ripper.progress.{job_id}` for exactly the given ripping jobs;
 * unsubscribe (and drop live state) for any job no longer in the set.
 */
export function reconcileSubscriptions(activeRippingJobIds: string[]): void {
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- local lookup, never stored
	const wanted = new Set(activeRippingJobIds);
	for (const id of Object.keys(unsubs)) {
		if (!wanted.has(id)) {
			unsubs[id]();
			delete unsubs[id];
			delete baselines[id];
			const next = { ...ripProgress.value };
			delete next[id];
			ripProgress.value = next;
		}
	}
	for (const id of wanted) {
		if (!(id in unsubs)) {
			unsubs[id] = wsClient.subscribe(`ripper.progress.${id}`, (env) => onProgress(id, env));
		}
	}
}

export function onProgress(jobId: string, env: WSEnvelope): void {
	const payload = env.payload as unknown as RipperProgressPayload;
	const now = Date.now();
	const bytes = {
		bytes_done: payload.bytes_done ?? null,
		bytes_total: payload.bytes_total ?? null,
		rate_bps: payload.rate_bps ?? null
	};
	const byteEta =
		bytes.rate_bps && bytes.rate_bps > 0 && bytes.bytes_total != null && bytes.bytes_done != null
			? Math.round(Math.max(0, bytes.bytes_total - bytes.bytes_done) / bytes.rate_bps)
			: null;
	const baseline = baselines[jobId];
	// First tick for this track (or track changed) → reset baseline; ETA stays
	// null until enough has accumulated. Also reset on a sustained backwards
	// jump (>1 pp) — defensive against a non-monotonic sequence under a stable
	// track_id; without it pctDelta goes negative and ETA hangs at null.
	if (baseline === undefined || baseline.trackId !== payload.track_id || payload.progress_pct < baseline.atPct - 1) {
		baselines[jobId] = { trackId: payload.track_id, atMs: now, atPct: payload.progress_pct };
		ripProgress.value = {
			...ripProgress.value,
			[jobId]: { track_id: payload.track_id, progress_pct: payload.progress_pct, eta_seconds: byteEta, ...bytes }
		};
		return;
	}
	const elapsedMs = now - baseline.atMs;
	const pctDelta = payload.progress_pct - baseline.atPct;
	let eta: number | null = null;
	if (elapsedMs > ETA_MIN_ELAPSED_MS && pctDelta > ETA_MIN_DELTA) {
		const pctPerMs = pctDelta / elapsedMs;
		const remainingPct = Math.max(0, 100 - payload.progress_pct);
		eta = Math.round(remainingPct / pctPerMs / 1000);
	}
	ripProgress.value = {
		...ripProgress.value,
		[jobId]: { track_id: payload.track_id, progress_pct: payload.progress_pct, eta_seconds: byteEta ?? eta, ...bytes }
	};
}

/** "12.3 GB of 20.9 GB · 45.1 MB/s" for a byte copy, or null when none was reported. */
export function formatTransfer(live: RipLiveProgress | null | undefined): string | null {
	if (!live || live.bytes_done == null) return null;
	const parts = [
		live.bytes_total != null
			? `${formatBytes(live.bytes_done)} of ${formatBytes(live.bytes_total)}`
			: formatBytes(live.bytes_done)
	];
	if (live.rate_bps != null && live.rate_bps > 0) parts.push(`${formatBytes(live.rate_bps)}/s`);
	return parts.join(' · ');
}

export function formatEta(seconds: number): string {
	if (seconds < 60) return '< 1m';
	const h = Math.floor(seconds / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	const s = seconds % 60;
	if (h > 0) return `${h}h ${m}m`;
	if (m >= 5) return `${m}m`;
	return `${m}m ${s}s`;
}
