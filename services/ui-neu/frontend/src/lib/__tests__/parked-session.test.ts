import { describe, it, expect } from 'vitest';
import { parkedSessionLine } from '../utils/parked-session';

describe('parkedSessionLine', () => {
	const names = new Map([['ses_a', 'Plex 1080p']]);
	it('null when nothing is parked', () => {
		expect(parkedSessionLine({ status: 'identified', parked_session_ids: [] }, names)).toBeNull();
	});
	it('pre-rip: applies when the rip finishes', () => {
		expect(parkedSessionLine({ status: 'awaiting_review', parked_session_ids: ['ses_a'] }, names)).toBe(
			'Plex 1080p, applies when the rip finishes'
		);
	});
	it('failed or abandoned: never promises the rip will finish', () => {
		expect(parkedSessionLine({ status: 'failed', parked_session_ids: ['ses_a'] }, names)).toBe(
			'Plex 1080p, not applied, the rip failed'
		);
		expect(parkedSessionLine({ status: 'abandoned', parked_session_ids: ['ses_a'] }, names)).toBe(
			'Plex 1080p, not applied, the job was abandoned'
		);
	});
	it('post-rip: waiting, unknown ids shortened', () => {
		expect(
			parkedSessionLine({ status: 'ripped', parked_session_ids: ['ses_a', 'ses_0123456789abcdefXYZ'] }, names)
		).toBe('Plex 1080p, ses_0123456789a..., waiting');
	});
	it('unknown ids of 15 characters or fewer are shown in full', () => {
		expect(parkedSessionLine({ status: 'ripped', parked_session_ids: ['ses_01234567890'] }, names)).toBe(
			'ses_01234567890, waiting'
		);
	});
});
