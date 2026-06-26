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
