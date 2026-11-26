import type { JobView, JobStatus, TranscodeTaskView, TranscodeStatsView, IsoPrepareView } from '$lib/types/api.gen';
import { taskCount } from '$lib/transcode/stats';
import { fetchConfigView } from './config';
import { fetchDrives } from './drives';
import { fetchIsoPreparing } from './iso';
import { liveSource, type LiveSourceDrive } from '$lib/drives/summary';
import { fetchJobs } from './jobs';
import { fetchTranscoderStats, fetchTranscoderJobs } from './transcoder';
import { fetchNotificationCount } from './notifications';

// ---------------------------------------------------------------------------
// Client-side dashboard composition.
//
// There is no single dashboard endpoint, so this fans out across the v3 endpoints and composes the
// shape the dashboard store + sidebar components consume. Each field
// degrades independently (Promise.allSettled): one failing endpoint nulls/zeros
// that field instead of taking the whole dashboard down, and the store layer
// (STICKY_FIELDS / TWO_STRIKE_FIELDS) holds last-good values through blips.
// ---------------------------------------------------------------------------

// Transcoder summary as the header reads it: how many transcode tasks are
// queued.
interface TranscoderStats {
	pending: number;
}

/** An ISO rip whose ripper is scanning or unpacking the image: no job yet. */
export interface IsoPreparing extends IsoPrepareView {
	drive: LiveSourceDrive;
}

/** What a virtual drive rips: an .iso file or a disc folder. */
export type IsoSourceKind = 'iso' | 'folder';

/** One drive as every dashboard consumer reads it. */
export interface DriveSummary {
	/** display_name, else the last segment of source_path, else device_path. */
	name: string;
	kind: 'optical' | 'virtual';
	/** What a virtual drive reads from; null for an optical drive. */
	source: IsoSourceKind | null;
	retired: boolean;
}

export interface DashboardData {
	db_available: boolean;
	arm_online: boolean;
	active_jobs: JobView[];
	// Physical optical drives only (Decision 11) — a virtual (ISO) drive row
	// isn't a drive an operator can plug/unplug, so it never counts here.
	drives_online: number;
	// drive id -> summary for EVERY drive, retired ones included, so a
	// finished ISO job (whose drive is retired) keeps its name and source kind.
	drives: Record<string, DriveSummary>;
	// ISO rips with no job yet (scanning / unpacking the image), so the
	// dashboard can show them before identify creates the job.
	preparing: IsoPreparing[];
	notification_count: number;
	ripping_enabled: boolean;
	makemkv_key_valid: boolean | null;
	makemkv_key_checked_at: string | null;
	transcoder_online: boolean;
	transcoder_stats: TranscoderStats | null;
	active_transcodes: TranscodeTaskView[];
	// Review countdown length (config manual_wait_seconds); 60 when unread.
	review_wait_seconds: number;
}

// Fields whose endpoint can blip independently. A snapshot reports them as
// `null` when their read failed this poll, so the store can hold the last
// good value instead of flickering to an empty map or a zero count.
export const STICKY_FIELDS = [
	'active_jobs',
	'drives_online',
	'drives',
	'notification_count',
	'ripping_enabled',
	'review_wait_seconds'
] as const satisfies readonly (keyof DashboardData)[];

type StickyField = (typeof STICKY_FIELDS)[number];

export type DashboardSnapshot = Omit<DashboardData, StickyField> & {
	[K in StickyField]: DashboardData[K] | null;
};

// JobView.status values that mean "in-flight" (non-terminal). v3 GET /api/jobs
// has no "all active" status_filter, so we fetch the full list and filter here.
const TERMINAL_JOB_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>(['abandoned', 'failed']);

function isActiveJob(job: JobView): boolean {
	// `ripped` is a completed rip but still pre-transcode/finalize, so keep it
	// visible on the dashboard's active lanes. Only truly terminal jobs drop.
	return !TERMINAL_JOB_STATUSES.has(job.status);
}

const IN_PROGRESS_TRANSCODE_STATUSES = new Set(['queued', 'in_progress']);

/** The dashboard with every failed read's fields filled with empty defaults. */
export async function fetchDashboard(): Promise<DashboardData> {
	const s = await fetchDashboardSnapshot();
	return {
		...s,
		active_jobs: s.active_jobs ?? [],
		drives_online: s.drives_online ?? 0,
		drives: s.drives ?? {},
		notification_count: s.notification_count ?? 0,
		ripping_enabled: s.ripping_enabled ?? true,
		review_wait_seconds: s.review_wait_seconds ?? 60
	};
}

type DriveList = Awaited<ReturnType<typeof fetchDrives>>;

function settledValue<T>(res: PromiseSettledResult<T>): T | null {
	return res.status === 'fulfilled' ? res.value : null;
}

function orNull<T, R>(value: T | null, fn: (value: T) => R): R | null {
	return value === null ? null : fn(value);
}

type DriveRow = DriveList[number];

function sourceKindOf(drive: DriveRow): IsoSourceKind {
	return drive.source_kind === 'folder' ? 'folder' : 'iso';
}

/** The last non-empty segment of a path, or undefined when it has none. */
function baseName(path: string | null | undefined): string | undefined {
	return path?.split('/').filter(Boolean).pop();
}

function driveNameOf(drive: DriveRow): string {
	return drive.display_name ?? baseName(drive.source_path) ?? drive.device_path;
}

function summarizeDrive(drive: DriveRow): DriveSummary {
	const virtual = drive.kind === 'virtual';
	return {
		name: driveNameOf(drive),
		kind: virtual ? 'virtual' : 'optical',
		source: virtual ? sourceKindOf(drive) : null,
		retired: drive.lifecycle === 'retired'
	};
}

function summarizeDrives(drives: DriveList): Record<string, DriveSummary> {
	return Object.fromEntries(drives.map((d) => [d.id, summarizeDrive(d)]));
}

function countOpticalDrives(drives: DriveList): number {
	return drives.filter((d) => d.kind === 'optical' && d.lifecycle !== 'retired').length;
}

function selectPreparing(
	preparing: IsoPrepareView[],
	drives: Record<string, DriveSummary>,
	activeJobs: JobView[]
): IsoPreparing[] {
	// Only a live ISO rip that has no active job yet; once identify creates
	// the job, the job's own row takes over.
	const jobDrives = new Set(activeJobs.map((j) => j.drive_id));
	return preparing.flatMap((p) => {
		const drive = liveSource(drives[p.drive_id]);
		return drive && !jobDrives.has(p.drive_id) ? [{ ...p, drive }] : [];
	});
}

function transcoderStatsOf(stats: TranscodeStatsView): TranscoderStats {
	return { pending: taskCount(stats, 'queued') };
}

function activeTranscodesOf(transcodes: TranscodeTaskView[] | null): TranscodeTaskView[] {
	return (transcodes ?? []).filter((t) => IN_PROGRESS_TRANSCODE_STATUSES.has(t.status));
}

/**
 * Compose the dashboard from independent v3 endpoints. Uses Promise.allSettled
 * so a single failing endpoint degrades only its field(s), which come back
 * `null` (see STICKY_FIELDS); `arm_online` / `transcoder_online` are derived
 * from which fetches settled.
 */
export async function fetchDashboardSnapshot(): Promise<DashboardSnapshot> {
	const [configRes, jobsRes, drivesRes, transcodesRes, transcoderStatsRes, notificationsRes, preparingRes] =
		await Promise.allSettled([
			fetchConfigView(),
			fetchJobs(),
			fetchDrives({ includeRetired: true }),
			fetchTranscoderJobs(),
			fetchTranscoderStats(),
			fetchNotificationCount(),
			fetchIsoPreparing()
		]);

	const config = settledValue(configRes);
	const jobs = settledValue(jobsRes);
	const drives = settledValue(drivesRes);
	const transcodes = settledValue(transcodesRes);
	const notifications = settledValue(notificationsRes);

	// ARM (backend/ripper) is reachable if config + jobs both resolved — those
	// are the core backend reads. Transcoder is reachable if its list resolved.
	const armOnline = configRes.status === 'fulfilled' && jobsRes.status === 'fulfilled';
	const transcoderOnline = transcodesRes.status === 'fulfilled';

	const activeJobs = (jobs ?? []).filter(isActiveJob);
	const driveSummaries = summarizeDrives(drives ?? []);
	const preparing = selectPreparing(settledValue(preparingRes) ?? [], driveSummaries, activeJobs);

	return {
		// db_available stands in for "backend config read succeeded" — the
		// sidebar uses it to gate drive counts / the ripping toggle.
		db_available: config !== null,
		arm_online: armOnline,
		active_jobs: jobs === null ? null : activeJobs,
		drives_online: orNull(drives, countOpticalDrives),
		drives: orNull(drives, () => driveSummaries),
		preparing,
		notification_count: notifications === null ? null : (notifications.unseen ?? 0),
		ripping_enabled: config === null ? null : !config.ripping_paused,
		review_wait_seconds: config === null ? null : (config.manual_wait_seconds ?? 60),
		makemkv_key_valid: config?.makemkv_key_valid ?? null,
		makemkv_key_checked_at: config?.makemkv_key_checked_at ?? null,
		transcoder_online: transcoderOnline,
		transcoder_stats: orNull(settledValue(transcoderStatsRes), transcoderStatsOf),
		active_transcodes: activeTranscodesOf(transcodes)
	};
}
