import { describe, it, expect } from 'vitest';
import {
	closestMiss,
	discRuntime,
	explainedCandidate,
	flagWords,
	identifyMatchOf,
	matchExplanation,
	shortlistRows
} from '$lib/jobs/match-explain';
import {
	BLADE_RUNNER_ACCEPTED,
	BLADE_RUNNER_NO_MATCH,
	TOTAL_RECALL_SHORTLIST,
	TOTAL_RECALL_SUGGESTION
} from '$lib/__fixtures__/identify-match';

describe('identifyMatchOf', () => {
	it('reads the stored breakdown, or null', () => {
		expect(identifyMatchOf({ metadata_json: { identify_match: BLADE_RUNNER_ACCEPTED } as never })).toBe(
			BLADE_RUNNER_ACCEPTED
		);
		expect(identifyMatchOf({ metadata_json: {} })).toBeNull();
		expect(identifyMatchOf(null)).toBeNull();
	});
});

describe('flagWords', () => {
	it('words the known flags and drops the rest', () => {
		expect(flagWords(['numbers_differ', 'something_new', 'runtime_far'])).toBe('numbers differ, runtime far off');
		expect(flagWords(undefined)).toBe('');
	});
});

describe('matchExplanation (Blade Runner 2049, accepted)', () => {
	const why = matchExplanation(BLADE_RUNNER_ACCEPTED)!;
	it('lists the five parts with their points and the evidence behind each', () => {
		expect(why.parts.map((p) => [p.label, p.points, p.detail])).toEqual([
			['Title', '45.0', 'title matches'],
			['Year', '13.5', 'year 2017 from the file name'],
			['Runtime', '20.0', 'runtime 164 vs disc 163 min'],
			['Kind', '7.0', 'movie, single 163-min feature'],
			['Agreement', '6.0', 'found by TMDb and OMDb']
		]);
	});
	it('names the queries, the year source and the runtime source', () => {
		expect(why.evidence).toEqual([
			'Searched for "Blade Runner 2049"',
			'Year 2017 from the file name',
			'Disc runtime 163 min from the disc structure'
		]);
	});
	it('says so when the hit was found by an exact route', () => {
		const exact = { ...BLADE_RUNNER_ACCEPTED, decision: 'exact' as const, exact: 'thediscdb' as const, queries: [] };
		expect(matchExplanation(exact)!.evidence[0]).toBe('Found by an exact match (TheDiscDB), not by searching');
	});
	it('is null with no stored candidate', () => {
		expect(matchExplanation({ ...BLADE_RUNNER_ACCEPTED, candidates: [] })).toBeNull();
		expect(matchExplanation(null)).toBeNull();
	});
	it('explains the shortlist row the operator picked', () => {
		const picked = { ...TOTAL_RECALL_SHORTLIST, picked: 1 };
		expect(explainedCandidate(picked)?.year).toBe(2012);
		const runtime = matchExplanation(picked)!.parts.find((p) => p.label === 'Runtime')!;
		expect(runtime.detail).toBe('runtime 118 vs disc 113 min, runtime far off');
		expect(matchExplanation(picked)!.parts[0].detail).toBe('title matches');
	});
});

describe('shortlistRows (Total Recall)', () => {
	it('gives each alternative its title, kind, runtime, score and flag note', () => {
		expect(shortlistRows(TOTAL_RECALL_SUGGESTION, TOTAL_RECALL_SHORTLIST)).toEqual([
			{ index: 0, title: 'Total Recall (1990)', kind: 'Movie', runtime: '113 min', score: '71', note: '' },
			{
				index: 1,
				title: 'Total Recall (2012)',
				kind: 'Movie',
				runtime: '118 min',
				score: '67',
				note: 'runtime far off'
			}
		]);
		expect(discRuntime(TOTAL_RECALL_SHORTLIST)).toBe(113);
	});
	it('copes with no stored breakdown', () => {
		expect(shortlistRows(TOTAL_RECALL_SUGGESTION, null).map((r) => r.note)).toEqual(['', '']);
	});
});

describe('closestMiss', () => {
	it('names the closest rejected candidate and its flags', () => {
		expect(closestMiss(BLADE_RUNNER_NO_MATCH)).toBe('Blade Runner 2099 (2026, TV), numbers differ');
	});
	it('is null for anything but a no-match with candidates', () => {
		expect(closestMiss(BLADE_RUNNER_ACCEPTED)).toBeNull();
		expect(closestMiss({ ...BLADE_RUNNER_NO_MATCH, candidates: [] })).toBeNull();
		expect(closestMiss(null)).toBeNull();
	});
});
