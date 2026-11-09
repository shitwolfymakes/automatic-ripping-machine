// The resolve request bodies the UI sends, for the job page's in-place fact
// edit, the identify dialog's manual entry and the music search's release
// apply, and whether a fact edit re-runs the episode match. Pure, so each rule
// is tested without the page or the dialog.
import type { resolveJob } from '$lib/api/jobs';
import type { JobView, MetadataReleaseTrack } from '$lib/types/api.gen';
import type { EditableJobField } from '$lib/utils/job-fields';

export type ResolveBody = Parameters<typeof resolveJob>[1];

const num = (v: string) => (v.trim() === '' ? null : Number(v));

// Unlike `num`, a non-finite number (NaN, Infinity) also becomes null.
const finiteNum = (v: string) => {
	const n = num(v);
	return Number.isFinite(n) ? n : null;
};

/**
 * The resolve body for one edited fact. Title and year restate the identity
 * (the edited one from `raw`, the other from the job); season, disc number
 * and disc total are classifications, where a blank `raw` clears them (null).
 * A blank title throws before anything is sent.
 */
export function buildResolveBody(job: JobView, field: EditableJobField | 'title', raw: string): ResolveBody {
	if (field === 'title' && !raw.trim()) throw new Error('A title is required');
	const body: ResolveBody = {
		title: field === 'title' ? raw.trim() : (job.title ?? ''),
		year: field === 'year' ? num(raw) : (job.year ?? null)
	};
	if (field !== 'title' && field !== 'year') body[field] = num(raw);
	return body;
}

/**
 * The identify dialog's resolve body for a CD: the trimmed album as the title,
 * and `music` holding the trimmed artist, album and one track per title.
 */
export function cdIdentifyBody(f: {
	album: string;
	artist: string;
	year: number | null;
	trackTitles: string[];
}): ResolveBody {
	return {
		title: f.album.trim(),
		year: f.year ?? null,
		music: {
			artist: f.artist.trim(),
			album: f.album.trim(),
			tracks: f.trackTitles.map((t) => ({ title: t.trim() }))
		}
	};
}

/**
 * The identify dialog's resolve body for anything but a CD: the trimmed title
 * and the year, with no `music` key.
 */
export function videoIdentifyBody(f: { title: string; year: number | null }): ResolveBody {
	return { title: f.title.trim(), year: f.year ?? null };
}

/**
 * The music search's resolve body for the chosen release, with the trimmed
 * album as the title, the year, disc number and disc total parsed from their
 * fields (null when blank or not a finite number), and `music` holding the
 * trimmed artist and album and each track with its position, title, length
 * and disc number (the length and disc number null when missing).
 */
export function musicReleaseBody(
	f: { album: string; artist: string; year: string; discNumber: string; discTotal: string },
	tracks: MetadataReleaseTrack[]
): ResolveBody {
	return {
		title: f.album.trim(),
		year: finiteNum(f.year),
		disc_number: finiteNum(f.discNumber),
		disc_total: finiteNum(f.discTotal),
		music: {
			artist: f.artist.trim(),
			album: f.album.trim(),
			tracks: tracks.map((t) => ({
				position: t.position,
				title: t.title,
				length_ms: t.length_ms ?? null,
				disc_number: t.disc_number ?? null
			}))
		}
	};
}

/**
 * A TV job's season or disc change re-runs the episode match. True only when
 * `after` exists, the job is TV and its season or disc number differs, a
 * missing value counting as null on both sides.
 */
export function tvSeasonOrDiscChanged(before: JobView, after: JobView | null | undefined): boolean {
	return (
		!!after &&
		before.media_type === 'tv' &&
		((before.season ?? null) !== (after.season ?? null) || (before.disc_number ?? null) !== (after.disc_number ?? null))
	);
}
