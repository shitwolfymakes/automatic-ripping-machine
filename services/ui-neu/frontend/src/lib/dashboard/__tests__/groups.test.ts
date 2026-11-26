import { describe, it, expect } from 'vitest';
import { isAwaitingAction } from '$lib/jobs/status';
import { groupActiveJobs } from '$lib/dashboard/groups';

const job = (status: string, tp: any = null) => ({ status, transcode_progress: tp }) as any;

describe('isAwaitingAction (FINISHING membership)', () => {
	it('ripped + no session -> awaiting action (in FINISHING)', () => {
		expect(isAwaitingAction(job('ripped', null))).toBe(true);
	});
	it('identified -> NOT awaiting action (pre-rip; shows on the review card, not FINISHING)', () => {
		expect(isAwaitingAction(job('identified', null))).toBe(false);
	});
	it('ripped + transcoding -> NOT awaiting (leaves FINISHING)', () => {
		expect(isAwaitingAction(job('ripped', { state: 'transcoding', tasks_total: 1, tasks_done: 0, percent: 0 }))).toBe(
			false
		);
	});
	it('ripped + done -> NOT awaiting (leaves dashboard entirely)', () => {
		expect(isAwaitingAction(job('ripped', { state: 'done', tasks_total: 1, tasks_done: 1, percent: 100 }))).toBe(false);
	});
	it('ripping -> not awaiting (it is an active rip)', () => {
		expect(isAwaitingAction(job('ripping', null))).toBe(false);
	});
});

const idJob = (id: string, status: string | undefined, tp: any = null) =>
	({ id, status, transcode_progress: tp }) as any;
const ids = (jobs: any[]) => jobs.map((j) => j.id);
const none = new Set<string>();

describe('groupActiveJobs', () => {
	it('sorts each status into its section, keeping the order of the input', () => {
		const active = [
			idJob('a', 'ripping'),
			idJob('b', 'created'),
			idJob('c', 'awaiting_user_id'),
			idJob('d', 'ripping'),
			idJob('e', 'ripped'),
			idJob('f', 'created')
		];
		const g = groupActiveJobs(active, none);
		expect(ids(g.scanning)).toEqual(['b', 'f']);
		expect(ids(g.ripping)).toEqual(['a', 'd']);
		expect(ids(g.waiting)).toEqual(['c', 'e']);
		expect(ids(g.finishing)).toEqual([]);
	});
	it('reads a missing status as no section at all', () => {
		const g = groupActiveJobs([idJob('a', undefined)], none);
		expect([g.scanning, g.waiting, g.ripping, g.finishing].map(ids)).toEqual([[], [], [], []]);
	});
	it('leaves a dismissed review job out of waiting', () => {
		const g = groupActiveJobs([idJob('a', 'awaiting_user_id')], new Set(['a']));
		expect(ids(g.waiting)).toEqual([]);
		expect(ids(g.finishing)).toEqual([]);
	});
	it('keeps an identified job in waiting and out of finishing (identified is a review-card status)', () => {
		const g = groupActiveJobs([idJob('a', 'identified')], none);
		expect(ids(g.waiting)).toEqual(['a']);
		expect(ids(g.finishing)).toEqual([]);
	});
	it('puts a ripped job with no session in waiting and not finishing', () => {
		const g = groupActiveJobs([idJob('a', 'ripped')], none);
		expect(ids(g.waiting)).toEqual(['a']);
		expect(ids(g.finishing)).toEqual([]);
	});
	it('puts the same ripped job in finishing once it is dismissed', () => {
		const g = groupActiveJobs([idJob('a', 'ripped')], new Set(['a']));
		expect(ids(g.waiting)).toEqual([]);
		expect(ids(g.finishing)).toEqual(['a']);
	});
	it('puts a ripped job with a session in neither waiting nor finishing', () => {
		const tp = { state: 'transcoding', tasks_total: 1, tasks_done: 0, percent: 0 };
		const g = groupActiveJobs([idJob('a', 'ripped', tp)], none);
		expect(ids(g.waiting)).toEqual([]);
		expect(ids(g.finishing)).toEqual([]);
	});
});
