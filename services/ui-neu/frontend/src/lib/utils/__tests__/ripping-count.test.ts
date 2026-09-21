import { describe, it, expect } from 'vitest';
import { countRipping } from '$lib/utils/job-status';

const job = (status: string, tp: any = null) => ({ status, transcode_progress: tp }) as any;

describe('countRipping', () => {
	it('counts a genuinely ripping job', () => {
		expect(countRipping([job('ripping')])).toBe(1);
	});
	it('does NOT count a ripped job that is transcoding', () => {
		expect(countRipping([job('ripped', { state: 'transcoding', tasks_total: 1, tasks_done: 0, percent: 0 })])).toBe(0);
	});
	it('does NOT count a completed job', () => {
		expect(countRipping([job('ripped', { state: 'done', tasks_total: 1, tasks_done: 1, percent: 100 })])).toBe(0);
	});
	it('does NOT count a ripped job awaiting a session (terminal rip, not ripping)', () => {
		expect(countRipping([job('ripped', null)])).toBe(0);
	});
});
