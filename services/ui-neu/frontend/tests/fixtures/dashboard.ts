import type { DashboardData } from '$lib/api/dashboard';
import type { JobView } from '$lib/types/api.gen';

export const emptyDashboard: DashboardData = {
	db_available: true,
	arm_online: true,
	active_jobs: [],
	drives_online: 0,
	drive_names: {},
	iso_sources: {},
	iso_source_kinds: {},
	preparing: [],
	notification_count: 0,
	ripping_enabled: true,
	makemkv_key_valid: null,
	makemkv_key_checked_at: null,
	transcoder_online: true,
	transcoder_stats: null,
	active_transcodes: []
};

// GET /api/jobs answers a plain JobView[] page (the total rides in the
// X-Total-Count header, absent here, so the page falls back to the length).
export const emptyJobs: JobView[] = [];

export const emptyStats = {
	total: 0,
	success: 0,
	failed: 0,
	pending: 0
};
