// What the weighted identify says about its own decision (`metadata_json.identify_match`), in words.
import type { IdentifyMatch, IdentitySuggestion, JobView, MatchCandidate } from '$lib/types/api.gen';
import { providerLabel } from '$lib/settings/provider-labels';

type WithMeta = { metadata_json?: JobView['metadata_json'] };

const FLAG_WORDS: Record<string, string> = {
	numbers_differ: 'numbers differ',
	numbers_partial: 'some numbers differ',
	disc_number_missing: 'disc number missing',
	candidate_sequel_number: 'has a sequel number the disc lacks',
	year_mismatch: 'year differs',
	runtime_far: 'runtime far off',
	edition_tolerance: 'runtime fits an extended edition',
	text_disagrees: "the disc's text and runtime don't look like this title"
};
// Which part of the score a flag explains.
const PART_FLAGS: Record<'title' | 'year' | 'runtime', string[]> = {
	title: ['numbers_differ', 'numbers_partial', 'disc_number_missing', 'candidate_sequel_number'],
	year: ['year_mismatch'],
	runtime: ['runtime_far', 'edition_tolerance']
};
const TEXT_SOURCES: Record<string, string> = {
	bd_title: 'disc title metadata',
	iso_name: 'file name',
	label: 'volume label'
};
const RUNTIME_SOURCES: Record<string, string> = {
	structure: 'disc structure',
	titles: 'title list',
	episodes: 'episode lengths'
};

export function identifyMatchOf(job: WithMeta | null | undefined): IdentifyMatch | null {
	return job?.metadata_json?.identify_match ?? null;
}

/** The flags in words, comma separated; a flag with no wording is left out. */
export function flagWords(flags: string[] | undefined): string {
	return (flags ?? [])
		.map((f) => FLAG_WORDS[f])
		.filter(Boolean)
		.join(', ');
}

/** The candidate that explains the applied title: the row the operator picked, else the winner. */
export function explainedCandidate(match: IdentifyMatch): MatchCandidate | null {
	return match.candidates?.[match.picked ?? 0] ?? null;
}

/** The disc's own runtime in minutes (its main feature, or one episode), or null when the disc gave none. */
export function discRuntime(match: IdentifyMatch | null): number | null {
	return match?.evidence.runtime_min?.[0] ?? null;
}

const minutes = (n: number) => `${Math.round(n)} min`;

export interface ShortlistRow {
	index: number;
	title: string;
	kind: string;
	runtime: string;
	score: string;
	note: string;
}

/** The shortlist's rows: the suggestion's alternatives, each with the breakdown flags of its own candidate. */
export function shortlistRows(suggestion: IdentitySuggestion, match: IdentifyMatch | null): ShortlistRow[] {
	return (suggestion.alternatives ?? []).map((a, index) => ({
		index,
		title: a.year != null ? `${a.title} (${a.year})` : a.title,
		kind: a.kind === 'tv' ? 'TV' : 'Movie',
		runtime: a.runtime != null ? minutes(a.runtime) : 'unknown',
		score: a.score.toFixed(0),
		note: flagWords(match?.candidates?.[index]?.flags)
	}));
}

export interface MatchPart {
	label: string;
	points: string;
	detail: string;
}

export interface MatchExplanation {
	parts: MatchPart[];
	evidence: string[];
}

/** The candidate's flags that explain one part of its score, in words. */
function partFlags(c: MatchCandidate, part: keyof typeof PART_FLAGS): string {
	return flagWords((c.flags ?? []).filter((f) => PART_FLAGS[part].includes(f)));
}

const withFlags = (detail: string, flags: string) => (flags ? `${detail}, ${flags}` : detail);

function yearDetail(match: IdentifyMatch, c: MatchCandidate): string {
	const years = match.evidence.years ?? [];
	if (c.year == null) return 'no year to compare';
	const same = years.find((y) => y.year === c.year);
	if (same) return `year ${c.year} from the ${TEXT_SOURCES[same.sources[0]] ?? same.sources[0]}`;
	const detail =
		years.length > 0 ? `year ${c.year}, the disc says ${years[0].year}` : `year ${c.year}, the disc gives none`;
	return withFlags(detail, partFlags(c, 'year'));
}

function runtimeDetail(match: IdentifyMatch, c: MatchCandidate): string {
	const disc = discRuntime(match);
	if (c.runtime == null || disc == null) return 'no runtime to compare';
	return withFlags(`runtime ${Math.round(c.runtime)} vs disc ${Math.round(disc)} min`, partFlags(c, 'runtime'));
}

function evidenceLines(match: IdentifyMatch): string[] {
	const lines: string[] = [];
	const queries = match.queries ?? [];
	if (match.exact) lines.push(`Found by an exact match (${providerLabel(match.exact)}), not by searching`);
	if (queries.length > 0) lines.push(`Searched for ${queries.map((q) => `"${q.text}"`).join(', ')}`);
	const years = match.evidence.years ?? [];
	if (years.length > 0)
		lines.push(
			`Year ${years.map((y) => `${y.year} from the ${TEXT_SOURCES[y.sources[0]] ?? y.sources[0]}`).join(', ')}`
		);
	const disc = discRuntime(match);
	const source = match.evidence.runtime_source;
	if (disc != null) lines.push(`Disc runtime ${minutes(disc)}${source ? ` from the ${RUNTIME_SOURCES[source]}` : ''}`);
	return lines;
}

/** Why the explained candidate scored as it did (spec 6), or null when the search stored no candidate. */
export function matchExplanation(match: IdentifyMatch | null): MatchExplanation | null {
	const c = match ? explainedCandidate(match) : null;
	if (!match || !c) return null;
	const p = c.parts;
	const titleFlags = partFlags(c, 'title');
	const found = (c.providers ?? []).map(providerLabel).join(' and ');
	return {
		parts: [
			{ label: 'Title', points: p.title.toFixed(1), detail: titleFlags ? `title ${titleFlags}` : 'title matches' },
			{ label: 'Year', points: p.year.toFixed(1), detail: yearDetail(match, c) },
			{ label: 'Runtime', points: p.runtime.toFixed(1), detail: runtimeDetail(match, c) },
			{
				label: 'Kind',
				points: p.kind.toFixed(1),
				detail: [c.kind === 'tv' ? 'TV show' : 'movie', match.evidence.kind_reasons?.[0]].filter(Boolean).join(', ')
			},
			{ label: 'Agreement', points: p.agreement.toFixed(1), detail: found ? `found by ${found}` : 'one provider' }
		],
		evidence: evidenceLines(match)
	};
}

/**
 * The closest rejected candidate of a no-match, in words: `Blade Runner 2099 (2026, TV), numbers differ`.
 * Null when the search rejected nothing.
 */
export function closestMiss(match: IdentifyMatch | null): string | null {
	const c = match?.decision === 'no_match' ? match.candidates?.[0] : undefined;
	if (!c) return null;
	const tags = [c.year != null ? String(c.year) : null, c.kind === 'tv' ? 'TV' : null].filter(Boolean).join(', ');
	const why = flagWords(c.flags);
	return `${c.title}${tags ? ` (${tags})` : ''}${why ? `, ${why}` : ''}`;
}
