import type { JobView, JobStatus, TranscodeTaskView, IsoPrepareView } from '$lib/types/api.gen';
import { fetchConfigView } from './config';
import { fetchDrives } from './drives';
import { fetchIsoPreparing } from './iso';
import { fetchJobs } from './jobs';
import { fetchTranscoderStats, fetchTranscoderJobs } from './transcoder';
import { fetchNotificationCount } from './notifications';

// ---------------------------------------------------------------------------
// Client-side dashboard composition.
//
// v3 has NO single dashboard/BFF endpoint — the legacy `DashboardResponse`
// aggregation is gone. We FAN OUT across the v3 endpoints and compose the
// shape the dashboard store + sidebar components consume. Each field
// degrades independently (Promise.allSettled): one failing endpoint nulls/zeros
// that field instead of taking the whole dashboard down, and the store layer
// (STICKY_FIELDS / TWO_STRIKE_FIELDS) holds last-good values through blips.
// ---------------------------------------------------------------------------

// Transcoder summary as the sidebar reads it. v3's TranscodeStatsView has no
// worker_running/pending fields, so those stay undefined; the dashboard badges
// optional-chain them.
interface TranscoderStats {
	worker_running?: boolean | null;
	pending?: number | null;
}

/** An ISO rip whose ripper is scanning or unpacking the image: no job yet. */
export interface IsoPreparing extends IsoPrepareView {
	iso_name: string;
	iso_kind: IsoSourceKind;
}

/** What a virtual drive rips: an .iso file or a disc folder. */
export type IsoSourceKind = 'iso' | 'folder';

export interface DashboardData {
	db_available: boolean;
	arm_online: boolean;
	active_jobs: JobView[];
	// Physical optical drives only (Decision 11) — a virtual (ISO) drive row
	// isn't a drive an operator can plug/unplug, so it never counts here.
	drives_online: number;
	drive_names: Record<string, string>;
	// drive id -> ISO file name, for the currently-enrolled virtual drives
	// (one per in-flight ISO rip). Lets the dashboard swap the drive chip for
	// an ISO source chip without a second fetch.
	iso_sources: Record<string, string>;
	// drive id -> 'iso' / 'folder' for the same drives, so the source chip
	// says ISO or Folder.
	iso_source_kinds: Record<string, IsoSourceKind>;
	// drive id -> 'iso' / 'folder' for EVERY virtual drive, retired ones
	// included, so a finished ISO job (whose drive is retired) still reads as
	// ISO / Folder (the log list's disc chip).
	drive_source_kinds: Record<string, IsoSourceKind>;
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
}

// Fields whose endpoint can blip independently. A snapshot reports them as
// `null` when their read failed this poll, so the store can hold the last
// good value instead of flickering to an empty map or a zero count.
export const STICKY_FIELDS = [
	'active_jobs',
	'drives_online',
	'drive_names',
	'iso_sources',
	'iso_source_kinds',
	'drive_source_kinds',
	'notification_count',
	'ripping_enabled'
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
		drive_names: s.drive_names ?? {},
		iso_sources: s.iso_sources ?? {},
		iso_source_kinds: s.iso_source_kinds ?? {},
		drive_source_kinds: s.drive_source_kinds ?? {},
		notification_count: s.notification_count ?? 0,
		ripping_enabled: s.ripping_enabled ?? true
	};
}

type DriveList = Awaited<ReturnType<typeof fetchDrives>>;

function settledValue<T>(res: PromiseSettledResult<T>): T | null {
	return res.status === 'fulfilled' ? res.value : null;
}

function orNull<T, R>(value: T | null, fn: (value: T) => R): R | null {
	return value === null ? null : fn(value);
}

function sourceKindOf(drive: DriveList[number]): IsoSourceKind {
	return drive.source_kind === 'folder' ? 'folder' : 'iso';
}

function buildDriveMaps(drives: DriveList) {
	const driveNames: Record<string, string> = {};
	const isoSources: Record<string, string> = {};
	const isoSourceKinds: Record<string, IsoSourceKind> = {};
	const driveSourceKinds: Record<string, IsoSourceKind> = {};
	// `drives` includes retired rows so a finished ISO job keeps its label in
	// drive_names; the live-only maps below skip them.
	for (const d of drives) {
		driveNames[d.id] = d.display_name ?? d.device_path;
		if (d.kind === 'virtual') driveSourceKinds[d.id] = sourceKindOf(d);
		if (d.kind === 'virtual' && d.lifecycle !== 'retired') {
			// display_name is the ISO's file name for a virtual drive; fall back
			// to the last path segment of source_path if it's ever missing.
			isoSources[d.id] = d.display_name ?? d.source_path?.split('/').pop() ?? d.source_path ?? d.device_path;
			isoSourceKinds[d.id] = sourceKindOf(d);
		}
	}
	return { driveNames, isoSources, isoSourceKinds, driveSourceKinds };
}

function countOpticalDrives(drives: DriveList): number {
	return drives.filter((d) => d.kind === 'optical' && d.lifecycle !== 'retired').length;
}

function selectPreparing(
	preparing: IsoPrepareView[],
	isoSources: Record<string, string>,
	isoSourceKinds: Record<string, IsoSourceKind>,
	activeJobs: JobView[]
): IsoPreparing[] {
	// Only a live ISO rip that has no active job yet; once identify creates
	// the job, the job's own row takes over.
	const jobDrives = new Set(activeJobs.map((j) => j.drive_id));
	return preparing
		.filter((p) => p.drive_id in isoSources && !jobDrives.has(p.drive_id))
		.map((p) => ({ ...p, iso_name: isoSources[p.drive_id], iso_kind: isoSourceKinds[p.drive_id] }));
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
	const { driveNames, isoSources, isoSourceKinds, driveSourceKinds } = buildDriveMaps(drives ?? []);
	const preparing = selectPreparing(settledValue(preparingRes) ?? [], isoSources, isoSourceKinds, activeJobs);

	return {
		// db_available stands in for "backend config read succeeded" — the
		// sidebar uses it to gate drive counts / the ripping toggle.
		db_available: config !== null,
		arm_online: armOnline,
		active_jobs: jobs === null ? null : activeJobs,
		drives_online: orNull(drives, countOpticalDrives),
		drive_names: orNull(drives, () => driveNames),
		iso_sources: orNull(drives, () => isoSources),
		iso_source_kinds: orNull(drives, () => isoSourceKinds),
		drive_source_kinds: orNull(drives, () => driveSourceKinds),
		preparing,
		notification_count: notifications === null ? null : (notifications.unseen ?? 0),
		ripping_enabled: config === null ? null : !config.ripping_paused,
		makemkv_key_valid: config?.makemkv_key_valid ?? null,
		makemkv_key_checked_at: config?.makemkv_key_checked_at ?? null,
		transcoder_online: transcoderOnline,
		// v3 TranscodeStatsView has no worker_running/pending — surface nothing
		// rather than a wrong value; the badges optional-chain these.
		transcoder_stats: transcoderStatsRes.status === 'fulfilled' ? {} : null,
		active_transcodes: activeTranscodesOf(transcodes)
	};
}
