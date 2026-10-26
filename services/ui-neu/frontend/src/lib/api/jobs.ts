import type {
	ExternalIds,
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
	MusicMeta,
	ResolveMatch,
	ResolveResponse,
	ApplySessionResponse,
	ManualTriggerRequest,
	ManualTriggerResponse,
	RipAgainResponse
} from '$lib/types/api.gen';
import { apiFetch, apiFetchResponse, post } from './client';

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

function jobsPath(params?: FetchJobsParams): string {
	const query = new URLSearchParams();
	if (params?.status) query.set('status', params.status);
	if (params?.drive_id) query.set('drive_id', params.drive_id);
	if (params?.limit !== undefined) query.set('limit', String(params.limit));
	if (params?.offset !== undefined) query.set('offset', String(params.offset));
	const qs = query.toString();
	return `/api/jobs${qs ? `?${qs}` : ''}`;
}

export function fetchJobs(params?: FetchJobsParams): Promise<JobView[]> {
	return apiFetch<JobView[]>(jobsPath(params));
}

export interface JobsPage {
	jobs: JobView[];
	/** Jobs matching the filters across all pages (the `X-Total-Count` header). */
	total: number;
}

/** One page of jobs plus the filtered total, for paged lists. */
export async function fetchJobsPage(params?: FetchJobsParams): Promise<JobsPage> {
	const { data, headers } = await apiFetchResponse<JobView[]>(jobsPath(params));
	const header = Number(headers.get('X-Total-Count'));
	return { jobs: data, total: Number.isFinite(header) && header > 0 ? header : data.length };
}

// The Backend's per-request cap on `limit`.
const MAX_JOBS_PAGE = 500;

/** Every job matching `params`, paged through MAX_JOBS_PAGE at a time. For
 *  views that sort or filter client-side on fields the API can't order by. */
export async function fetchAllJobs(params?: Omit<FetchJobsParams, 'limit' | 'offset'>): Promise<JobsPage> {
	const jobs: JobView[] = [];
	for (;;) {
		const page = await fetchJobsPage({ ...params, limit: MAX_JOBS_PAGE, offset: jobs.length });
		jobs.push(...page.jobs);
		if (page.jobs.length === 0 || jobs.length >= page.total) break;
	}
	return { jobs, total: jobs.length };
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

// Clear the operator title override: `title` is resolver-owned, so revert it
// (hands it back to the automatic sources) rather than pinning a manual null.
// year / imdb_id / poster_url are plain fields and are cleared with null.
export function clearTrackTitle(jobId: string, trackId: string): Promise<JobView> {
	return patchJob(jobId, {
		tracks: [{ track_id: trackId, year: null, imdb_id: null, poster_url: null, revert_fields: ['title'] }]
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

// Header Movie | TV switch: the type alone; ids and title stay (spec 3.2).
export function setJobMediaType(jobId: string, mediaType: 'movie' | 'tv'): Promise<JobView> {
	return patchJob(jobId, { media_type: mediaType });
}

export function updateJobConfig(jobId: string, data: JobUpdateRequest): Promise<JobView> {
	return patchJob(jobId, data);
}

// ---------------------------------------------------------------------------
// Identify / resolve + apply-session (EXISTS in v3)
// ---------------------------------------------------------------------------

// v3 POST /api/jobs/{id}/resolve  body: ResolveRequest { title, year?, season?, disc_number?, disc_total?, media_type?, music? }.
// Stamps the chosen identity onto the job (status → identified). `year` defaults
// to null; `music`/`media_type` are only sent by callers that have something
// typed to say; `external_ids` and `match` carry a picked candidate (the free-form `metadata` bag is gone — unknown keys 422).
//
// season/disc_number/disc_total are a classification like media_type on the
// Backend, not part of the identity statement: omitted keeps whatever value
// is already stored (a disc-hint source may have filled it before the
// operator ever opened the identify dialog -- Review Focus 5), while an
// explicit `null` is the operator clearing it. `!== undefined` is the only
// way to tell "the caller didn't pass this" from "the caller passed null".
export function resolveJob(
	jobId: string,
	body: {
		title: string;
		year?: number | null;
		season?: number | null;
		disc_number?: number | null;
		disc_total?: number | null;
		media_type?: MediaType | null;
		music?: MusicMeta;
		external_ids?: ExternalIds | null;
		match?: ResolveMatch;
	}
): Promise<ResolveResponse> {
	const payload: Record<string, unknown> = {
		title: body.title,
		year: body.year ?? null
	};
	if (body.season !== undefined) {
		payload.season = body.season;
	}
	if (body.disc_number !== undefined) {
		payload.disc_number = body.disc_number;
	}
	if (body.disc_total !== undefined) {
		payload.disc_total = body.disc_total;
	}
	payload.media_type = body.media_type;
	payload.music = body.music;
	if (body.external_ids !== undefined) {
		payload.external_ids = body.external_ids;
	}
	if (body.match !== undefined) {
		payload.match = body.match;
	}
	return post<ResolveResponse>(`/api/jobs/${jobId}/resolve`, payload);
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

export type MatchProvider = 'tmdb' | 'omdb' | 'tvmaze' | 'tvdb';

export function searchMetadata(
	query: string,
	type?: 'movie' | 'tv',
	provider?: MatchProvider,
	year?: number | null
): Promise<MetadataSearchResponse> {
	const params = new URLSearchParams({ title: query });
	if (type) params.set('type', type);
	if (provider) params.set('provider', provider);
	if (year != null) params.set('year', String(year));
	return apiFetch<MetadataSearchResponse>(`/api/metadata/search?${params}`);
}

// One title's full record for the match picker's detail pane (cached server side).
export function fetchMatchDetails(
	provider: MatchProvider,
	type: 'movie' | 'tv',
	id: string
): Promise<MetadataSearchResponse> {
	const params = new URLSearchParams({ provider, type, id });
	return apiFetch<MetadataSearchResponse>(`/api/metadata/details?${params}`);
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
export function fetchNamingPreview(jobId: string, sessionId?: string): Promise<JobNamingPreviewResponse> {
	const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
	return apiFetch<JobNamingPreviewResponse>(`/api/jobs/${jobId}/naming-preview${qs}`, {
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
export function validatePattern(
	template: string,
	mediaType: MediaType,
	hasTranscodePreset = false
): Promise<NamingValidateResponse> {
	return apiFetch<NamingValidateResponse>('/api/naming/validate', {
		method: 'POST',
		body: JSON.stringify({ template, media_type: mediaType, has_transcode_preset: hasTranscodePreset })
	});
}

// v3 GET /api/naming/variables → { variables: { group: NamingVariable[] } }.
export function fetchNamingVariables(): Promise<NamingVariablesResponse> {
	return apiFetch<NamingVariablesResponse>('/api/naming/variables');
}

// Timed review gate: operator Start for a disc held in awaiting_review.
// Transitions AWAITING_REVIEW -> RIPPING and unblocks the parked ripper.
// on_previously_ripped: rip a ripped job's disc again. Starts a held copy of
// the disc if one is waiting, otherwise lets the next insert through once.
export function ripAgain(id: string): Promise<RipAgainResponse> {
	return apiFetch<RipAgainResponse>(`/api/jobs/${id}/rip-again`, { method: 'POST' });
}

// Apply the identity suggestion identify held for review (the media type's
// auto-apply switch is off). Answers like resolve; 409 when none is held.
export function acceptIdentitySuggestion(jobId: string): Promise<ResolveResponse> {
	return post<ResolveResponse>(`/api/jobs/${jobId}/identity/accept`);
}

export function startWaitingJob(id: string): Promise<JobView> {
	return apiFetch<JobView>(`/api/jobs/${id}/rip-start-review`, { method: 'POST' });
}

// Timed review gate: per-job pause/resume. paused=true freezes this disc's
// countdown; paused=false resumes with a fresh countdown.
export function pauseWaitingJob(id: string, paused = true): Promise<JobView> {
	return apiFetch<JobView>(`/api/jobs/${id}/review-pause?paused=${paused}`, { method: 'POST' });
}
