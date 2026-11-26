// The resolve request bodies the UI sends, for the job page's in-place fact
// edit, the identify dialog's manual entry and the music search's release
// apply, the title search's apply, and whether a fact edit re-runs the episode
// match. Pure, so each rule is tested without the page or the dialog.
import type { MatchProvider, resolveJob } from '$lib/api/jobs';
import type { ExternalIds, JobView, MetadataCandidate, MetadataReleaseTrack } from '$lib/types/api.gen';
import type { EditableJobField } from '$lib/jobs/fields';

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

/** The values Use applies: the match's own, or the edited ones. */
export interface TitleApplyValues {
	title: string;
	/**
	 * The year as text, already trimmed: blank, the edit field's trimmed text,
	 * or the match's year.
	 */
	year: string;
	isSeries: boolean;
	poster: string | null;
}

// Every show id, null when missing.
function externalIdsFrom(ids: ExternalIds | null | undefined): ExternalIds {
	const given = ids ?? {};
	return {
		imdb: given.imdb ?? null,
		tmdb: given.tmdb ?? null,
		tmdb_kind: given.tmdb_kind ?? null,
		tvdb: given.tvdb ?? null,
		tvmaze: given.tvmaze ?? null
	};
}

/**
 * The title search's resolve body for a picked match. A picked match states
 * the whole show: every show id, nulls included, plus provider,
 * poster and facts in one call.
 */
export function titleMatchBody(c: MetadataCandidate, values: TitleApplyValues, posterIsManual: boolean): ResolveBody {
	return {
		title: values.title,
		year: finiteNum(values.year),
		media_type: values.isSeries ? 'tv' : 'movie',
		external_ids: externalIdsFrom(c.external_ids),
		match: {
			provider: c.provider as MatchProvider,
			// The candidate's own poster stays the automatic one; an edit is the override.
			poster_url: c.poster_url ?? null,
			poster_is_manual: posterIsManual,
			poster_url_manual: posterIsManual ? values.poster : null,
			facts: c.facts ?? null
		}
	};
}

/**
 * The title search's plain resolve body: the title, the year and the media
 * type.
 */
export function titleResolveBody(values: TitleApplyValues): ResolveBody {
	return { title: values.title, year: finiteNum(values.year), media_type: values.isSeries ? 'tv' : 'movie' };
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
