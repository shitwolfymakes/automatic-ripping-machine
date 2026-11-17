// Feed adapters: turn the rip and transcode progress messages into one
// LiveSample shape. Pure functions with no store or socket knowledge; the
// live store owns the subscriptions and calls these per message.

/** One progress reading for a job; each field is null when not reported. */
export interface LiveSample {
	pct: number | null;
	etaSeconds: number | null;
	fps: number | null;
	avgFps: number | null;
	pass: number | null;
	bytesDone: number | null;
	bytesTotal: number | null;
	rateBps: number | null;
	phase: string | null;
	trackId: string | null;
}

type Payload = Record<string, unknown>;

interface RipBaseline {
	trackId: string | null;
	atMs: number;
	atPct: number;
}

// Mask early per-track samples: the first tick has no rate yet, and the
// second can mislead if the drive stalls briefly.
const ETA_MIN_ELAPSED_MS = 5_000;
const ETA_MIN_DELTA = 0.5;
const ESTIMATE_MIN_ELAPSED_SECONDS = 30;

function num(value: unknown): number | null {
	return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function str(value: unknown): string | null {
	return typeof value === 'string' ? value : null;
}

const EMPTY_SAMPLE: LiveSample = {
	pct: null,
	etaSeconds: null,
	fps: null,
	avgFps: null,
	pass: null,
	bytesDone: null,
	bytesTotal: null,
	rateBps: null,
	phase: null,
	trackId: null
};

function byteEta(sample: LiveSample): number | null {
	const { rateBps, bytesTotal, bytesDone } = sample;
	if (rateBps === null || rateBps <= 0 || bytesTotal === null || bytesDone === null) return null;
	return Math.round(Math.max(0, bytesTotal - bytesDone) / rateBps);
}

function isStaleBaseline(baseline: RipBaseline, trackId: string | null, pct: number): boolean {
	return baseline.trackId !== trackId || pct < baseline.atPct - 1;
}

function percentEta(baseline: RipBaseline, pct: number, now: number): number | null {
	const elapsedMs = now - baseline.atMs;
	const pctDelta = pct - baseline.atPct;
	if (elapsedMs <= ETA_MIN_ELAPSED_MS || pctDelta <= ETA_MIN_DELTA) return null;
	return Math.round(Math.max(0, 100 - pct) / (pctDelta / elapsedMs) / 1000);
}

function readRip(payload: Payload): LiveSample {
	return {
		...EMPTY_SAMPLE,
		pct: num(payload.progress_pct),
		etaSeconds: num(payload.eta_seconds),
		bytesDone: num(payload.bytes_done),
		bytesTotal: num(payload.bytes_total),
		rateBps: num(payload.rate_bps),
		phase: str(payload.phase),
		trackId: str(payload.track_id)
	};
}

/**
 * A rip feed for one job. It keeps its own percent baseline, so the store
 * creates one per job. The ETA is the ripper's published one, else the byte
 * ETA, else one measured from the percent since the baseline.
 */
export function createRipFeed(): (payload: Payload, now: number) => LiveSample {
	let baseline: RipBaseline | null = null;
	return (payload, now) => {
		const sample = readRip(payload);
		const { pct, trackId } = sample;
		const published = sample.etaSeconds ?? byteEta(sample);
		if (pct === null) return { ...sample, etaSeconds: published };
		if (baseline === null || isStaleBaseline(baseline, trackId, pct)) {
			baseline = { trackId, atMs: now, atPct: pct };
			return { ...sample, etaSeconds: published };
		}
		return { ...sample, etaSeconds: published ?? percentEta(baseline, pct, now) };
	};
}

/** A transcode progress message as a sample. */
export function transcodeSample(payload: Payload): LiveSample {
	return {
		...EMPTY_SAMPLE,
		pct: num(payload.progress_pct),
		etaSeconds: num(payload.eta_seconds),
		fps: num(payload.fps),
		avgFps: num(payload.avg_fps),
		pass: num(payload.pass)
	};
}

/**
 * Seconds left, estimated from when the job started and how far along it is.
 * Null when there is no start, the percent is outside (0, 100), or under 30 s
 * have passed (too early to extrapolate).
 */
export function estimateEtaSeconds(
	startedAt: string | null | undefined,
	pct: number | null | undefined,
	now: number
): number | null {
	if (!startedAt || pct == null || pct <= 0 || pct >= 100) return null;
	const elapsedSeconds = (now - new Date(startedAt).getTime()) / 1000;
	if (elapsedSeconds < ESTIMATE_MIN_ELAPSED_SECONDS) return null;
	return (elapsedSeconds * (100 - pct)) / pct;
}
