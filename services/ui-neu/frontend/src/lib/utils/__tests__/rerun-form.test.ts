import { describe, expect, it } from 'vitest';
import { rerunRequest, type RerunForm } from '../rerun-form';

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
