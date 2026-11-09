import { describe, it, expect } from 'vitest';
import { jobInfoText } from '$lib/utils/job-info';

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
