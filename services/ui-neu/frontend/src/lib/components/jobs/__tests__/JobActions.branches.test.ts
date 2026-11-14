import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { tick } from 'svelte';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import type { JobStatus, JobView } from '$lib/types/api.gen';
import JobActions from '../JobActions.svelte';
import { createJob } from '../../../__fixtures__/job';

// Behaviour pins for JobActions, beside JobActions.test.ts, written before
// its three handlers share one helper. Every branch is reachable from the
// rendered component, so nothing is left unpinned.

vi.mock('$lib/api/jobs', () => ({
	abandonJob: vi.fn(() => Promise.resolve()),
	deleteJob: vi.fn(() => Promise.resolve()),
	ripAgain: vi.fn(() => Promise.resolve({ started_job_id: null, armed: true }))
}));

import { abandonJob, deleteJob, ripAgain } from '$lib/api/jobs';
const mockAbandon = vi.mocked(abandonJob);
const mockDelete = vi.mocked(deleteJob);
const mockRipAgain = vi.mocked(ripAgain);

vi.stubGlobal(
	'confirm',
	vi.fn(() => true)
);

const ALL_STATUSES: JobStatus[] = [
	'created',
	'awaiting_user_id',
	'identified',
	'ripping',
	'ripped',
	'ripped_partial',
	'awaiting_review',
	'ripped_awaiting_identify',
	'abandoned',
	'failed'
];
const RIP_AGAIN_STATUSES: JobStatus[] = ['ripped', 'ripped_partial', 'ripped_awaiting_identify'];

// A ripped job that offers all three buttons.
function allButtonsJob(overrides: Partial<JobView> = {}): JobView {
	const base = createJob({ status: 'ripped', ...overrides });
	return { ...base, actions: { ...base.actions, can_abandon: true, can_delete: true } };
}

function deferred<T = void>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

// Let pending promise callbacks and Svelte's DOM update run.
async function flush() {
	await vi.advanceTimersByTimeAsync(0);
	await tick();
}

const feedbackEl = () => document.querySelector('.job-actions-feedback');
const btn = (name: string | RegExp) => screen.getByRole('button', { name });
const allButtons = () => screen.getAllByRole('button') as HTMLButtonElement[];

type Case = {
	name: string;
	label: string;
	busy: string;
	click: string;
	api: typeof mockAbandon | typeof mockDelete | typeof mockRipAgain;
	success: string;
	fallback: string;
	confirmText: ((label: string) => string) | null;
};

const CASES: Case[] = [
	{
		name: 'abandon',
		label: 'Abandon',
		busy: 'Abandoning...',
		click: 'Abandon',
		api: mockAbandon,
		success: 'Job abandoned',
		fallback: 'Failed to abandon',
		confirmText: (l) => `Abandon job "${l}"?`
	},
	{
		name: 'rip again',
		label: 'Rip again',
		busy: 'Working...',
		click: 'Rip again',
		api: mockRipAgain,
		success: 'The next time this disc goes in, ARM rips it again',
		fallback: 'Failed to rip again',
		confirmText: null
	},
	{
		name: 'delete',
		label: 'Delete',
		busy: 'Deleting...',
		click: 'Delete',
		api: mockDelete,
		success: 'Job deleted',
		fallback: 'Failed to delete',
		confirmText: (l) => `Delete job "${l}"? This cannot be undone.`
	}
];

describe('JobActions branches', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
		vi.mocked(confirm).mockReturnValue(true);
		mockAbandon.mockImplementation(() => Promise.resolve(createJob()));
		mockDelete.mockImplementation(() => Promise.resolve());
		mockRipAgain.mockImplementation(() => Promise.resolve({ started_job_id: null, armed: true }));
		vi.useRealTimers();
	});

	describe.each(CASES)('$name', (c) => {
		it('asks the confirm text with the job title', async () => {
			renderComponent(JobActions, { props: { job: allButtonsJob({ title: 'Alien' }) } });
			await fireEvent.click(btn(c.click));
			await flush();
			if (c.confirmText) {
				expect(confirm).toHaveBeenCalledTimes(1);
				expect(confirm).toHaveBeenCalledWith(c.confirmText('Alien'));
			} else {
				expect(confirm).not.toHaveBeenCalled();
			}
		});

		it('asks the confirm text with the job id when the job has no title', async () => {
			renderComponent(JobActions, { props: { job: allButtonsJob({ id: 'job_77', title: '' }) } });
			await fireEvent.click(btn(c.click));
			await flush();
			if (c.confirmText) {
				expect(confirm).toHaveBeenCalledWith(c.confirmText('job_77'));
			} else {
				expect(confirm).not.toHaveBeenCalled();
			}
		});

		it('shows its busy label and disables every button while in flight', async () => {
			const pending = deferred<never>();
			c.api.mockImplementationOnce(() => pending.promise as never);
			renderComponent(JobActions, { props: { job: allButtonsJob() } });
			await fireEvent.click(btn(c.click));
			await flush();
			expect(btn(c.busy)).toBeInTheDocument();
			expect(allButtons()).toHaveLength(3);
			expect(allButtons().every((b) => b.disabled)).toBe(true);
			expect(feedbackEl()).toBeNull();
			pending.resolve(undefined as never);
			await flush();
			expect(screen.queryByRole('button', { name: c.busy })).toBeNull();
			expect(allButtons().every((b) => !b.disabled)).toBe(true);
		});

		it('shows a success line and calls onaction once', async () => {
			const onaction = vi.fn();
			renderComponent(JobActions, { props: { job: allButtonsJob(), onaction } });
			await fireEvent.click(btn(c.click));
			await flush();
			expect(feedbackEl()).toHaveTextContent(c.success);
			expect(feedbackEl()).toHaveAttribute('data-tone', 'success');
			expect(onaction).toHaveBeenCalledTimes(1);
			expect(allButtons().every((b) => !b.disabled)).toBe(true);
		});

		it('succeeds without an onaction', async () => {
			renderComponent(JobActions, { props: { job: allButtonsJob() } });
			await fireEvent.click(btn(c.click));
			await flush();
			expect(feedbackEl()).toHaveAttribute('data-tone', 'success');
			expect(feedbackEl()).toHaveTextContent(c.success);
		});

		it("shows the Error's message on failure", async () => {
			const onaction = vi.fn();
			c.api.mockRejectedValueOnce(new Error('boom'));
			renderComponent(JobActions, { props: { job: allButtonsJob(), onaction } });
			await fireEvent.click(btn(c.click));
			await flush();
			expect(feedbackEl()).toHaveTextContent('boom');
			expect(feedbackEl()).toHaveAttribute('data-tone', 'error');
			expect(onaction).not.toHaveBeenCalled();
			expect(screen.queryByRole('button', { name: c.busy })).toBeNull();
			expect(allButtons().every((b) => !b.disabled)).toBe(true);
		});

		it('shows the fallback message when a non-Error is thrown', async () => {
			const onaction = vi.fn();
			c.api.mockRejectedValueOnce('nope');
			renderComponent(JobActions, { props: { job: allButtonsJob(), onaction } });
			await fireEvent.click(btn(c.click));
			await flush();
			expect(feedbackEl()).toHaveTextContent(c.fallback);
			expect(feedbackEl()).toHaveAttribute('data-tone', 'error');
			expect(onaction).not.toHaveBeenCalled();
			expect(allButtons().every((b) => !b.disabled)).toBe(true);
		});

		it('clears a success line 3000 ms after it settles', async () => {
			renderComponent(JobActions, { props: { job: allButtonsJob() } });
			await fireEvent.click(btn(c.click));
			await flush();
			expect(feedbackEl()).not.toBeNull();
			await vi.advanceTimersByTimeAsync(2999);
			await tick();
			expect(feedbackEl()).not.toBeNull();
			await vi.advanceTimersByTimeAsync(1);
			await tick();
			expect(feedbackEl()).toBeNull();
		});

		it('clears an error line 3000 ms after it settles', async () => {
			c.api.mockRejectedValueOnce(new Error('boom'));
			renderComponent(JobActions, { props: { job: allButtonsJob() } });
			await fireEvent.click(btn(c.click));
			await flush();
			expect(feedbackEl()).toHaveTextContent('boom');
			await vi.advanceTimersByTimeAsync(2999);
			await tick();
			expect(feedbackEl()).not.toBeNull();
			await vi.advanceTimersByTimeAsync(1);
			await tick();
			expect(feedbackEl()).toBeNull();
		});

		it('clears an earlier line when it starts', async () => {
			// Put an error line up with a different action, then start this one.
			const other = CASES.find((o) => o.name !== c.name)!;
			other.api.mockRejectedValueOnce(new Error('earlier'));
			const pending = deferred<never>();
			c.api.mockImplementationOnce(() => pending.promise as never);
			renderComponent(JobActions, { props: { job: allButtonsJob() } });
			await fireEvent.click(btn(other.click));
			await flush();
			expect(feedbackEl()).toHaveTextContent('earlier');
			await fireEvent.click(btn(c.click));
			await flush();
			expect(feedbackEl()).toBeNull();
			pending.resolve(undefined as never);
			await flush();
		});
	});

	describe.each(CASES.filter((c) => c.confirmText))('$name declined', (c) => {
		it('sends nothing, keeps its label and shows no feedback', async () => {
			vi.mocked(confirm).mockReturnValue(false);
			renderComponent(JobActions, { props: { job: allButtonsJob() } });
			await fireEvent.click(btn(c.click));
			await flush();
			expect(c.api).not.toHaveBeenCalled();
			expect(btn(c.label)).toBeInTheDocument();
			expect(allButtons().every((b) => !b.disabled)).toBe(true);
			expect(feedbackEl()).toBeNull();
		});
	});

	describe('rip again', () => {
		it('says it started the held copy when started_job_id is set', async () => {
			mockRipAgain.mockResolvedValueOnce({ started_job_id: 'job_new', armed: false });
			const onaction = vi.fn();
			renderComponent(JobActions, { props: { job: allButtonsJob(), onaction } });
			await fireEvent.click(btn('Rip again'));
			await flush();
			expect(feedbackEl()).toHaveTextContent('Started ripping the copy waiting in the drive');
			expect(feedbackEl()).toHaveAttribute('data-tone', 'success');
			expect(onaction).toHaveBeenCalledTimes(1);
		});
	});

	describe('delete with ondelete', () => {
		it('calls ondelete only, shows no line and clears the busy label', async () => {
			const ondelete = vi.fn();
			const onaction = vi.fn();
			const pending = deferred();
			mockDelete.mockImplementationOnce(() => pending.promise);
			renderComponent(JobActions, { props: { job: allButtonsJob(), ondelete, onaction } });
			await fireEvent.click(btn('Delete'));
			await flush();
			expect(btn('Deleting...')).toBeInTheDocument();
			pending.resolve();
			await flush();
			expect(ondelete).toHaveBeenCalledTimes(1);
			expect(onaction).not.toHaveBeenCalled();
			expect(feedbackEl()).toBeNull();
			expect(btn('Delete')).toBeInTheDocument();
			expect(allButtons().every((b) => !b.disabled)).toBe(true);
		});

		it("shows the Error's message when ondelete throws", async () => {
			const onaction = vi.fn();
			const ondelete = vi.fn(() => {
				throw new Error('ondelete failed');
			});
			renderComponent(JobActions, { props: { job: allButtonsJob(), ondelete, onaction } });
			await fireEvent.click(btn('Delete'));
			await flush();
			expect(feedbackEl()).toHaveTextContent('ondelete failed');
			expect(feedbackEl()).toHaveAttribute('data-tone', 'error');
			expect(onaction).not.toHaveBeenCalled();
			expect(allButtons().every((b) => !b.disabled)).toBe(true);
		});
	});

	describe('shared clear timer', () => {
		it("lets an earlier action's timer clear a later action's line", async () => {
			mockAbandon.mockRejectedValueOnce(new Error('first failed'));
			renderComponent(JobActions, { props: { job: allButtonsJob() } });
			await fireEvent.click(btn('Abandon'));
			await flush();
			expect(feedbackEl()).toHaveTextContent('first failed');

			await vi.advanceTimersByTimeAsync(2000);
			await fireEvent.click(btn('Rip again'));
			await flush();
			expect(feedbackEl()).toHaveTextContent('The next time this disc goes in, ARM rips it again');

			await vi.advanceTimersByTimeAsync(999);
			await tick();
			expect(feedbackEl()).not.toBeNull();
			await vi.advanceTimersByTimeAsync(1);
			await tick();
			expect(feedbackEl()).toBeNull();
		});
	});

	describe('gating', () => {
		it.each(ALL_STATUSES)('offers Rip again for %s only when it is a ripped status', (status) => {
			renderComponent(JobActions, { props: { job: createJob({ status }) } });
			const shown = screen.queryByRole('button', { name: 'Rip again' }) !== null;
			expect(shown).toBe(RIP_AGAIN_STATUSES.includes(status));
		});

		it('renders nothing when no action is offered', () => {
			const base = createJob({ status: 'ripping' });
			const job = {
				...base,
				actions: { ...base.actions, can_abandon: false, can_delete: false }
			};
			const { container } = renderComponent(JobActions, { props: { job } });
			expect(screen.queryAllByRole('button')).toHaveLength(0);
			expect(container.querySelector('.job-actions-row')).toBeNull();
		});

		it('sets data-compact on every button', () => {
			renderComponent(JobActions, { props: { job: allButtonsJob(), compact: true } });
			const buttons = allButtons();
			expect(buttons).toHaveLength(3);
			for (const b of buttons) expect(b).toHaveAttribute('data-compact', 'true');
		});
	});
});
