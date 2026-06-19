import type {
	JobView,
	JobStatus,
	TranscodeTaskView,
	ConfigView
} from '$lib/types/api.gen';
import { apiFetch } from './client';
import { notAvailable } from './_stub';
import { fetchDrives } from './drives';
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

export interface DashboardData {
	db_available: boolean;
	arm_online: boolean;
	active_jobs: JobView[];
	drives_online: number;
	drive_names: Record<string, string>;
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
const TERMINAL_JOB_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>([
	'abandoned',
	'failed'
]);

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
	const [
		configRes,
		jobsRes,
		drivesRes,
		transcodesRes,
		transcoderStatsRes,
		notificationsRes
	] = await Promise.allSettled([
		fetchConfig(),
		fetchJobs(),
		fetchDrives(),
		fetchTranscoderJobs(),
		fetchTranscoderStats(),
		fetchNotificationCount()
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
	for (const d of drives ?? []) {
		driveNames[d.id] = d.display_name ?? d.device_path;
	}

	const activeTranscodes = (transcodes ?? []).filter((t) =>
		IN_PROGRESS_TRANSCODE_STATUSES.has(t.status)
	);

	return {
		// db_available stands in for "backend config read succeeded" — the
		// sidebar uses it to gate drive counts / the ripping toggle.
		db_available: config !== null,
		arm_online: armOnline,
		active_jobs: activeJobs,
		drives_online: drives?.length ?? 0,
		drive_names: driveNames,
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

// v3 has no makemkv-key-check endpoint (the BFF POST /api/dashboard/
// makemkv-key-check is gone). Key validity surfaces via ConfigView's
// makemkv_key_valid/makemkv_key_checked_at on the next dashboard poll instead.
export async function checkMakemkvKey(): Promise<{
	key_valid: boolean;
	checked_at: string | null;
	message: string;
}> {
	notAvailable('MakeMKV key check');
}

// v3 sets the global ripping pause via PATCH /api/config { ripping_paused }.
// The BFF's POST /api/system/ripping-enabled is gone.
export function setRippingEnabled(enabled: boolean): Promise<ConfigView> {
	return apiFetch<ConfigView>('/api/config', {
		method: 'PATCH',
		body: JSON.stringify({ ripping_paused: !enabled })
	});
}
