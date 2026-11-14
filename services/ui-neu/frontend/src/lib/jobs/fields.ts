import type { JobView } from '$lib/types/api.gen';
import { statusLabel } from '$lib/jobs/status-format';
import { readJobMetadata, type JobMetadata } from '$lib/jobs/metadata';
import { discTypeLabel } from '$lib/jobs/type';
import { isAwaitingIdentity, isInProgress, isLive } from '$lib/jobs/status-groups';
import { parkedSessionLine } from '$lib/sessions/parked-session';
import { driveLabel } from '$lib/drives/name';

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

const FIELD_GRID_WIDTH = 4;

/** An in-place-editable number cell: shows the number or '-', edits from the number or ''. */
function editableNumberField(label: string, edit: EditableJobField, value: number | null | undefined): MetadataField {
	return {
		label,
		value: value != null ? String(value) : '-',
		edit,
		raw: value != null ? String(value) : ''
	};
}

function baseFields(job: JobView, driveNames?: Record<string, string> | null): MetadataField[] {
	const fields: MetadataField[] = [
		{ label: 'Disc Type', value: discTypeLabel(job.disc_type) },
		{ label: 'Status', value: statusLabel(job.status) },
		editableNumberField('Year', 'year', job.year),
		{ label: 'Drive', value: driveLabel(job.drive_id, driveNames), mono: true }
	];
	if (job.resumed_from_crash) {
		fields.push({ label: 'Recovery', value: 'Resumed from crash' });
	}
	if (job.rip_progress) {
		const { tracks_done, tracks_total } = job.rip_progress;
		fields.push({ label: 'Tracks', value: `${tracks_done} / ${tracks_total}` });
	}
	return fields;
}

function stateLabel(job: JobView, parked: string | null): string {
	if (isInProgress(job)) return 'In progress';
	if (!isLive(job)) return 'Finished';
	if (isAwaitingIdentity(job.status)) return 'Waiting for identity';
	return parked ? 'Waiting' : 'Waiting for session';
}

function stateFields(job: JobView, sessionNames?: Map<string, string>): MetadataField[] {
	// A ripped job that is waiting for the operator is live (it can still change)
	// but nothing is running, so it is neither "In progress" nor "Finished". A
	// job with a parked session is not waiting for one: the Session row below
	// names the session that is waiting.
	const parked = parkedSessionLine(job, sessionNames ?? new Map());
	const fields: MetadataField[] = [{ label: 'State', value: stateLabel(job, parked) }];
	if (parked) fields.push({ label: 'Session', value: parked });
	return fields;
}

function discPositionFields(job: JobView, tv: boolean): MetadataField[] {
	// A TV job always offers its disc position and season, set in place; any
	// other job shows them once something set them.
	const fields: MetadataField[] = [];
	if (tv || job.disc_number != null) {
		fields.push(editableNumberField('Disc #', 'disc_number', job.disc_number));
	}
	if (tv || job.disc_total != null) {
		fields.push(editableNumberField('Disc total', 'disc_total', job.disc_total));
	}
	return fields;
}

function posterFields(job: JobView): MetadataField[] {
	if (job.poster_url_manual) return [{ label: 'Poster', value: 'Manual' }];
	if (job.poster_url) return [{ label: 'Poster', value: 'Auto' }];
	return [];
}

function externalIdFields(md: JobMetadata, discType: JobView['disc_type']): MetadataField[] {
	const fields: MetadataField[] = [];
	if (md.imdb_id && discType !== 'cd') {
		fields.push({ label: 'IMDb', value: md.imdb_id, link: `https://www.imdb.com/title/${md.imdb_id}` });
	}
	if (md.tmdb_id) {
		fields.push({ label: 'TMDB', value: md.tmdb_id, link: `https://www.themoviedb.org/movie/${md.tmdb_id}` });
	}
	if (md.tvdb_id) {
		fields.push({ label: 'TVDB', value: md.tvdb_id, link: `https://www.thetvdb.com/dereferrer/series/${md.tvdb_id}` });
	}
	return fields;
}

function metadataJsonFields(job: JobView, tv: boolean): MetadataField[] {
	const md = readJobMetadata(job.metadata_json, job);
	const fields: MetadataField[] = [];
	if (md.video_type) {
		fields.push({ label: 'Type', value: videoTypeLabel(md.video_type) });
	}
	fields.push(...externalIdFields(md, job.disc_type));
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
	return fields;
}

/** Fill the last grid row with empty cells so the rows are always full. */
function padToRow(fields: MetadataField[], width: number): MetadataField[] {
	const remainder = fields.length % width;
	if (remainder === 0) return fields;
	const padding: MetadataField[] = Array.from({ length: width - remainder }, () => ({
		label: '',
		value: '',
		empty: true
	}));
	return [...fields, ...padding];
}

// JobView exposes only a small set of fields. Richer metadata
// (video_type, label, devpath, multi_title, crc_id, imdb_id, season,
// tvdb_id, artist/album, output paths, stop_time, job_length, …) has no
// v3 equivalent, so those fields are dropped here rather than synthesized.
export function buildMetadataFields(
	job: JobView,
	driveNames?: Record<string, string> | null,
	sessionNames?: Map<string, string>
): MetadataField[] {
	const tv = job.media_type === 'tv';
	const fields = [
		...baseFields(job, driveNames),
		...stateFields(job, sessionNames),
		...discPositionFields(job, tv),
		...posterFields(job),
		...metadataJsonFields(job, tv)
	];
	return padToRow(fields, FIELD_GRID_WIDTH);
}
