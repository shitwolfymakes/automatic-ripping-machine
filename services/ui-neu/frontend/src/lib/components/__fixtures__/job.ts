import type { JobView, JobDetailView, TrackView } from '$lib/types/api.gen';

const jobDefaults: JobView = {
	id: 'job_1',
	drive_id: 'drv_1',
	disc_type: 'bluray',
	status: 'ripping',
	title: 'Test Movie',
	year: 2024,
	poster_url: null,
	poster_url_manual: null,
	metadata_json: {},
	resumed_from_crash: false,
	rip_progress: null
};

export function createJob(overrides: Partial<JobView> = {}): JobView {
	return { ...jobDefaults, ...overrides };
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
	video_type: null,
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
