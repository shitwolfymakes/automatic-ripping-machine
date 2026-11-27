// What a rip writes versus what is ticked: the checkbox meaning, the totals line and the
// warning. Components render these; no decision lives in a template.
import type { JobView, RipInvocation, TrackView } from '$lib/types/api.gen';
import { formatBytes } from '$lib/utils/format';

export type TickMeaning = 'rip-and-transcode' | 'transcode-only' | 'not-ripped';

/** The job states before the rip starts: ticks still decide what rips in per-title mode. */
const PRE_RIP = new Set(['created', 'awaiting_user_id', 'identified', 'awaiting_review']);

type PlanJob = Pick<JobView, 'rip_invocation' | 'status'>;

/** The job's rip mode; a job that does not say rips as one `mkv all` invocation. */
function modeOf(job: PlanJob): RipInvocation {
	return job.rip_invocation ?? 'mkv_all';
}

function isStarted(job: PlanJob): boolean {
	return !PRE_RIP.has(job.status);
}

/** What the title's tick does: rips and transcodes, only transcodes, or was never ripped. */
export function tickMeaning(track: Pick<TrackView, 'status'>, job: PlanJob): TickMeaning {
	if (track.status === 'skipped') return 'not-ripped';
	if (!isStarted(job) && modeOf(job) === 'per_title') return 'rip-and-transcode';
	return 'transcode-only';
}

const TICK_TITLES: Record<TickMeaning, string> = {
	'rip-and-transcode': 'Rip and transcode this title',
	'transcode-only': 'Include this title in the transcode',
	'not-ripped': 'Not ripped: it was unticked when the rip started'
};

/** The checkbox's title text. */
export function tickTitle(meaning: TickMeaning): string {
	return TICK_TITLES[meaning];
}

export interface RipPlanSummary {
	/** Every title of the disc. */
	titles: number;
	/** Titles ticked (not left out of the transcode). */
	ticked: number;
	/** Bytes the rip writes, or null when any counted title has no size. */
	bytes: number | null;
	unticked: number;
	mode: RipInvocation;
	/** The rip has started: the line then only speaks of the transcode. */
	started: boolean;
}

function sizeOf(track: TrackView): number | null {
	return track.size_bytes ?? track.expected_size_bytes ?? null;
}

/** The sum of the sizes, or null when one is unknown (never estimated). */
function totalBytes(tracks: readonly TrackView[]): number | null {
	let sum = 0;
	for (const track of tracks) {
		const size = sizeOf(track);
		if (size == null) return null;
		sum += size;
	}
	return sum;
}

/** The plan of a DVD/Blu-ray rip; null for a CD, a data disc or a whole-disc track. */
export function ripPlanSummary(tracks: readonly TrackView[], job: PlanJob): RipPlanSummary | null {
	if (tracks.length === 0 || tracks.some((t) => t.kind !== 'video_title')) return null;
	const mode = modeOf(job);
	const ticked = tracks.filter((t) => !t.excluded);
	const rips = mode === 'per_title' ? ticked : tracks;
	return {
		titles: tracks.length,
		ticked: ticked.length,
		bytes: totalBytes(rips),
		unticked: tracks.length - ticked.length,
		mode,
		started: isStarted(job)
	};
}

function sizeClause(bytes: number | null): string {
	return bytes == null ? '' : `, about ${formatBytes(bytes)}`;
}

/** The totals line: what the rip writes before Start, what transcodes after. */
export function ripPlanLine(s: RipPlanSummary): string {
	if (s.started) return `${s.ticked} of ${s.titles} titles transcode`;
	if (s.mode === 'per_title') return `Rips ${s.ticked} of ${s.titles} titles${sizeClause(s.bytes)}`;
	return `Rips all ${s.titles} titles${sizeClause(s.bytes)}. ${s.ticked} transcode.`;
}

/** The notice for unticked titles in `mkv all` mode, which still rips them; else null. */
export function ripPlanWarning(s: RipPlanSummary): string | null {
	if (s.mode !== 'mkv_all' || s.unticked === 0) return null;
	const size = s.bytes == null ? '' : ` (about ${formatBytes(s.bytes)})`;
	return `All ${s.titles} titles still rip${size}. Unticked titles are only left out of the transcode.`;
}
