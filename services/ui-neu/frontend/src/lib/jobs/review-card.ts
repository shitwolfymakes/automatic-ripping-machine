// The review card's text, built from the job's state.
import type { JobView } from '$lib/types/api.gen';
import type { EpisodeStatus } from '$lib/episodes/status';
import { videoTypeLabel } from '$lib/jobs/fields';
import { providerLabel } from '$lib/settings/provider-labels';
import { driveLabel } from '$lib/drives/name';
import { discTypeLabel } from '$lib/jobs/type';
import { sessionDisplayName } from '$lib/sessions/parked-session';

/** The job states that decide the review card's status label. */
export interface StatusLabelFlags {
	/** The disc was ripped before. */
	previouslyRipped: boolean;
	/** An identity suggestion is waiting to be confirmed. */
	suggestion: boolean;
	/** The job is at the review gate. */
	reviewGate: boolean;
	/** The rip is done and a session can be applied. */
	postRip: boolean;
}

/** The status bar's label; the first matching state wins. */
export function reviewStatusLabel(flags: StatusLabelFlags): string {
	if (flags.previouslyRipped) return 'Already ripped: Rip again or Discard';
	if (flags.suggestion) return 'Confirm the title: use it or search';
	if (flags.reviewGate) return 'Ready: Review & Start';
	if (flags.postRip) return 'Ripped: Apply Session';
	return 'Awaiting Review';
}

/**
 * "TMDb, 4 of 6 titles" under a running match; parts it doesn't know yet are
 * left out, and nothing known gives null.
 */
export function episodeMatchingDetail(row: Pick<EpisodeStatus, 'source' | 'total' | 'unmatched'>): string | null {
	const { source, total, unmatched } = row;
	const counts = total && unmatched != null ? `${total - unmatched} of ${total} titles` : null;
	return [source, counts].filter(Boolean).join(', ') || null;
}

/** The year, or "1974-1975" when the end year is set and differs. */
function yearSpan(year: number | null | undefined, endYear: number | null | undefined): string | null {
	if (!year) return null;
	if (endYear && endYear !== year) return `${year}-${endYear}`;
	return `${year}`;
}

/** "TV Series" on TV, else the video type's label; null with neither. */
function matchKind(isTv: boolean, videoType: string | undefined): string | null {
	if (isTv) return 'TV Series';
	if (videoType) return videoTypeLabel(videoType);
	return null;
}

/**
 * The SHOW / MATCH row's trailing detail: "TV Series, 1974-1975" or
 * "Movie, 1999". Off TV the type is the job meta's video_type: media_type,
 * else the provider's own.
 */
export function matchDetailLine(
	job: Pick<JobView, 'year' | 'metadata_json'>,
	isTv: boolean,
	videoType: string | undefined
): string {
	const facts = (job.metadata_json?.identity as { facts?: { end_year?: number | null } } | undefined)?.facts;
	return [matchKind(isTv, videoType), yearSpan(job.year, facts?.end_year)].filter(Boolean).join(', ');
}

/**
 * A match without an IMDb id names the provider that made it; a hand-set
 * title has none.
 */
export function matchProviderLabel(job: Pick<JobView, 'metadata_json'>): string | null {
	const provider = (job.metadata_json?.identity as { provider?: string } | undefined)?.provider;
	if (!provider || provider === 'manual') return null;
	return providerLabel(provider);
}

/** "Disc 1/4", "Disc 2" with no total, or null with no disc number. */
function discNumberText(discNumber: JobView['disc_number'], discTotal: JobView['disc_total']): string | null {
	if (discNumber == null) return null;
	if (discTotal == null) return `Disc ${discNumber}`;
	return `Disc ${discNumber}/${discTotal}`;
}

/**
 * The disc facts row's text, like "Blu-ray, Disc 1/4, 6 titles", leaving out
 * the parts that are empty.
 */
export function discFactsLine(
	job: Pick<JobView, 'disc_type' | 'disc_number' | 'disc_total'>,
	titleCount: number | undefined
): string {
	return [
		discTypeLabel(job.disc_type),
		discNumberText(job.disc_number, job.disc_total),
		titleCount ? `${titleCount} titles` : null
	]
		.filter(Boolean)
		.join(', ');
}

/** The source row: what the disc came from, and its name. */
export interface SourceRow {
	label: string;
	value: string;
}

const SOURCE_KIND_LABEL: Record<'iso' | 'folder', string> = { iso: 'ISO', folder: 'Folder' };

/**
 * The source row names what the disc came from: a folder, an ISO, or a drive.
 * An ISO name needs a drive id to look its kind up; without one it is a drive.
 */
export function reviewSourceRow(
	job: Pick<JobView, 'drive_id'>,
	isoName: string | null,
	isoSourceKinds: Record<string, 'iso' | 'folder'> | null | undefined,
	driveNames: Record<string, string> | null | undefined
): SourceRow {
	const value = isoName ?? driveLabel(job.drive_id, driveNames);
	if (!isoName || !job.drive_id) return { label: 'Drive', value };
	return { label: SOURCE_KIND_LABEL[isoSourceKinds?.[job.drive_id] ?? 'iso'], value };
}

/** The applied session's text: the parked line, else the pending session's name. */
export function appliedSessionName(
	parkedLine: string | null,
	pendingSessionId: string | undefined,
	names: Map<string, string>
): string | null {
	if (parkedLine != null) return parkedLine;
	if (!pendingSessionId) return null;
	return sessionDisplayName(pendingSessionId, names);
}
