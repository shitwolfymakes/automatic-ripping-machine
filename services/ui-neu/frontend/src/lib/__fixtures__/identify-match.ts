// Test mirrors of what the weighted identify stores in `metadata_json.identify_match` and the shortlist
// suggestion, shaped like the three real discs the spec works through.
import type { IdentifyMatch, IdentitySuggestion, MatchCandidate } from '$lib/types/api.gen';

const THRESHOLDS = { accept: 65, margin: 10, floor: 40, title_min: 0.7 };

function candidate(over: Partial<MatchCandidate> & Pick<MatchCandidate, 'title' | 'score'>): MatchCandidate {
	return {
		year: null,
		kind: 'movie',
		runtime: null,
		providers: ['tmdb'],
		provider: 'tmdb',
		ids: {},
		parts: { title: 0, year: 0, runtime: 0, kind: 0, agreement: 0 },
		flags: [],
		...over
	};
}

/** Blade Runner 2049 (3D): accepted on its title, the file name's year and a 163 vs 164 min runtime. */
export const BLADE_RUNNER_ACCEPTED: IdentifyMatch = {
	version: 1,
	decision: 'accept',
	evidence: {
		titles: [
			{
				source: 'bd_title',
				text: 'Blade Runner 2049 - 3D Blu-rayTM',
				core: 'Blade Runner 2049',
				optional: ['3d', 'bluray', 'tm']
			},
			{ source: 'iso_name', text: 'Blade_Runner_2049_(2017)_[3D]', core: 'Blade Runner 2049', optional: [] }
		],
		years: [{ year: 2017, sources: ['iso_name'], reliability: 0.9 }],
		numbers: ['2049'],
		runtime_min: [163],
		runtime_source: 'structure',
		p_tv: 0.15,
		kind_reasons: ['single 163-min feature']
	},
	queries: [{ text: 'Blade Runner 2049', kinds: ['movie'] }],
	calls: { list: 2, detail: 1, cached: 0 },
	candidates: [
		candidate({
			title: 'Blade Runner 2049',
			year: 2017,
			runtime: 164,
			providers: ['tmdb', 'omdb'],
			ids: { tmdb: '335984', imdb: 'tt1856101' },
			score: 91.5,
			parts: { title: 45, year: 13.5, runtime: 20, kind: 7, agreement: 6 }
		})
	],
	shortlist: 0,
	runner_up: 24.7,
	thresholds: THRESHOLDS
};

const TOTAL_RECALL_EVIDENCE: IdentifyMatch['evidence'] = {
	titles: [{ source: 'label', text: 'TOTAL_RECALL', core: 'Total Recall', optional: [] }],
	years: [],
	numbers: [],
	runtime_min: [113],
	runtime_source: 'structure',
	p_tv: 0.1,
	kind_reasons: ['single 113-min feature']
};

const TOTAL_RECALL_ROWS: MatchCandidate[] = [
	candidate({
		title: 'Total Recall',
		year: 1990,
		runtime: 113,
		providers: ['tmdb', 'omdb'],
		ids: { tmdb: '861', imdb: 'tt0100802' },
		score: 71,
		parts: { title: 45, year: 0, runtime: 20, kind: 7, agreement: 6 }
	}),
	candidate({
		title: 'Total Recall',
		year: 2012,
		runtime: 118,
		ids: { tmdb: '64635' },
		score: 66.5,
		parts: { title: 45, year: 0, runtime: 14.5, kind: 7, agreement: 0 },
		flags: ['runtime_far']
	})
];

/** Total Recall: the 1990 film and its 2012 remake both fit a label with no year, so the operator picks. */
export const TOTAL_RECALL_SHORTLIST: IdentifyMatch = {
	version: 1,
	decision: 'shortlist',
	evidence: TOTAL_RECALL_EVIDENCE,
	queries: [{ text: 'Total Recall', kinds: ['movie'] }],
	calls: { list: 2, detail: 1, cached: 0 },
	candidates: TOTAL_RECALL_ROWS,
	shortlist: 2,
	runner_up: 66.5,
	thresholds: THRESHOLDS
};

/** The suggestion identify stores for that shortlist: no provider record, rows with ids to ask again by. */
export const TOTAL_RECALL_SUGGESTION: IdentitySuggestion = {
	reason: 'close',
	score: 71,
	provider: 'tmdb',
	title: 'Total Recall',
	year: 1990,
	kind: 'movie',
	external_ids: {},
	payload: {},
	alternatives: TOTAL_RECALL_ROWS.map((c) => ({
		title: c.title,
		year: c.year,
		kind: c.kind,
		runtime: c.runtime,
		providers: c.providers,
		provider: c.provider,
		ids: c.ids,
		score: c.score
	})),
	suggested_at: '2026-11-28T10:00:00Z'
};

/** A no-match: the only rejected candidate is the 2099 TV show, whose number differs from the disc's 2049. */
export const BLADE_RUNNER_NO_MATCH: IdentifyMatch = {
	version: 1,
	decision: 'no_match',
	evidence: { ...BLADE_RUNNER_ACCEPTED.evidence, years: [] },
	queries: [{ text: 'Blade Runner 2049', kinds: ['movie', 'tv'] }],
	calls: { list: 3, detail: 0, cached: 0 },
	candidates: [
		candidate({
			title: 'Blade Runner 2099',
			year: 2026,
			kind: 'tv',
			providers: ['tmdb'],
			ids: { tmdb: '999' },
			score: 4,
			flags: ['numbers_differ']
		})
	],
	shortlist: 0,
	thresholds: THRESHOLDS
};
