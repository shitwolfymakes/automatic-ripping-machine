import { describe, it, expect } from 'vitest';
import {
	effectiveJobStatus,
	isPartialComplete,
	reviewPhaseBadge,
	hasTitleMatch,
	identitySuggestionOf,
	missReason,
	providerLabel,
	PROVIDER_LABELS
} from '$lib/utils/job-status';

type TP = { state: string; tasks_total: number; tasks_done: number; percent: number } | null;
const job = (status: string, transcode_progress: TP = null) => ({ status, transcode_progress }) as any;

describe('effectiveJobStatus', () => {
	it('ripped + no session stays ripped (awaiting action)', () => {
		expect(effectiveJobStatus(job('ripped', null))).toBe('ripped');
	});
	it('ripped + transcoding -> transcoding', () => {
		expect(
			effectiveJobStatus(job('ripped', { state: 'transcoding', tasks_total: 2, tasks_done: 1, percent: 50 }))
		).toBe('transcoding');
	});
	it('ripped + done -> complete', () => {
		expect(effectiveJobStatus(job('ripped', { state: 'done', tasks_total: 2, tasks_done: 2, percent: 100 }))).toBe(
			'complete'
		);
	});
	it('ripped + done_partial -> transcode_failed (not complete — some tracks failed)', () => {
		expect(
			effectiveJobStatus(job('ripped', { state: 'done_partial', tasks_total: 2, tasks_done: 1, percent: 50 }))
		).toBe('transcode_failed');
	});
	it('ripped + failed -> transcode_failed (all tracks failed; rip itself was fine)', () => {
		expect(effectiveJobStatus(job('ripped', { state: 'failed', tasks_total: 1, tasks_done: 0, percent: 0 }))).toBe(
			'transcode_failed'
		);
	});
	it('ripped_partial + done -> complete', () => {
		expect(
			effectiveJobStatus(job('ripped_partial', { state: 'done', tasks_total: 1, tasks_done: 1, percent: 100 }))
		).toBe('complete');
	});
	it('non-post-rip status is unchanged even with a summary', () => {
		expect(
			effectiveJobStatus(job('ripping', { state: 'transcoding', tasks_total: 1, tasks_done: 0, percent: 0 }))
		).toBe('ripping');
	});
});

describe('isPartialComplete', () => {
	it('true only for done_partial', () => {
		expect(
			isPartialComplete(job('ripped', { state: 'done_partial', tasks_total: 2, tasks_done: 1, percent: 50 }))
		).toBe(true);
		expect(isPartialComplete(job('ripped', { state: 'done', tasks_total: 2, tasks_done: 2, percent: 100 }))).toBe(
			false
		);
		expect(isPartialComplete(job('ripped', null))).toBe(false);
	});
});

const badgeJob = (status: string, title: string | null = 'X', transcode_progress: TP = null) =>
	({ status, title, transcode_progress }) as any;

describe('hasTitleMatch', () => {
	it('true for a non-empty title', () => {
		expect(hasTitleMatch({ title: 'MysterySuspense' } as any)).toBe(true);
	});
	it('false for null / empty / whitespace title', () => {
		expect(hasTitleMatch({ title: null } as any)).toBe(false);
		expect(hasTitleMatch({ title: '' } as any)).toBe(false);
		expect(hasTitleMatch({ title: '   ' } as any)).toBe(false);
	});
});

describe('reviewPhaseBadge', () => {
	it('awaiting_review -> REVIEW amber', () => {
		const b = reviewPhaseBadge(badgeJob('awaiting_review'));
		expect(b.label).toBe('REVIEW');
		expect(b.accent).toContain('--color-accent-1');
	});
	it('awaiting_user_id -> IDENTIFY cyan', () => {
		expect(reviewPhaseBadge(badgeJob('awaiting_user_id')).label).toBe('IDENTIFY');
		expect(reviewPhaseBadge(badgeJob('awaiting_user_id')).accent).toContain('--color-accent-4');
	});
	it('ripped_awaiting_identify -> IDENTIFY', () => {
		expect(reviewPhaseBadge(badgeJob('ripped_awaiting_identify')).label).toBe('IDENTIFY');
	});
	it('identified -> READY primary', () => {
		const b = reviewPhaseBadge(badgeJob('identified'));
		expect(b.label).toBe('READY');
		expect(b.accent).toContain('--color-primary');
	});
	it('ripped + no title -> RIPPED | NEEDS SESSION (session wins)', () => {
		expect(reviewPhaseBadge(badgeJob('ripped', null)).label).toBe('RIPPED | NEEDS SESSION');
	});
	it('ripped + has title -> RIPPED | NEEDS SESSION', () => {
		expect(reviewPhaseBadge(badgeJob('ripped', 'MysterySuspense')).label).toBe('RIPPED | NEEDS SESSION');
	});
	it('ripped violet accent', () => {
		expect(reviewPhaseBadge(badgeJob('ripped', null)).accent).toContain('--color-accent-3');
	});
});

const SUGGESTION = {
	provider: 'tmdb',
	title: 'Iron Man',
	year: 2008,
	kind: 'movie',
	poster_url: null,
	external_ids: {},
	overview: null,
	payload: {},
	suggested_at: '2026-10-15T10:00:00Z'
};
const heldJob = (status: string, extra: Record<string, unknown> = {}) =>
	({
		status,
		title: 'MY_DISC',
		transcode_progress: null,
		metadata_json: { identity_suggestion: SUGGESTION, flags: { unidentified: true }, ...extra }
	}) as any;

describe('reviewPhaseBadge with an identity suggestion', () => {
	it('awaiting_review + suggestion -> CONFIRM TITLE', () => {
		const b = reviewPhaseBadge(heldJob('awaiting_review'));
		expect(b.label).toBe('CONFIRM TITLE');
		expect(b.accent).toBe('var(--color-accent-4)');
	});
	it('awaiting_user_id + suggestion -> CONFIRM TITLE', () => {
		expect(reviewPhaseBadge(heldJob('awaiting_user_id')).label).toBe('CONFIRM TITLE');
	});
	it('ripped_awaiting_identify + suggestion -> CONFIRM TITLE', () => {
		expect(reviewPhaseBadge(heldJob('ripped_awaiting_identify')).label).toBe('CONFIRM TITLE');
	});
	it('previously ripped still wins over a suggestion', () => {
		const b = reviewPhaseBadge(heldJob('awaiting_review', { previously_ripped: { job_id: 'job_old' } }));
		expect(b.label).toBe('ALREADY RIPPED');
	});
	it('a suggestion on another status does not change its badge', () => {
		expect(reviewPhaseBadge(heldJob('identified')).label).toBe('READY');
	});
});

describe('identitySuggestionOf', () => {
	it('returns the held suggestion', () => {
		expect(identitySuggestionOf(heldJob('awaiting_review'))?.title).toBe('Iron Man');
	});
	it('null when absent, null metadata, or no job', () => {
		expect(identitySuggestionOf({ metadata_json: {} } as any)).toBeNull();
		expect(identitySuggestionOf({ metadata_json: { identity_suggestion: null } } as any)).toBeNull();
		expect(identitySuggestionOf({ metadata_json: null } as any)).toBeNull();
		expect(identitySuggestionOf(null)).toBeNull();
		expect(identitySuggestionOf(undefined)).toBeNull();
	});
});

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

import { transcodeColumnStatus } from '$lib/utils/job-status';

const tp = (state: string, tasks_total: number, tasks_done: number, tasks_failed: number) =>
	({ status: 'ripped', transcode_progress: { state, tasks_total, tasks_done, tasks_failed, percent: 0 } }) as any;

describe('transcodeColumnStatus', () => {
	it('null when no transcode_progress', () => {
		expect(transcodeColumnStatus({ status: 'ripped', transcode_progress: null } as any)).toBeNull();
	});
	it('done -> Complete/complete (green; the all-succeed gate)', () => {
		expect(transcodeColumnStatus(tp('done', 4, 4, 0))).toEqual({ label: 'Complete', badgeStatus: 'complete' });
	});
	it('done_partial -> Transcode failed (red)', () => {
		expect(transcodeColumnStatus(tp('done_partial', 4, 2, 2))).toEqual({
			label: 'Transcode failed',
			badgeStatus: 'transcode_failed'
		});
	});
	it('failed -> Transcode failed (red)', () => {
		expect(transcodeColumnStatus(tp('failed', 4, 0, 4))).toEqual({
			label: 'Transcode failed',
			badgeStatus: 'transcode_failed'
		});
	});
	it('transcoding + tasks_failed>0 -> Failed — retrying (red, never green/blue)', () => {
		expect(transcodeColumnStatus(tp('transcoding', 4, 1, 1))).toEqual({
			label: 'Failed, retrying 1/4',
			badgeStatus: 'transcode_failed'
		});
	});
	it('transcoding + no failures -> Transcoding N/M (blue)', () => {
		expect(transcodeColumnStatus(tp('transcoding', 4, 2, 0))).toEqual({
			label: 'Transcoding 2/4',
			badgeStatus: 'transcoding'
		});
	});
});

describe('missReason', () => {
	const a = (outcome: string, extra: Record<string, unknown> = {}) => ({
		source: 'tmdb',
		step: 'title',
		kind: 'movie',
		outcome,
		detail: null,
		...extra
	});
	const missed = (attempts: unknown[] | null | undefined, over: Record<string, unknown> = {}) =>
		({
			status: 'awaiting_user_id',
			title: 'MY_DISC',
			metadata_json: { flags: {}, identify_attempts: attempts },
			...over
		}) as any;

	it('no attempts (an older job) gives no line', () => {
		expect(missReason(missed(undefined))).toBeNull();
		expect(missReason(missed(null))).toBeNull();
		expect(missReason(missed([]))).toBeNull();
		expect(missReason({ status: 'awaiting_user_id', title: 'X', metadata_json: null } as any)).toBeNull();
	});
	it('a job that is not a miss gives no line', () => {
		expect(missReason(missed([a('miss')], { status: 'awaiting_review' }))).toBeNull();
	});
	it('an unidentified job past the review gate still gets the line', () => {
		const job = missed([a('miss', { detail: 'HEAT' })], {
			status: 'identified',
			metadata_json: { flags: { unidentified: true }, identify_attempts: [a('miss', { detail: 'HEAT' })] }
		});
		expect(missReason(job)).toContain('"HEAT"');
	});
	it('any no_sources wins', () => {
		expect(missReason(missed([a('miss'), a('no_sources', { source: null, kind: 'tv' })]))).toBe(
			'No online source is switched on for this kind of disc.'
		);
	});
	it('every attempt not_configured', () => {
		expect(missReason(missed([a('not_configured'), a('not_configured', { source: 'omdb' })]))).toBe(
			'No API keys are saved for the sources in your lists.'
		);
	});
	it('a timeout with no miss', () => {
		expect(missReason(missed([a('timeout'), a('error', { source: 'omdb' })]))).toBe(
			'The lookup timed out. Try the search below.'
		);
		expect(
			missReason(
				missed([
					{ source: null, step: 'title', kind: null, outcome: 'timeout', detail: 'lookup took longer than 25 s' }
				])
			)
		).toBe('The lookup timed out. Try the search below.');
	});
	it('otherwise names the last searched title', () => {
		expect(
			missReason(missed([a('miss', { detail: 'MY DISC' }), a('miss', { detail: 'MY DISC 2' }), a('timeout')]))
		).toBe('No source found a close match for "MY DISC 2". Try another source in the search below.');
	});
	it('falls back to the job title when no title attempt carries one', () => {
		expect(missReason(missed([a('miss', { step: 'imdb', detail: 'tt1' })]))).toBe(
			'No source found a close match for "MY_DISC". Try another source in the search below.'
		);
	});
	it('the whole-dispatch timeout entry is not a searched title', () => {
		const attempts = [
			a('miss', { detail: 'HEAT' }),
			{ source: null, step: 'title', kind: null, outcome: 'timeout', detail: 'lookup took longer than 25 s' }
		];
		expect(missReason(missed(attempts))).toBe(
			'No source found a close match for "HEAT". Try another source in the search below.'
		);
	});
});
