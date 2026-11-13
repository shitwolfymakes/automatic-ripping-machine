import { describe, it, expect } from 'vitest';
import { parkedSessionLine, sessionDisplayName } from '../sessions/parked-session';

describe('sessionDisplayName', () => {
	const names = new Map([['ses_a', 'Plex 1080p']]);
	it('gives the name of a known session', () => {
		expect(sessionDisplayName('ses_a', names)).toBe('Plex 1080p');
	});
	it('shows an unknown short id as itself', () => {
		expect(sessionDisplayName('ses_b', names)).toBe('ses_b');
	});
	it('shortens an unknown id of 16 or more characters', () => {
		expect(sessionDisplayName('ses_0123456789abcdef', names)).toBe('ses_0123456789a...');
	});
});

describe('parkedSessionLine', () => {
	const names = new Map([['ses_a', 'Plex 1080p']]);
	it('null when nothing is parked', () => {
		expect(parkedSessionLine({ status: 'identified', parked_session_ids: [] }, names)).toBeNull();
	});
	it('null when the job has no parked_session_ids', () => {
		expect(parkedSessionLine({ status: 'identified' }, names)).toBeNull();
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
