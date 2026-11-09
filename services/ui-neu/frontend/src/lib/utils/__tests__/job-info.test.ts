import { describe, it, expect } from 'vitest';
import { jobInfoText, jobInfoResolveBody } from '$lib/utils/job-info';
import type { JobInfoText } from '$lib/utils/job-info';

describe('jobInfoResolveBody', () => {
	const fields: JobInfoText = { title: 'Alien', year: '1979', season: '2', discNumber: '3', discTotal: '4' };

	it('trims the title', () => {
		expect(jobInfoResolveBody({ ...fields, title: '  Alien  ' }, false).title).toBe('Alien');
	});

	it('sends each number from a digit string', () => {
		expect(jobInfoResolveBody(fields, true)).toMatchObject({ year: 1979, season: 2, disc_number: 3, disc_total: 4 });
	});

	it('sends a number from a padded string', () => {
		expect(jobInfoResolveBody({ ...fields, year: ' 7 ' }, false).year).toBe(7);
	});

	it('sends null for an empty string', () => {
		const body = jobInfoResolveBody({ ...fields, year: '', season: '', discNumber: '', discTotal: '' }, true);
		expect(body).toMatchObject({ year: null, season: null, disc_number: null, disc_total: null });
	});

	it('sends null for a cleared number input', () => {
		const cleared = {
			...fields,
			year: null,
			season: null,
			discNumber: null,
			discTotal: null
		} as unknown as JobInfoText;
		expect(jobInfoResolveBody(cleared, true)).toMatchObject({
			year: null,
			season: null,
			disc_number: null,
			disc_total: null
		});
	});

	it('sends a number value as a number input binds it', () => {
		const bound = { ...fields, year: 1979, season: 0, discNumber: 2, discTotal: 3 } as unknown as JobInfoText;
		expect(jobInfoResolveBody(bound, true)).toMatchObject({ year: 1979, season: 0, disc_number: 2, disc_total: 3 });
	});

	it('includes season when touched', () => {
		const body = jobInfoResolveBody(fields, true);
		expect('season' in body).toBe(true);
		expect(body.season).toBe(2);
	});

	it('omits season when untouched', () => {
		expect('season' in jobInfoResolveBody(fields, false)).toBe(false);
	});

	it('keeps the key order, season after year when present', () => {
		expect(Object.keys(jobInfoResolveBody(fields, true))).toEqual([
			'title',
			'year',
			'season',
			'disc_number',
			'disc_total'
		]);
		expect(Object.keys(jobInfoResolveBody(fields, false))).toEqual(['title', 'year', 'disc_number', 'disc_total']);
	});
});

describe('jobInfoText', () => {
	it('shows every field as text, a zero number included', () => {
		expect(jobInfoText({ title: 'Alien', year: 1979, season: 0, disc_number: 2, disc_total: 3 })).toEqual({
			title: 'Alien',
			year: '1979',
			season: '0',
			discNumber: '2',
			discTotal: '3'
		});
	});

	it('shows a null field as an empty string', () => {
		expect(jobInfoText({ title: null, year: null, season: null, disc_number: null, disc_total: null })).toEqual({
			title: '',
			year: '',
			season: '',
			discNumber: '',
			discTotal: ''
		});
	});

	it('shows an undefined field as an empty string', () => {
		const job = {} as Parameters<typeof jobInfoText>[0];
		expect(jobInfoText(job)).toEqual({ title: '', year: '', season: '', discNumber: '', discTotal: '' });
	});
});
