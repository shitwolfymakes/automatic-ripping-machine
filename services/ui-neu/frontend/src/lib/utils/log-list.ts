// Pure helpers for the Logs page's job list (routes/logs/+page.svelte).
import type { JobView } from '$lib/types/api.gen';
import { discTypeLabel, getVideoTypeConfig, type VideoTypeConfig } from './job-type';
import { readJobMetadata } from './job-fields';

type DiscFields = Partial<Pick<JobView, 'season' | 'disc_number' | 'disc_total'>>;
type TypeFields = Pick<JobView, 'metadata_json' | 'disc_type'> & Partial<Pick<JobView, 'media_type' | 'season'>>;

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

/** The disc chip: `ISO` / `Folder` for virtual sources (as the job page decides it), else the disc type. */
export function discKindLabel(job: TypeFields): string {
	const source = readJobMetadata(job.metadata_json, job).source_type;
	if (source === 'iso') return 'ISO';
	if (source === 'folder') return 'Folder';
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

/** `Oct 16, 8:18 AM` in the viewer's locale and time zone. */
export function formatShortDateTime(iso: string): string {
	return new Date(iso).toLocaleString(undefined, {
		month: 'short',
		day: 'numeric',
		hour: 'numeric',
		minute: '2-digit'
	});
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
