// Reads the known scalar keys out of a job's freeform metadata_json.
import type { JobView } from '$lib/types/api.gen';

export interface JobMetadata {
	imdb_id?: string;
	tmdb_id?: string;
	tvdb_id?: string;
	video_type?: string;
	season?: string;
	artist?: string;
	album?: string;
	multi_title?: boolean;
	source_type?: string;
	pending_session_id?: string;
	titleCount?: number;
}

function asScalarString(v: unknown): string | undefined {
	if (typeof v === 'string') return v;
	if (typeof v === 'number' && Number.isFinite(v)) return String(v);
	return undefined;
}

const MEDIA_TYPE_TO_VIDEO_TYPE: Record<string, string> = {
	tv: 'series'
};

function asRecord(v: unknown): Record<string, unknown> {
	return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function readExternalIds(ext: Record<string, unknown>): Pick<JobMetadata, 'imdb_id' | 'tmdb_id' | 'tvdb_id'> {
	const out: Pick<JobMetadata, 'imdb_id' | 'tmdb_id' | 'tvdb_id'> = {};
	const imdb = asScalarString(ext.imdb);
	if (imdb !== undefined) out.imdb_id = imdb;
	const tmdb = asScalarString(ext.tmdb);
	if (tmdb !== undefined) out.tmdb_id = tmdb;
	const tvdb = asScalarString(ext.tvdb);
	if (tvdb !== undefined) out.tvdb_id = tvdb;
	return out;
}

function readVideoType(
	job: Pick<JobView, 'media_type'> | null | undefined,
	armServer: Record<string, unknown>,
	legacy: Record<string, unknown>
): string | undefined {
	// job.media_type is the authoritative column (set at identify, correctable at
	// resolve); the provider's own video_type is only a fallback for rows without it.
	if (job?.media_type) return MEDIA_TYPE_TO_VIDEO_TYPE[job.media_type] ?? job.media_type;
	return asScalarString(armServer.video_type) ?? asScalarString(legacy.video_type);
}

function readMusic(music: Record<string, unknown>): Pick<JobMetadata, 'artist' | 'album'> {
	const out: Pick<JobMetadata, 'artist' | 'album'> = {};
	const artist = asScalarString(music.artist);
	if (artist !== undefined) out.artist = artist;
	const album = asScalarString(music.album);
	if (album !== undefined) out.album = album;
	return out;
}

function readProviderExtras(
	armServer: Record<string, unknown>,
	legacy: Record<string, unknown>
): Pick<JobMetadata, 'multi_title' | 'source_type'> {
	const out: Pick<JobMetadata, 'multi_title' | 'source_type'> = {};
	const multiTitle = typeof armServer.multi_title === 'boolean' ? armServer.multi_title : legacy.multi_title;
	if (typeof multiTitle === 'boolean') out.multi_title = multiTitle;
	const source = asScalarString(armServer.source_type) ?? asScalarString(legacy.source_type);
	if (source !== undefined) out.source_type = source;
	return out;
}

function countScanTitles(md: Record<string, unknown>): number | undefined {
	const scan = md.scan_result;
	if (!scan || typeof scan !== 'object') return undefined;
	const titles = (scan as Record<string, unknown>).titles;
	return Array.isArray(titles) ? titles.length : undefined;
}

/**
 * Read the known scalar keys out of a job's freeform `metadata_json`.
 * Every read is guarded so a missing or malformed blob yields `undefined`
 * for that key (never throws). Structured values (scan_result, tracks, raw)
 * are intentionally NOT surfaced here — they belong to the raw viewer.
 */
export function readJobMetadata(
	metadata_json: Record<string, unknown> | null | undefined,
	job?: Pick<JobView, 'season' | 'pending_session_id' | 'media_type'> | null
): JobMetadata {
	const md = (metadata_json ?? {}) as Record<string, unknown>;
	const out: JobMetadata = {};

	// season and pending_session_id are job COLUMNS.
	if (job?.season != null) out.season = String(job.season).padStart(2, '0');
	if (job?.pending_session_id) out.pending_session_id = job.pending_session_id;

	// The typed sections are authoritative — external ids
	// live under identity.external_ids, the 1337-server extras under
	// provider_raw.arm_server, music naming under music.
	const identity = asRecord(md.identity);
	const ext = asRecord(identity.external_ids);
	const providerRaw = asRecord(md.provider_raw);
	const armServer = asRecord(providerRaw.arm_server);
	// Rows from before the typed sections keep their merged provider payload
	// under provider_raw.legacy (migration 0032).
	const legacy = asRecord(providerRaw.legacy);
	const music = asRecord(md.music);

	Object.assign(out, readExternalIds(ext));
	const videoType = readVideoType(job, armServer, legacy);
	if (videoType !== undefined) out.video_type = videoType;
	Object.assign(out, readMusic(music), readProviderExtras(armServer, legacy));
	const titleCount = countScanTitles(md);
	if (titleCount !== undefined) out.titleCount = titleCount;

	return out;
}
