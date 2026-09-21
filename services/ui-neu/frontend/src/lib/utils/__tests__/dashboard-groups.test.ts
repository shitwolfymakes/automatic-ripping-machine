import { describe, it, expect } from 'vitest';
import { isAwaitingAction } from '$lib/utils/job-status';

const job = (status: string, tp: any = null) => ({ status, transcode_progress: tp }) as any;

describe('isAwaitingAction (FINISHING membership)', () => {
	it('ripped + no session -> awaiting action (in FINISHING)', () => {
		expect(isAwaitingAction(job('ripped', null))).toBe(true);
	});
	it('identified -> NOT awaiting action (pre-rip; shows on the review card, not FINISHING)', () => {
		expect(isAwaitingAction(job('identified', null))).toBe(false);
	});
	it('ripped + transcoding -> NOT awaiting (leaves FINISHING)', () => {
		expect(isAwaitingAction(job('ripped', { state: 'transcoding', tasks_total: 1, tasks_done: 0, percent: 0 }))).toBe(false);
	});
	it('ripped + done -> NOT awaiting (leaves dashboard entirely)', () => {
		expect(isAwaitingAction(job('ripped', { state: 'done', tasks_total: 1, tasks_done: 1, percent: 100 }))).toBe(false);
	});
	it('ripping -> not awaiting (it is an active rip)', () => {
		expect(isAwaitingAction(job('ripping', null))).toBe(false);
	});
});
