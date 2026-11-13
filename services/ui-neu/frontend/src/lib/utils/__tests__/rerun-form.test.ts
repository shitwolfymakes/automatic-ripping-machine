import { describe, expect, it } from 'vitest';
import type { EpisodeSourceOption } from '../../episodes/sources';
import { fillRestForm, fixMatchForm, rerunRequest, type RerunForm } from '../../jobs/rerun-form';

const BARE: RerunForm = { source: 'tvmaze', season: null, disc: null, tolerance: null };

describe('rerunRequest', () => {
	it('sends only the source and apply for a bare form', () => {
		expect(rerunRequest(BARE, true)).toEqual({ source: 'tvmaze', apply: true });
		expect(rerunRequest(BARE, false)).toEqual({ source: 'tvmaze', apply: false });
	});

	it('asks to scan every season, with no season, for a season of scan', () => {
		expect(rerunRequest({ ...BARE, season: 'scan' }, false)).toEqual({
			source: 'tvmaze',
			apply: false,
			scan_seasons: true
		});
	});

	it('sends a numeric season, 0 included', () => {
		expect(rerunRequest({ ...BARE, season: 3 }, true)).toEqual({ source: 'tvmaze', apply: true, season: 3 });
		expect(rerunRequest({ ...BARE, season: 0 }, true)).toEqual({ source: 'tvmaze', apply: true, season: 0 });
	});

	it('sends a disc, 0 included', () => {
		expect(rerunRequest({ ...BARE, disc: 2 }, true)).toEqual({ source: 'tvmaze', apply: true, disc_number: 2 });
		expect(rerunRequest({ ...BARE, disc: 0 }, true)).toEqual({ source: 'tvmaze', apply: true, disc_number: 0 });
	});

	it('sends a tolerance, 0 included', () => {
		expect(rerunRequest({ ...BARE, tolerance: 5 }, true)).toEqual({ source: 'tvmaze', apply: true, tolerance: 5 });
		expect(rerunRequest({ ...BARE, tolerance: 0 }, true)).toEqual({ source: 'tvmaze', apply: true, tolerance: 0 });
	});

	it('sends every field the operator set', () => {
		expect(rerunRequest({ source: 'tvdb', season: 2, disc: 1, tolerance: 4 }, false)).toEqual({
			source: 'tvdb',
			apply: false,
			season: 2,
			disc_number: 1,
			tolerance: 4
		});
	});
});

const ALL_ON: EpisodeSourceOption[] = [
	{ id: 'tmdb', label: 'TMDb', disabled: false },
	{ id: 'tvmaze', label: 'TVmaze', disabled: false },
	{ id: 'tvdb', label: 'TVDB', disabled: false }
];
const NO_JOB = { season: null, disc_number: null };

describe('fixMatchForm', () => {
	it('opens on the active source, bare or with the episodes_ prefix', () => {
		expect(fixMatchForm('tvdb', ALL_ON, null, NO_JOB).source).toBe('tvdb');
		expect(fixMatchForm('episodes_tvmaze', ALL_ON, null, NO_JOB).source).toBe('tvmaze');
		expect(fixMatchForm('episodes_tmdb', ALL_ON, null, NO_JOB).source).toBe('tmdb');
	});

	it('opens on the first option that is on for a source outside the three', () => {
		const options = [{ ...ALL_ON[0], disabled: true }, ALL_ON[1], ALL_ON[2]];
		expect(fixMatchForm('episodes_other', options, null, NO_JOB).source).toBe('tvmaze');
	});

	it('opens on the first option that is on when there is no active source', () => {
		const options = [{ ...ALL_ON[0], disabled: true }, { ...ALL_ON[1], disabled: true }, ALL_ON[2]];
		expect(fixMatchForm(null, options, null, NO_JOB).source).toBe('tvdb');
	});

	it('opens on TMDb when every option is off', () => {
		const off = ALL_ON.map((o) => ({ ...o, disabled: true }));
		expect(fixMatchForm(null, off, null, NO_JOB).source).toBe('tmdb');
		expect(fixMatchForm(null, [], null, NO_JOB).source).toBe('tmdb');
	});

	it('takes the guessed season over the job, 0 included', () => {
		expect(fixMatchForm('tvdb', ALL_ON, 2, { season: 5, disc_number: null }).season).toBe(2);
		expect(fixMatchForm('tvdb', ALL_ON, 0, { season: 5, disc_number: null }).season).toBe(0);
	});

	it('falls back to the job season, then to null', () => {
		expect(fixMatchForm('tvdb', ALL_ON, null, { season: 5, disc_number: null }).season).toBe(5);
		expect(fixMatchForm('tvdb', ALL_ON, null, NO_JOB).season).toBeNull();
	});

	it('builds the whole form with the job disc and no tolerance', () => {
		expect(fixMatchForm('tvdb', ALL_ON, 2, { season: 5, disc_number: 3 })).toEqual({
			source: 'tvdb',
			season: 2,
			disc: 3,
			tolerance: null
		});
		expect(fixMatchForm('tvdb', ALL_ON, null, NO_JOB)).toEqual({
			source: 'tvdb',
			season: null,
			disc: null,
			tolerance: null
		});
	});
});

describe('fillRestForm', () => {
	it("uses the job's season over the rows'", () => {
		const rows = [{ handSet: true, season: 4 }];
		expect(fillRestForm('tvdb', { season: 1, disc_number: null }, rows)).toEqual({
			source: 'tvdb',
			season: 1,
			disc: null,
			tolerance: null
		});
	});

	it('uses the one season every hand-set row shares', () => {
		const rows = [
			{ handSet: true, season: 2 },
			{ handSet: true, season: 2 }
		];
		expect(fillRestForm('tmdb', NO_JOB, rows).season).toBe(2);
	});

	it('sends no season when hand-set rows disagree', () => {
		const rows = [
			{ handSet: true, season: 2 },
			{ handSet: true, season: 3 }
		];
		expect(fillRestForm('tmdb', NO_JOB, rows).season).toBeNull();
	});

	it('sends no season when hand-set rows have none', () => {
		expect(fillRestForm('tmdb', NO_JOB, [{ handSet: true, season: null }]).season).toBeNull();
	});

	it('sends no season when no row is hand-set', () => {
		expect(fillRestForm('tmdb', NO_JOB, []).season).toBeNull();
	});

	it('ignores rows that are not hand-set', () => {
		const rows = [
			{ handSet: true, season: 2 },
			{ handSet: false, season: 7 }
		];
		expect(fillRestForm('tmdb', NO_JOB, rows).season).toBe(2);
	});

	it("carries the job's disc, or none", () => {
		expect(fillRestForm('tvmaze', { season: 1, disc_number: 2 }, [])).toEqual({
			source: 'tvmaze',
			season: 1,
			disc: 2,
			tolerance: null
		});
		expect(fillRestForm('tvmaze', { season: 1, disc_number: null }, []).disc).toBeNull();
	});
});
