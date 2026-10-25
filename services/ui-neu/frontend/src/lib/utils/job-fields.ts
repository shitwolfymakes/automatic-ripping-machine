import type { JobView } from '$lib/types/api.gen';
import { statusLabel } from '$lib/utils/format';
import { discTypeLabel } from '$lib/utils/job-type';
import { isAwaitingIdentity, isInProgress, isLive, isPostRipStatus } from '$lib/utils/job-status-groups';
import { driveLabel } from '$lib/utils/drive-name';

export type EditableJobField = 'year' | 'season' | 'disc_number' | 'disc_total';

export interface MetadataField {
	label: string;
	value: string;
	mono?: boolean;
	link?: string;
	isSelect?: boolean;
	empty?: boolean;
	/** The job field an admin edits in place in this cell. */
	edit?: EditableJobField;
	/** The raw value the editor starts from ('' when unset); `value` stays the display form. */
	raw?: string;
}

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

/**
 * Read the known scalar keys out of a job's freeform `metadata_json`.
 * Every read is guarded so a missing or malformed blob yields `undefined`
 * for that key (never throws). Structured values (scan_result, tracks, raw)
 * are intentionally NOT surfaced here — they belong to the raw viewer.
 */
const MEDIA_TYPE_TO_VIDEO_TYPE: Record<string, string> = {
	tv: 'series'
};

export function readJobMetadata(
	metadata_json: Record<string, unknown> | null | undefined,
	job?: Pick<JobView, 'season' | 'pending_session_id' | 'media_type'> | null
): JobMetadata {
	const md = (metadata_json ?? {}) as Record<string, unknown>;
	const out: JobMetadata = {};

	// Step 2 (backend): season and pending_session_id are job COLUMNS now.
	if (job?.season != null) out.season = String(job.season).padStart(2, '0');
	if (job?.pending_session_id) out.pending_session_id = job.pending_session_id;

	// Step 2 (§3.4): the typed sections are authoritative — external ids
	// live under identity.external_ids, the 1337-server extras under
	// provider_raw.arm_server, music naming under music.
	const asRecord = (v: unknown): Record<string, unknown> =>
		v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
	const identity = asRecord(md.identity);
	const ext = asRecord(identity.external_ids);
	const providerRaw = asRecord(md.provider_raw);
	const armServer = asRecord(providerRaw.arm_server);
	// Rows from before the typed sections keep their merged provider payload
	// under provider_raw.legacy (migration 0032).
	const legacy = asRecord(providerRaw.legacy);
	const music = asRecord(md.music);

	const imdb = asScalarString(ext.imdb);
	if (imdb !== undefined) out.imdb_id = imdb;
	const tmdb = asScalarString(ext.tmdb);
	if (tmdb !== undefined) out.tmdb_id = tmdb;
	const tvdb = asScalarString(ext.tvdb);
	if (tvdb !== undefined) out.tvdb_id = tvdb;
	// job.media_type is the authoritative column (set at identify, correctable at
	// resolve); the provider's own video_type is only a fallback for rows without it.
	if (job?.media_type) {
		out.video_type = MEDIA_TYPE_TO_VIDEO_TYPE[job.media_type] ?? job.media_type;
	} else {
		const vt = asScalarString(armServer.video_type) ?? asScalarString(legacy.video_type);
		if (vt !== undefined) out.video_type = vt;
	}
	const artist = asScalarString(music.artist);
	if (artist !== undefined) out.artist = artist;
	const album = asScalarString(music.album);
	if (album !== undefined) out.album = album;
	const multiTitle = typeof armServer.multi_title === 'boolean' ? armServer.multi_title : legacy.multi_title;
	if (typeof multiTitle === 'boolean') out.multi_title = multiTitle;
	const source = asScalarString(armServer.source_type) ?? asScalarString(legacy.source_type);
	if (source !== undefined) out.source_type = source;

	const scan = md.scan_result;
	if (scan && typeof scan === 'object') {
		const titles = (scan as Record<string, unknown>).titles;
		if (Array.isArray(titles)) out.titleCount = titles.length;
	}

	return out;
}

const VIDEO_TYPE_LABELS: Record<string, string> = {
	movie: 'Movie',
	series: 'Series',
	music: 'Music',
	data: 'Data'
};

export function videoTypeLabel(vt: string | null | undefined): string {
	if (!vt) return 'Unknown';
	return VIDEO_TYPE_LABELS[vt.toLowerCase()] ?? vt;
}

// v3 JobView exposes only a small set of fields. The rich BFF metadata
// (video_type, label, devpath, multi_title, crc_id, imdb_id, season,
// tvdb_id, artist/album, output paths, stop_time, job_length, …) has no
// v3 equivalent, so those fields are dropped here rather than synthesized.
function shortSessionId(id: string): string {
	return id.length > 15 ? `${id.slice(0, 15)}...` : id;
}

function parkedSuffix(status: JobView['status']): string {
	if (status === 'failed') return 'not applied, the rip failed';
	if (status === 'abandoned') return 'not applied, the job was abandoned';
	return isPostRipStatus(status) ? 'waiting' : 'applies when the rip finishes';
}

/**
 * "Name[, Name], applies when the rip finishes" pre-rip, "..., waiting" post-rip,
 * "..., not applied, ..." once the rip failed or the job was abandoned; null if none parked.
 */
export function parkedSessionLine(
	job: Pick<JobView, 'parked_session_ids' | 'status'>,
	names: Map<string, string>
): string | null {
	const ids = job.parked_session_ids ?? [];
	if (ids.length === 0) return null;
	const label = ids.map((id) => names.get(id) ?? shortSessionId(id)).join(', ');
	return `${label}, ${parkedSuffix(job.status)}`;
}

export function buildMetadataFields(
	job: JobView,
	driveNames?: Record<string, string> | null,
	sessionNames?: Map<string, string>
): MetadataField[] {
	const fields: MetadataField[] = [];

	// --- Always-present base fields ---
	fields.push({ label: 'Disc Type', value: discTypeLabel(job.disc_type) });
	fields.push({ label: 'Status', value: statusLabel(job.status) });
	fields.push({
		label: 'Year',
		value: job.year != null ? String(job.year) : '-',
		edit: 'year',
		raw: job.year != null ? String(job.year) : ''
	});
	fields.push({ label: 'Drive', value: driveLabel(job.drive_id, driveNames), mono: true });
	if (job.resumed_from_crash) {
		fields.push({ label: 'Recovery', value: 'Resumed from crash' });
	}

	// --- Rip progress when present ---
	if (job.rip_progress) {
		const { tracks_done, tracks_total } = job.rip_progress;
		fields.push({ label: 'Tracks', value: `${tracks_done} / ${tracks_total}` });
	}

	// --- Time field based on job state ---
	// A ripped job that is waiting for the operator is live (it can still change)
	// but nothing is running, so it is neither "In progress" nor "Finished". A
	// job with a parked session is not waiting for one: the Session row below
	// names the session that is waiting.
	const parked = parkedSessionLine(job, sessionNames ?? new Map());
	let stateLabel = 'Finished';
	if (isInProgress(job)) stateLabel = 'In progress';
	else if (isLive(job)) {
		if (isAwaitingIdentity(job.status)) stateLabel = 'Waiting for identity';
		else stateLabel = parked ? 'Waiting' : 'Waiting for session';
	}
	fields.push({ label: 'State', value: stateLabel });
	if (parked) fields.push({ label: 'Session', value: parked });

	// --- Promoted real JobView columns ---
	// A TV job always offers its disc position and season, set in place; any
	// other job shows them once something set them.
	const tv = job.media_type === 'tv';
	if (tv || job.disc_number != null) {
		fields.push({
			label: 'Disc #',
			value: job.disc_number != null ? String(job.disc_number) : '-',
			edit: 'disc_number',
			raw: job.disc_number != null ? String(job.disc_number) : ''
		});
	}
	if (tv || job.disc_total != null) {
		fields.push({
			label: 'Disc total',
			value: job.disc_total != null ? String(job.disc_total) : '-',
			edit: 'disc_total',
			raw: job.disc_total != null ? String(job.disc_total) : ''
		});
	}
	if (job.poster_url_manual) {
		fields.push({ label: 'Poster', value: 'Manual' });
	} else if (job.poster_url) {
		fields.push({ label: 'Poster', value: 'Auto' });
	}

	// --- Promoted metadata_json known scalars ---
	const md = readJobMetadata(job.metadata_json, job);
	if (md.video_type) {
		fields.push({ label: 'Type', value: videoTypeLabel(md.video_type) });
	}
	if (md.imdb_id && job.disc_type !== 'cd') {
		fields.push({ label: 'IMDb', value: md.imdb_id, link: `https://www.imdb.com/title/${md.imdb_id}` });
	}
	if (md.tmdb_id) {
		fields.push({ label: 'TMDB', value: md.tmdb_id, link: `https://www.themoviedb.org/movie/${md.tmdb_id}` });
	}
	if (md.tvdb_id) {
		fields.push({ label: 'TVDB', value: md.tvdb_id, link: `https://www.thetvdb.com/dereferrer/series/${md.tvdb_id}` });
	}
	if (tv || md.season) {
		fields.push({
			label: 'Season',
			value: md.season || '-',
			edit: 'season',
			raw: job.season != null ? String(job.season) : ''
		});
	}
	if (md.artist) {
		fields.push({ label: 'Artist', value: md.artist });
	}
	if (md.album) {
		fields.push({ label: 'Album', value: md.album });
	}
	// Scanned-title count: only when the base "Tracks" cell (rip_progress) is absent.
	if (!job.rip_progress && md.titleCount != null) {
		fields.push({ label: 'Titles', value: String(md.titleCount) });
	}

	// --- Pad to multiple of 4 ---
	const remainder = fields.length % 4;
	if (remainder !== 0) {
		const padding = 4 - remainder;
		for (let i = 0; i < padding; i++) {
			fields.push({ label: '', value: '', empty: true });
		}
	}

	return fields;
}
