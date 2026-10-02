import type { JobView, JobStatus, TranscodeTaskView, ConfigView, IsoPrepareView } from '$lib/types/api.gen';
import { apiFetch } from './client';
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
export interface TranscoderStats {
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

// JobView.status values that mean "in-flight" (non-terminal). v3 GET /api/jobs
// has no "all active" status_filter, so we fetch the full list and filter here.
const TERMINAL_JOB_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>(['abandoned', 'failed']);

function isActiveJob(job: JobView): boolean {
	// `ripped` is a completed rip but still pre-transcode/finalize, so keep it
	// visible on the dashboard's active lanes. Only truly terminal jobs drop.
	return !TERMINAL_JOB_STATUSES.has(job.status);
}

const IN_PROGRESS_TRANSCODE_STATUSES = new Set(['queued', 'in_progress']);

function fetchConfig(): Promise<ConfigView> {
	return apiFetch<ConfigView>('/api/config');
}

/**
 * Compose the dashboard from independent v3 endpoints. Uses Promise.allSettled
 * so a single failing endpoint degrades only its field(s); `arm_online` /
 * `transcoder_online` are derived from which fetches settled.
 */
export async function fetchDashboard(): Promise<DashboardData> {
	const [configRes, jobsRes, drivesRes, transcodesRes, transcoderStatsRes, notificationsRes, preparingRes] =
		await Promise.allSettled([
			fetchConfig(),
			fetchJobs(),
			fetchDrives({ includeRetired: true }),
			fetchTranscoderJobs(),
			fetchTranscoderStats(),
			fetchNotificationCount(),
			fetchIsoPreparing()
		]);

	const config = configRes.status === 'fulfilled' ? configRes.value : null;
	const jobs = jobsRes.status === 'fulfilled' ? jobsRes.value : null;
	const drives = drivesRes.status === 'fulfilled' ? drivesRes.value : null;
	const transcodes = transcodesRes.status === 'fulfilled' ? transcodesRes.value : null;
	const notifications = notificationsRes.status === 'fulfilled' ? notificationsRes.value : null;

	// ARM (backend/ripper) is reachable if config + jobs both resolved — those
	// are the core backend reads. Transcoder is reachable if its list resolved.
	const armOnline = configRes.status === 'fulfilled' && jobsRes.status === 'fulfilled';
	const transcoderOnline = transcodesRes.status === 'fulfilled';

	const activeJobs = (jobs ?? []).filter(isActiveJob);

	const driveNames: Record<string, string> = {};
	const isoSources: Record<string, string> = {};
	const isoSourceKinds: Record<string, IsoSourceKind> = {};
	// `drives` includes retired rows so a finished ISO job keeps its label in
	// drive_names; the live-only maps below skip them.
	for (const d of drives ?? []) {
		driveNames[d.id] = d.display_name ?? d.device_path;
		if (d.kind === 'virtual' && d.lifecycle !== 'retired') {
			// display_name is the ISO's file name for a virtual drive; fall back
			// to the last path segment of source_path if it's ever missing.
			isoSources[d.id] = d.display_name ?? d.source_path?.split('/').pop() ?? d.source_path ?? d.device_path;
			isoSourceKinds[d.id] = d.source_kind === 'folder' ? 'folder' : 'iso';
		}
	}

	// Only a live ISO rip that has no active job yet; once identify creates
	// the job, the job's own row takes over.
	const jobDrives = new Set(activeJobs.map((j) => j.drive_id));
	const preparing: IsoPreparing[] = (preparingRes.status === 'fulfilled' ? preparingRes.value : [])
		.filter((p) => p.drive_id in isoSources && !jobDrives.has(p.drive_id))
		.map((p) => ({ ...p, iso_name: isoSources[p.drive_id], iso_kind: isoSourceKinds[p.drive_id] }));

	const activeTranscodes = (transcodes ?? []).filter((t) => IN_PROGRESS_TRANSCODE_STATUSES.has(t.status));

	return {
		// db_available stands in for "backend config read succeeded" — the
		// sidebar uses it to gate drive counts / the ripping toggle.
		db_available: config !== null,
		arm_online: armOnline,
		active_jobs: activeJobs,
		drives_online: (drives ?? []).filter((d) => d.kind === 'optical' && d.lifecycle !== 'retired').length,
		drive_names: driveNames,
		iso_sources: isoSources,
		iso_source_kinds: isoSourceKinds,
		preparing,
		notification_count: notifications?.unseen ?? 0,
		ripping_enabled: config ? !config.ripping_paused : true,
		makemkv_key_valid: config?.makemkv_key_valid ?? null,
		makemkv_key_checked_at: config?.makemkv_key_checked_at ?? null,
		transcoder_online: transcoderOnline,
		// v3 TranscodeStatsView has no worker_running/pending — surface nothing
		// rather than a wrong value; the badges optional-chain these.
		transcoder_stats: transcoderStatsRes.status === 'fulfilled' ? {} : null,
		active_transcodes: activeTranscodes
	};
}

// The Pause toggle means "hold discs for review": pausing lets discs scan +
// identify and then parks each in AWAITING_REVIEW indefinitely. The backend
// only PARKS (rather than rejecting with 409) when BOTH ripping_paused AND
// hold_for_review are set — see ripper.py identify(). Un-pausing clears both
// and resumes straight-through ripping; config.py gives held discs a fresh
// countdown on the ripping_paused ON->OFF transition so they don't stampede.
export function setRippingEnabled(enabled: boolean): Promise<ConfigView> {
	return apiFetch<ConfigView>('/api/config', {
		method: 'PATCH',
		body: JSON.stringify({ ripping_paused: !enabled, hold_for_review: !enabled })
	});
}
