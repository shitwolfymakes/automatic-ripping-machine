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
	fields.push({ label: 'Drive', value: job.drive_id ?? '-', mono: true });
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
