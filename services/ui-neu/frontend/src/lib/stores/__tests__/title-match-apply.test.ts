import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { JobView, MetadataCandidate, ResolveResponse } from '$lib/types/api.gen';
import type { TitleApplyValues } from '$lib/jobs/resolve';
import { titleMatchBody } from '$lib/jobs/resolve';

vi.mock('$lib/api/jobs', () => ({
	resolveJob: vi.fn(),
	updateJobTitle: vi.fn()
}));

import { resolveJob, updateJobTitle } from '$lib/api/jobs';
import { TitleMatchApply, type TitleApplyPlan } from '../title-match-apply.svelte';

const RESPONSE = { id: 'r1' } as unknown as ResolveResponse;
const AT = { row: 2, list: 5 };

const job = (over: { id?: string; can_resolve?: boolean; poster?: string | null } = {}) =>
	({
		id: over.id ?? 'j1',
		poster_url_manual: over.poster,
		actions: { can_resolve: over.can_resolve ?? true }
	}) as unknown as JobView;

const movie = (over: Partial<MetadataCandidate> = {}) =>
	({
		title: 'Dune',
		kind: 'movie',
		provider: 'tmdb',
		external_ids: { tmdb: '1' },
		...over
	}) as unknown as MetadataCandidate;

const values = (over: Partial<TitleApplyValues> = {}): TitleApplyValues => ({
	title: 'Dune',
	year: '2021',
	isSeries: false,
	poster: 'http://p/new.jpg',
	...over
});

function plan(over: Partial<TitleApplyPlan> = {}): TitleApplyPlan {
	return {
		job: () => job(),
		candidate: movie(),
		values: values(),
		posterIsManual: false,
		at: AT,
		...over
	};
}

describe('TitleMatchApply', () => {
	beforeEach(() => {
		vi.mocked(resolveJob).mockReset().mockResolvedValue(RESPONSE);
		vi.mocked(updateJobTitle)
			.mockReset()
			.mockResolvedValue({} as JobView);
	});

	it('starts idle with no feedback', () => {
		const a = new TitleMatchApply();
		expect(a.applying).toBe(false);
		expect(a.feedback).toBeNull();
	});

	it('refuses an empty title with feedback tagged with where it started', async () => {
		const a = new TitleMatchApply();
		const done = vi.fn();
		await a.apply(plan({ values: values({ title: '' }) }), done);
		expect(a.feedback).toEqual({ type: 'error', message: 'Title is required', ...AT });
		expect(a.applying).toBe(false);
		expect(resolveJob).not.toHaveBeenCalled();
		expect(updateJobTitle).not.toHaveBeenCalled();
		expect(done).not.toHaveBeenCalled();
	});

	it('is applying while pending and not after success', async () => {
		const a = new TitleMatchApply();
		let release!: (r: ResolveResponse) => void;
		vi.mocked(resolveJob).mockReturnValue(new Promise((r) => (release = r)));
		const pending = a.apply(plan(), vi.fn());
		expect(a.applying).toBe(true);
		release(RESPONSE);
		await pending;
		expect(a.applying).toBe(false);
	});

	it('is not applying after a failure', async () => {
		const a = new TitleMatchApply();
		vi.mocked(resolveJob).mockRejectedValue(new Error('x'));
		await a.apply(plan(), vi.fn());
		expect(a.applying).toBe(false);
	});

	it('clears the previous feedback when an apply starts', async () => {
		const a = new TitleMatchApply();
		a.feedback = { type: 'error', message: 'old', row: 0, list: 0 };
		let release!: (r: ResolveResponse) => void;
		vi.mocked(resolveJob).mockReturnValue(new Promise((r) => (release = r)));
		const pending = a.apply(plan(), vi.fn());
		expect(a.feedback).toBeNull();
		release(RESPONSE);
		await pending;
	});

	it('applies the picked match with its body and calls done with the response', async () => {
		const a = new TitleMatchApply();
		const done = vi.fn();
		const p = plan({ posterIsManual: true });
		await a.apply(p, done);
		expect(resolveJob).toHaveBeenCalledTimes(1);
		expect(resolveJob).toHaveBeenCalledWith('j1', titleMatchBody(p.candidate, p.values, true));
		expect(updateJobTitle).not.toHaveBeenCalled();
		expect(a.feedback).toEqual({ type: 'success', message: 'Identified', ...AT });
		expect(done).toHaveBeenCalledWith(RESPONSE);
	});

	it('resolves plainly and saves the poster when the match has no provider', async () => {
		const a = new TitleMatchApply();
		const done = vi.fn();
		await a.apply(plan({ candidate: movie({ provider: undefined }) }), done);
		expect(resolveJob).toHaveBeenCalledWith('j1', expect.not.objectContaining({ match: expect.anything() }));
		expect(updateJobTitle).toHaveBeenCalledWith('j1', { poster_url_manual: 'http://p/new.jpg' });
		expect(a.feedback).toEqual({ type: 'success', message: 'Identified', ...AT });
		expect(done).toHaveBeenCalledWith(RESPONSE);
	});

	it('resolves plainly when the type was changed', async () => {
		const a = new TitleMatchApply();
		await a.apply(plan({ values: values({ isSeries: true }) }), vi.fn());
		expect(resolveJob).toHaveBeenCalledWith('j1', expect.not.objectContaining({ match: expect.anything() }));
		expect(updateJobTitle).toHaveBeenCalledTimes(1);
	});

	it('does not save the poster when it equals the job manual poster', async () => {
		const a = new TitleMatchApply();
		await a.apply(
			plan({ candidate: movie({ provider: undefined }), job: () => job({ poster: 'http://p/new.jpg' }) }),
			vi.fn()
		);
		expect(updateJobTitle).not.toHaveBeenCalled();
		expect(a.feedback?.message).toBe('Identified');
	});

	it('counts a missing manual poster as null when comparing', async () => {
		const a = new TitleMatchApply();
		await a.apply(plan({ candidate: movie({ provider: undefined }), values: values({ poster: null }) }), vi.fn());
		expect(updateJobTitle).not.toHaveBeenCalled();
	});

	it('says the poster was not saved when that save fails', async () => {
		const a = new TitleMatchApply();
		const done = vi.fn();
		vi.mocked(updateJobTitle).mockRejectedValue(new Error('nope'));
		await a.apply(plan({ candidate: movie({ provider: undefined }) }), done);
		expect(a.feedback).toEqual({ type: 'success', message: 'Identified; poster not saved', ...AT });
		expect(done).toHaveBeenCalledWith(RESPONSE);
	});

	it('reads the job again after the resolve for the poster save', async () => {
		const a = new TitleMatchApply();
		let current = job({ id: 'old', poster: null });
		vi.mocked(resolveJob).mockImplementation(async () => {
			current = job({ id: 'new', poster: 'http://p/new.jpg' });
			return RESPONSE;
		});
		await a.apply(plan({ candidate: movie({ provider: undefined }), job: () => current }), vi.fn());
		expect(resolveJob).toHaveBeenCalledWith('old', expect.anything());
		// The new job's manual poster equals the values' poster: no save.
		expect(updateJobTitle).not.toHaveBeenCalled();

		current = job({ id: 'old', poster: null });
		vi.mocked(resolveJob).mockImplementation(async () => {
			current = job({ id: 'new', poster: 'http://p/other.jpg' });
			return RESPONSE;
		});
		await a.apply(plan({ candidate: movie({ provider: undefined }), job: () => current }), vi.fn());
		expect(updateJobTitle).toHaveBeenCalledWith('new', { poster_url_manual: 'http://p/new.jpg' });
	});

	it('saves only the poster when the job cannot be resolved', async () => {
		const a = new TitleMatchApply();
		const done = vi.fn();
		await a.apply(plan({ job: () => job({ can_resolve: false }) }), done);
		expect(resolveJob).not.toHaveBeenCalled();
		expect(updateJobTitle).toHaveBeenCalledWith('j1', { poster_url_manual: 'http://p/new.jpg' });
		expect(a.feedback).toEqual({ type: 'success', message: 'Poster updated', ...AT });
		expect(done).toHaveBeenCalledWith(undefined);
	});

	it('shows the error message of a failed apply and does not call done', async () => {
		const a = new TitleMatchApply();
		const done = vi.fn();
		vi.mocked(resolveJob).mockRejectedValue(new Error('boom'));
		await a.apply(plan(), done);
		expect(a.feedback).toEqual({ type: 'error', message: 'boom', ...AT });
		expect(done).not.toHaveBeenCalled();
	});

	it('says "Apply failed" for a failure that is not an Error', async () => {
		const a = new TitleMatchApply();
		vi.mocked(resolveJob).mockRejectedValue('bad');
		await a.apply(plan(), vi.fn());
		expect(a.feedback).toEqual({ type: 'error', message: 'Apply failed', ...AT });
	});

	it('shows the message of a done that throws as the error line', async () => {
		const a = new TitleMatchApply();
		await a.apply(plan(), () => {
			throw new Error('callback broke');
		});
		expect(a.feedback).toEqual({ type: 'error', message: 'callback broke', ...AT });
		expect(a.applying).toBe(false);
	});
});
