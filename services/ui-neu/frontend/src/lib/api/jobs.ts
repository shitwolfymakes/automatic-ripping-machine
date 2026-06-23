import type {
	JobView,
	JobDetailView,
	TrackEditRequest,
	JobUpdateRequest,
	BulkDeleteJobsResponse,
	MetadataSearchResponse,
	MetadataReleaseDetail,
	JobNamingPreviewResponse,
	NamingPreviewResponse,
	NamingValidateResponse,
	NamingVariablesResponse,
	MediaType,
	ResolveResponse,
	ApplySessionResponse,
	ManualTriggerRequest,
	ManualTriggerResponse
} from '$lib/types/api.gen';
import { apiFetch, post } from './client';
import { notAvailable } from './_stub';

// ---------------------------------------------------------------------------
// Job listing / detail (EXISTS in v3)
// ---------------------------------------------------------------------------

// v3 GET /api/jobs supports status/drive_id/limit/offset only. The BFF's
// page/per_page/search/sort/video_type/disctype/days are gone; we keep a thin
// local param type so callers compile, mapping page→offset where we can and
// silently dropping the unsupported filters (the screens that used them are
// guarded off in Tier C).
export interface FetchJobsParams {
	status?: string;
	drive_id?: string;
	limit?: number;
	offset?: number;
}

export function fetchJobs(params?: FetchJobsParams): Promise<JobView[]> {
	const query = new URLSearchParams();
	if (params?.status) query.set('status', params.status);
	if (params?.drive_id) query.set('drive_id', params.drive_id);
	if (params?.limit !== undefined) query.set('limit', String(params.limit));
	if (params?.offset !== undefined) query.set('offset', String(params.offset));
	const qs = query.toString();
	return apiFetch<JobView[]>(`/api/jobs${qs ? `?${qs}` : ''}`);
}

export function fetchJob(id: string): Promise<JobDetailView> {
	return apiFetch<JobDetailView>(`/api/jobs/${id}`);
}

export function abandonJob(id: string): Promise<JobView> {
	return apiFetch<JobView>(`/api/jobs/${id}/abandon`, { method: 'POST' });
}

export function deleteJob(id: string, deleteRaw = false): Promise<void> {
	const qs = deleteRaw ? '?delete_raw=true' : '';
	return apiFetch<void>(`/api/jobs/${id}${qs}`, { method: 'DELETE' });
}

export function bulkDeleteJobs(params: { job_ids?: string[]; status?: string }): Promise<BulkDeleteJobsResponse> {
	return apiFetch<BulkDeleteJobsResponse>('/api/jobs', {
		method: 'DELETE',
		body: JSON.stringify({ job_ids: params.job_ids ?? null, status: params.status ?? null })
	});
}

// ---------------------------------------------------------------------------
// Job / track edits — the v3 bulk-PATCH (FIELD-MISMATCH delta)
// ---------------------------------------------------------------------------
//
// v3 collapses every per-job and per-track edit into ONE atomic call:
//   PATCH /api/jobs/{job_id}  body: JobUpdateRequest
//     { poster_url_manual?, tracks?: TrackEditRequest[] }
// A single-track edit is wrapped into the `tracks` array; the BFF's dedicated
// /tracks/:id endpoints no longer exist. `track_id` selects the row, every
// other field is an optional operator edit (omitted=untouched, null=clear).

export function patchJob(jobId: string, body: JobUpdateRequest): Promise<JobView> {
	return apiFetch<JobView>(`/api/jobs/${jobId}`, {
		method: 'PATCH',
		body: JSON.stringify(body)
	});
}

// Single-track title edit → wrap into the bulk-PATCH tracks array.
export function updateTrackTitle(
	jobId: string,
	trackId: string,
	data: Omit<TrackEditRequest, 'track_id'>
): Promise<JobView> {
	return patchJob(jobId, { tracks: [{ track_id: trackId, ...data }] });
}

// Clear the operator title override (null = clear in v3).
export function clearTrackTitle(jobId: string, trackId: string): Promise<JobView> {
	return patchJob(jobId, {
		tracks: [{ track_id: trackId, title: null, year: null, imdb_id: null, poster_url: null }]
	});
}

// Generic per-track field edit → same bulk-PATCH wrap.
export function updateTrack(
	jobId: string,
	trackId: string,
	data: Omit<TrackEditRequest, 'track_id'>
): Promise<JobView> {
	return patchJob(jobId, { tracks: [{ track_id: trackId, ...data }] });
}

// Job-level edit. v3 only accepts poster_url_manual on the JOB (title/year live
// behind identify/resolve). Pass through whatever maps; the rest is dropped.
export function updateJobTitle(jobId: string, data: { poster_url_manual?: string | null }): Promise<JobView> {
	return patchJob(jobId, { poster_url_manual: data.poster_url_manual ?? null });
}

export function updateJobConfig(jobId: string, data: JobUpdateRequest): Promise<JobView> {
	return patchJob(jobId, data);
}

// ---------------------------------------------------------------------------
// Identify / resolve + apply-session (EXISTS in v3)
// ---------------------------------------------------------------------------

// v3 POST /api/jobs/{id}/resolve  body: ResolveRequest { title, year?, disc_number?, disc_total?, metadata }.
// Stamps the chosen identity onto the job (status → identified). `year` defaults
// to null, disc fields to null, and `metadata` to {} so the body always matches the v3 contract.
export function resolveJob(
	jobId: string,
	body: {
		title: string;
		year?: number | null;
		disc_number?: number | null;
		disc_total?: number | null;
		metadata?: Record<string, unknown>;
	}
): Promise<ResolveResponse> {
	return post<ResolveResponse>(`/api/jobs/${jobId}/resolve`, {
		title: body.title,
		year: body.year ?? null,
		disc_number: body.disc_number ?? null,
		disc_total: body.disc_total ?? null,
		metadata: body.metadata ?? {}
	});
}

// v3 POST /api/jobs/manual  body: ManualTriggerRequest { drive_id, session_id? }.
// Kicks off a manual rip on the given drive, optionally pinning a transcode session.
export function triggerManual(body: ManualTriggerRequest): Promise<ManualTriggerResponse> {
	return post<ManualTriggerResponse>('/api/jobs/manual', body);
}

// v3 POST /api/jobs/{id}/transcode  body: ApplySessionRequest { session_id, overwrite }.
// Applies a transcode session to the job; `overwrite` defaults to false.
export function applySession(
	jobId: string,
	body: { session_id: string; overwrite?: boolean }
): Promise<ApplySessionResponse> {
	return post<ApplySessionResponse>(`/api/jobs/${jobId}/transcode`, {
		session_id: body.session_id,
		overwrite: body.overwrite ?? false
	});
}

// ---------------------------------------------------------------------------
// Metadata search / lookup (EXISTS in v3)
// ---------------------------------------------------------------------------

export function searchMetadata(
	query: string,
	type?: 'movie' | 'tv',
	provider?: 'tmdb' | 'omdb'
): Promise<MetadataSearchResponse> {
	const params = new URLSearchParams({ title: query });
	if (type) params.set('type', type);
	if (provider) params.set('provider', provider);
	return apiFetch<MetadataSearchResponse>(`/api/metadata/search?${params}`);
}

// v3 lookup by IMDb id (or crc64). Returns the same candidate envelope.
export function fetchMediaDetail(imdbId: string): Promise<MetadataSearchResponse> {
	const params = new URLSearchParams({ imdb_id: imdbId });
	return apiFetch<MetadataSearchResponse>(`/api/metadata/lookup?${params}`);
}

// v3 music search: query + optional artist + track_count + Type/Format/Country/Status
// filters (Lucene narrowing).
export function searchMusicMetadata(
	query: string,
	opts?: {
		artist?: string;
		track_count?: number;
		release_type?: string;
		format?: string;
		country?: string;
		status?: string;
	}
): Promise<MetadataSearchResponse> {
	const params = new URLSearchParams({ query });
	if (opts?.artist) params.set('artist', opts.artist);
	if (opts?.track_count != null) params.set('track_count', String(opts.track_count));
	if (opts?.release_type) params.set('release_type', opts.release_type);
	if (opts?.format) params.set('format', opts.format);
	if (opts?.country) params.set('country', opts.country);
	if (opts?.status) params.set('status', opts.status);
	return apiFetch<MetadataSearchResponse>(`/api/metadata/music/search?${params}`);
}

export function fetchMusicDetail(releaseId: string): Promise<MetadataReleaseDetail> {
	return apiFetch<MetadataReleaseDetail>(`/api/metadata/music/${releaseId}`);
}

// ---------------------------------------------------------------------------
// Naming (EXISTS in v3 — note the reshaped request/response contracts)
// ---------------------------------------------------------------------------

// v3 per-job naming preview: { job_output_dir, job_output_name, items[] }.
export function fetchNamingPreview(jobId: string): Promise<JobNamingPreviewResponse> {
	return apiFetch<JobNamingPreviewResponse>(`/api/jobs/${jobId}/naming-preview`, {
		signal: AbortSignal.timeout(5000)
	});
}

// v3 POST /api/naming/preview renders a single template → { rendered }.
export function namingPreview(
	template: string,
	mediaType: MediaType,
	variables?: Record<string, string>,
	hasTranscodePreset = false
): Promise<NamingPreviewResponse> {
	return apiFetch<NamingPreviewResponse>('/api/naming/preview', {
		method: 'POST',
		body: JSON.stringify({
			template,
			media_type: mediaType,
			has_transcode_preset: hasTranscodePreset,
			variables: variables ?? {}
		})
	});
}

// v3 POST /api/naming/validate → { valid }.
export function validatePattern(template: string, mediaType: MediaType, hasTranscodePreset = false): Promise<NamingValidateResponse> {
	return apiFetch<NamingValidateResponse>('/api/naming/validate', {
		method: 'POST',
		body: JSON.stringify({ template, media_type: mediaType, has_transcode_preset: hasTranscodePreset })
	});
}

// v3 GET /api/naming/variables → { variables: { group: NamingVariable[] } }.
export function fetchNamingVariables(): Promise<NamingVariablesResponse> {
	return apiFetch<NamingVariablesResponse>('/api/naming/variables');
}

// ---------------------------------------------------------------------------
// MISSING in v3 — no endpoint exists. Screens are feature-flagged OFF; the
// stub rejects before any fetch so a hidden path fails loudly. Function shapes
// are preserved so callers still compile. (P1/P2 backlog.)
// ---------------------------------------------------------------------------

export async function cancelWaitingJob(_id: string): Promise<never> {
	notAvailable('Cancel waiting job');
}

export async function startWaitingJob(_id: string): Promise<never> {
	notAvailable('Start waiting job');
}

export async function pauseWaitingJob(_id: string, _paused?: boolean): Promise<never> {
	notAvailable('Pause waiting job');
}

export async function fixJobPermissions(_id: string): Promise<never> {
	notAvailable('Fix job permissions');
}

export async function skipAndFinalize(_jobId: string): Promise<never> {
	notAvailable('Skip and finalize');
}

export async function forceComplete(_jobId: string): Promise<never> {
	notAvailable('Force complete');
}

export async function submitToCrcDb(_id: string): Promise<never> {
	notAvailable('Submit to CRC database');
}

export async function fetchCrcLookup(_jobId: string): Promise<never> {
	notAvailable('CRC lookup');
}

export async function retranscodeJob(_id: string): Promise<never> {
	notAvailable('Re-transcode job');
}

export async function toggleMultiTitle(_jobId: string, _enabled: boolean): Promise<never> {
	notAvailable('Multi-title toggle');
}

export async function tvdbMatch(
	_jobId: string,
	_opts?: {
		season?: number | null;
		tolerance?: number | null;
		apply?: boolean;
		disc_number?: number | null;
		disc_total?: number | null;
	}
): Promise<never> {
	notAvailable('TVDB episode matching');
}

export async function fetchTvdbEpisodes(_jobId: string, _season: number): Promise<never> {
	notAvailable('TVDB episode listing');
}

export async function updateJobTranscodeConfig(_jobId: string, _overrides: Record<string, unknown>): Promise<never> {
	notAvailable('Per-job transcode config');
}

export async function updateJobNaming(
	_jobId: string,
	_data: { title_pattern_override?: string | null; folder_pattern_override?: string | null }
): Promise<never> {
	notAvailable('Per-job naming overrides');
}

export async function bulkPurgeJobs(_params: { job_ids?: string[]; status?: string }): Promise<never> {
	notAvailable('Bulk purge jobs');
}

export async function fetchJobStats(_params?: {
	search?: string;
	video_type?: string;
	disctype?: string;
	days?: number;
}): Promise<never> {
	notAvailable('Job stats');
}

export async function fetchJobProgress(_id: string): Promise<never> {
	notAvailable('Job progress polling');
}

export async function setJobTracks(
	_jobId: string,
	_tracks: { track_number: string; title: string; length_ms: number | null }[]
): Promise<never> {
	notAvailable('Replace job tracks');
}
