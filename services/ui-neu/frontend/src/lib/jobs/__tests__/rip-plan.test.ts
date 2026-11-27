import { describe, it, expect } from 'vitest';
import { createTrack } from '$lib/__fixtures__/job';
import { ripPlanLine, ripPlanSummary, ripPlanWarning, tickMeaning, tickTitle, type RipPlanSummary } from '../rip-plan';

const GB = 1024 ** 3;
const job = (rip_invocation: 'mkv_all' | 'per_title' | undefined, status = 'awaiting_review') =>
	({ rip_invocation, status }) as Parameters<typeof tickMeaning>[1];

describe('tickMeaning', () => {
	it.each([
		['per_title', 'awaiting_review', 'queued', 'rip-and-transcode'],
		['per_title', 'created', 'queued', 'rip-and-transcode'],
		['per_title', 'ripping', 'queued', 'transcode-only'],
		['per_title', 'ripped', 'done', 'transcode-only'],
		['mkv_all', 'awaiting_review', 'queued', 'transcode-only'],
		['mkv_all', 'ripped', 'done', 'transcode-only'],
		[undefined, 'awaiting_review', 'queued', 'transcode-only'],
		['per_title', 'awaiting_review', 'skipped', 'not-ripped'],
		['per_title', 'ripped', 'skipped', 'not-ripped'],
		['mkv_all', 'ripped', 'skipped', 'not-ripped']
	] as const)('%s, job %s, track %s is %s', (mode, status, trackStatus, expected) => {
		expect(tickMeaning({ status: trackStatus }, job(mode, status))).toBe(expected);
	});
});

describe('tickTitle', () => {
	it('words each meaning', () => {
		expect(tickTitle('rip-and-transcode')).toBe('Rip and transcode this title');
		expect(tickTitle('transcode-only')).toBe('Include this title in the transcode');
		expect(tickTitle('not-ripped')).toBe('Not ripped: it was unticked when the rip started');
	});
});

function tracks(sizes: (number | null)[], ticked: boolean[]) {
	return sizes.map((size, i) =>
		createTrack({ id: `t${i}`, index: i, expected_size_bytes: size, excluded: !ticked[i] })
	);
}

describe('ripPlanSummary', () => {
	it('is null without tracks', () => {
		expect(ripPlanSummary([], job('mkv_all'))).toBeNull();
	});

	it.each(['audio_track', 'data_dump', 'disc_backup'] as const)('is null for a %s track', (kind) => {
		expect(ripPlanSummary([createTrack({ kind })], job('mkv_all'))).toBeNull();
	});

	it('counts only the ticked titles in per-title mode', () => {
		const s = ripPlanSummary(tracks([10 * GB, 20 * GB, 30 * GB], [true, false, true]), job('per_title'));
		expect(s).toEqual({ titles: 3, ticked: 2, bytes: 40 * GB, unticked: 1, mode: 'per_title', started: false });
	});

	it('counts every title in mkv all mode', () => {
		const s = ripPlanSummary(tracks([10 * GB, 20 * GB], [true, false]), job('mkv_all'));
		expect(s).toMatchObject({ ticked: 1, bytes: 30 * GB, unticked: 1, mode: 'mkv_all' });
	});

	it('prefers the actual size over the estimate', () => {
		const t = [createTrack({ size_bytes: 5 * GB, expected_size_bytes: 9 * GB })];
		expect(ripPlanSummary(t, job('mkv_all'))?.bytes).toBe(5 * GB);
	});

	it('leaves the size unknown when a counted title has none', () => {
		expect(ripPlanSummary(tracks([10 * GB, null], [true, true]), job('mkv_all'))?.bytes).toBeNull();
	});

	it('ignores the size of an unticked title in per-title mode', () => {
		expect(ripPlanSummary(tracks([10 * GB, null], [true, false]), job('per_title'))?.bytes).toBe(10 * GB);
	});

	it('is started once the job leaves the review states', () => {
		expect(ripPlanSummary(tracks([GB], [true]), job('per_title', 'ripping'))?.started).toBe(true);
	});
});

const summary = (o: Partial<RipPlanSummary>): RipPlanSummary => ({
	titles: 4,
	ticked: 2,
	bytes: 58.3 * GB,
	unticked: 2,
	mode: 'per_title',
	started: false,
	...o
});

describe('ripPlanLine', () => {
	it('states the per-title rip', () => {
		expect(ripPlanLine(summary({}))).toBe('Rips 2 of 4 titles, about 58.3 GB');
	});

	it('states the mkv all rip with the transcode count', () => {
		expect(ripPlanLine(summary({ mode: 'mkv_all', bytes: 116.6 * GB }))).toBe(
			'Rips all 4 titles, about 116.6 GB. 2 transcode.'
		);
	});

	it('drops the size clause when a size is unknown', () => {
		expect(ripPlanLine(summary({ bytes: null }))).toBe('Rips 2 of 4 titles');
		expect(ripPlanLine(summary({ mode: 'mkv_all', bytes: null }))).toBe('Rips all 4 titles. 2 transcode.');
	});

	it('speaks only of the transcode after Start', () => {
		expect(ripPlanLine(summary({ started: true }))).toBe('2 of 4 titles transcode');
		expect(ripPlanLine(summary({ started: true, mode: 'mkv_all' }))).toBe('2 of 4 titles transcode');
	});
});

describe('ripPlanWarning', () => {
	it('warns for mkv all with unticked titles', () => {
		expect(ripPlanWarning(summary({ mode: 'mkv_all', bytes: 116.6 * GB }))).toBe(
			'All 4 titles still rip (about 116.6 GB). Unticked titles are only left out of the transcode.'
		);
	});

	it('drops the size when unknown', () => {
		expect(ripPlanWarning(summary({ mode: 'mkv_all', bytes: null }))).toBe(
			'All 4 titles still rip. Unticked titles are only left out of the transcode.'
		);
	});

	it('is null for per-title mode and for nothing unticked', () => {
		expect(ripPlanWarning(summary({}))).toBeNull();
		expect(ripPlanWarning(summary({ mode: 'mkv_all', unticked: 0, ticked: 4 }))).toBeNull();
	});
});
