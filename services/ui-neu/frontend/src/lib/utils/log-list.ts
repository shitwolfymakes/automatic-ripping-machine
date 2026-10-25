// Pure helpers for the Logs page's job list (routes/logs/+page.svelte).
import type { JobLogFileView, JobView } from '$lib/types/api.gen';
import type { IsoSourceKind } from '$lib/api/dashboard';
import { discTypeLabel, getVideoTypeConfig, type VideoTypeConfig } from './job-type';
import { readJobMetadata } from './job-fields';

type DiscFields = Partial<Pick<JobView, 'season' | 'disc_number' | 'disc_total'>>;
type TypeFields = Pick<JobView, 'metadata_json' | 'disc_type'> &
	Partial<Pick<JobView, 'media_type' | 'season' | 'drive_id'>>;

const CD_DISCTYPES = new Set(['cd']);

/** `S1 · Disc 2/4`, leaving out the parts that are unknown; `-` when nothing is. */
export function discPosition(job: DiscFields): string {
	const parts: string[] = [];
	if (job.season != null) parts.push(`S${job.season}`);
	if (job.disc_number != null) {
		parts.push(job.disc_total != null ? `Disc ${job.disc_number}/${job.disc_total}` : `Disc ${job.disc_number}`);
	}
	return parts.length ? parts.join(' · ') : '-';
}

/**
 * The disc chip: `ISO` / `Folder` when the job's drive is a virtual one (the
 * dashboard's drive_source_kinds, which keeps retired drives), else the disc type.
 */
export function discKindLabel(job: TypeFields, driveSourceKinds?: Record<string, IsoSourceKind> | null): string {
	const kind = job.drive_id ? driveSourceKinds?.[job.drive_id] : undefined;
	if (kind === 'iso') return 'ISO';
	if (kind === 'folder') return 'Folder';
	return discTypeLabel(job.disc_type);
}

/** The type chip's label and colours: Series / Movie from media_type, Music for CDs. */
export function jobTypeConfig(job: TypeFields): VideoTypeConfig {
	const videoType = readJobMetadata(job.metadata_json, job).video_type;
	if (!videoType && job.disc_type && CD_DISCTYPES.has(job.disc_type.toLowerCase())) {
		return getVideoTypeConfig('music');
	}
	return getVideoTypeConfig(videoType ?? null, job.disc_type);
}

/** job id -> log modified_at; an unparseable date is dropped, so it reads (and sorts) as no log. */
export function indexLogFiles(files: JobLogFileView[]): Map<string, string> {
	return new Map(files.filter((f) => !Number.isNaN(Date.parse(f.modified_at))).map((f) => [f.job_id, f.modified_at]));
}

/**
 * Newest log first; jobs with no log file follow those with one, in their
 * original (job) order. `modified` maps job id to the log's modified_at.
 */
export function orderByLastModified<T extends { id: string }>(jobs: T[], modified: Map<string, string>): T[] {
	const withLog = jobs.filter((j) => modified.has(j.id));
	const withoutLog = jobs.filter((j) => !modified.has(j.id));
	withLog.sort((a, b) => Date.parse(modified.get(b.id)!) - Date.parse(modified.get(a.id)!));
	return [...withLog, ...withoutLog];
}

/** `job_` plus the id's last four characters, lowercased: `job_9a41`. */
export function shortJobId(id: string): string {
	return `job_${id.slice(-4).toLowerCase()}`;
}
