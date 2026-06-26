import type { JobView } from '$lib/types/api.gen';
import { discTypeLabel, isJobActive } from '$lib/utils/job-type';

export interface MetadataField {
	label: string;
	value: string;
	mono?: boolean;
	link?: string;
	isSelect?: boolean;
	empty?: boolean;
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
export function readJobMetadata(
	metadata_json: Record<string, unknown> | null | undefined
): JobMetadata {
	const md = (metadata_json ?? {}) as Record<string, unknown>;
	const out: JobMetadata = {};

	const imdb = asScalarString(md.imdb_id);
	if (imdb !== undefined) out.imdb_id = imdb;
	const tmdb = asScalarString(md.tmdb_id);
	if (tmdb !== undefined) out.tmdb_id = tmdb;
	const tvdb = asScalarString(md.tvdb_id);
	if (tvdb !== undefined) out.tvdb_id = tvdb;
	const vt = asScalarString(md.video_type);
	if (vt !== undefined) out.video_type = vt;
	const season = asScalarString(md.season);
	if (season !== undefined) out.season = season;
	const artist = asScalarString(md.artist);
	if (artist !== undefined) out.artist = artist;
	const album = asScalarString(md.album);
	if (album !== undefined) out.album = album;
	if (typeof md.multi_title === 'boolean') out.multi_title = md.multi_title;
	const source = asScalarString(md.source_type);
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
export function buildMetadataFields(job: JobView): MetadataField[] {
	const active = isJobActive(job.status);

	const fields: MetadataField[] = [];

	// --- Always-present base fields ---
	fields.push({ label: 'Disc Type', value: discTypeLabel(job.disc_type) });
	fields.push({ label: 'Status', value: job.status });
	fields.push({ label: 'Year', value: job.year != null ? String(job.year) : '-' });
	fields.push({ label: 'Drive', value: job.drive_id, mono: true });
	if (job.resumed_from_crash) {
		fields.push({ label: 'Recovery', value: 'Resumed from crash' });
	}

	// --- Rip progress when present ---
	if (job.rip_progress) {
		const { tracks_done, tracks_total } = job.rip_progress;
		fields.push({ label: 'Tracks', value: `${tracks_done} / ${tracks_total}` });
	}

	// --- Time field based on job state ---
	if (active) {
		fields.push({ label: 'State', value: 'In progress' });
	} else {
		fields.push({ label: 'State', value: 'Finished' });
	}

	// --- Promoted real JobView columns ---
	if (job.disc_number != null) {
		const discValue =
			job.disc_total != null ? `${job.disc_number} of ${job.disc_total}` : String(job.disc_number);
		fields.push({ label: 'Disc #', value: discValue });
	}
	if (job.poster_url_manual) {
		fields.push({ label: 'Poster', value: 'Manual' });
	} else if (job.poster_url) {
		fields.push({ label: 'Poster', value: 'Auto' });
	}

	// --- Promoted metadata_json known scalars ---
	const md = readJobMetadata(job.metadata_json);
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
	if (md.season) {
		fields.push({ label: 'Season', value: md.season });
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

export interface MetadataEntry {
	key: string;
	display: string;
	isJson: boolean;
}

/**
 * Flatten a job's `metadata_json` into one row per TOP-LEVEL key for the raw
 * viewer. Scalars render inline; objects/arrays are pretty-printed JSON so
 * structured values (scan_result, tracks, raw) are fully visible without
 * being flattened into the grid. Returns [] for an empty/missing blob.
 */
export function metadataEntries(
	metadata_json: Record<string, unknown> | null | undefined
): MetadataEntry[] {
	const md = (metadata_json ?? {}) as Record<string, unknown>;
	return Object.entries(md).map(([key, value]) => {
		if (value !== null && typeof value === 'object') {
			return { key, display: JSON.stringify(value, null, 2), isJson: true };
		}
		return { key, display: value == null ? '' : String(value), isJson: false };
	});
}
