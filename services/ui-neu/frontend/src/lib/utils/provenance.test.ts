import { describe, it, expect } from 'vitest';
import { provenanceLine } from './provenance';

describe('provenanceLine', () => {
	it('names where a season came from', () => {
		expect(provenanceLine('season', { season: 'label' })).toBe('Season from the disc label');
		expect(provenanceLine('disc_number', { disc_number: 'manual' })).toBe('Disc number set by you');
		expect(provenanceLine('season', { season: 'episodes_tmdb' })).toBe('Season matched by TMDb');
		expect(provenanceLine('season', {})).toBeNull();
		expect(provenanceLine('season', null)).toBeNull();
		expect(provenanceLine('season', { season: 'bogus' })).toBeNull();
	});
});
