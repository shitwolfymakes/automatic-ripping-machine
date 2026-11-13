import { describe, it, expect } from 'vitest';
import { providerLabel, PROVIDER_LABELS } from '$lib/settings/provider-labels';

describe('PROVIDER_LABELS / providerLabel', () => {
	it('maps every known provider', () => {
		expect(PROVIDER_LABELS).toEqual({
			tmdb: 'TMDb',
			omdb: 'OMDb',
			tvmaze: 'TVmaze',
			tvdb: 'TVDB',
			musicbrainz: 'MusicBrainz',
			arm_server: 'ARM community database',
			thediscdb: 'TheDiscDB'
		});
		expect(providerLabel('arm_server')).toBe('ARM community database');
	});
	it('falls back to the id itself', () => {
		expect(providerLabel('somewhere_else')).toBe('somewhere_else');
	});
});
