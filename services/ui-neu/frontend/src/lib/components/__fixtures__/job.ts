import type { JobView, JobDetailView, TrackView, JobStatus, JobActions } from '$lib/types/api.gen';

// Test mirror of arm_common job_actions_for(). Keyed on JobStatus so a new
// backend status fails `npm run check` here too.
const ACTIONS: Record<JobStatus, JobActions> = {
	created: { can_resolve: false, can_apply: false, can_abandon: true, can_delete: false },
	awaiting_user_id: { can_resolve: true, can_apply: true, can_abandon: true, can_delete: false },
	identified: { can_resolve: true, can_apply: true, can_abandon: true, can_delete: false },
	awaiting_review: { can_resolve: true, can_apply: true, can_abandon: true, can_delete: false },
	ripping: { can_resolve: false, can_apply: false, can_abandon: true, can_delete: false },
	ripped: { can_resolve: true, can_apply: true, can_abandon: false, can_delete: true },
	ripped_partial: { can_resolve: true, can_apply: true, can_abandon: false, can_delete: true },
	ripped_awaiting_identify: { can_resolve: true, can_apply: true, can_abandon: false, can_delete: true },
	abandoned: { can_resolve: false, can_apply: false, can_abandon: false, can_delete: true },
	failed: { can_resolve: false, can_apply: false, can_abandon: false, can_delete: true }
};

export function actionsFor(status: JobStatus): JobActions {
	return { ...ACTIONS[status] };
}

const jobDefaults: JobView = {
	id: 'job_1',
	drive_id: 'drv_1',
	disc_type: 'bluray',
	status: 'ripping',
	actions: actionsFor('ripping'),
	title: 'Test Movie',
	year: 2024,
	poster_url: null,
	poster_url_manual: null,
	metadata_json: {},
	resumed_from_crash: false,
	rip_progress: null,
	looks_episodic: false,
	has_series: false
};

export function createJob(overrides: Partial<JobView> = {}): JobView {
	const status = overrides.status ?? jobDefaults.status;
	return { ...jobDefaults, actions: actionsFor(status), ...overrides };
}

const trackDefaults: TrackView = {
	id: 'trk_1',
	job_id: 'job_1',
	kind: 'video_title',
	index: 0,
	source_ref: 't00.mkv',
	status: 'queued',
	output_path: null,
	size_bytes: null,
	expected_size_bytes: null,
	duration_seconds: 2750,
	expected_duration_seconds: null,
	attempts: 0,
	last_error: null,
	label: null,
	role: null,
	edition: null,
	excluded: false,
	custom_filename: null,
	title: null,
	year: null,
	imdb_id: null,
	poster_url: null,
	episode_number: null,
	episode_name: null
};

export function createTrack(overrides: Partial<TrackView> = {}): TrackView {
	return { ...trackDefaults, ...overrides };
}

export function createJobDetail(overrides: Partial<JobDetailView> = {}): JobDetailView {
	const { tracks = [], fingerprints = [], ...jobOverrides } = overrides;
	return { job: createJob(jobOverrides as Partial<JobView>), tracks, fingerprints };
}
