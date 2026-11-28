// The review card of a disc that holds the film more than once: MakeMKV's title read, the versions
// row, and the choice. Fakes the API; the detail the card loads is set per test.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import DiscReviewWidget from '../DiscReviewWidget.svelte';
import { bladeRunnerDetail } from '../../../__fixtures__/version-sets';
import { patchJob, startWaitingJob } from '$lib/api/jobs';
import type { JobDetailView, TitlesReadView } from '$lib/types/api.gen';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return { role: { subscribe: _role.subscribe }, isAdmin: derived(_role, (r) => r === 'admin') };
});

const server = vi.hoisted(() => ({ detail: null as unknown as JobDetailView }));

vi.mock('$lib/api/jobs', () => ({
	fetchJob: vi.fn(() => Promise.resolve(server.detail)),
	fetchNamingPreview: vi.fn(() => Promise.resolve({ items: [] })),
	patchJob: vi.fn(() => Promise.resolve({})),
	resolveJob: vi.fn(() => Promise.resolve({})),
	startWaitingJob: vi.fn(() => Promise.resolve({})),
	updateTrack: vi.fn(() => Promise.resolve({}))
}));
vi.mock('$lib/api/sessions', () => ({ fetchSessions: vi.fn(() => Promise.resolve([])) }));
vi.mock('$lib/api/iso', () => ({ cancelIsoRip: vi.fn() }));

function load(titles: TitlesReadView, over: Partial<JobDetailView['job']> = {}) {
	const detail = bladeRunnerDetail(titles);
	detail.job = { ...detail.job, ...over };
	server.detail = detail;
	return detail.job;
}

function show(job: ReturnType<typeof load>) {
	renderComponent(DiscReviewWidget, { props: { job, paused: false } });
}

beforeEach(() => vi.mocked(patchJob).mockResolvedValue({} as never));
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('DiscReviewWidget, MakeMKV still reading the titles', () => {
	it('says so in the status bar and keeps Start off', async () => {
		show(load({ state: 'pending' }));
		await waitFor(() => expect(screen.getByText('Reading titles with MakeMKV...')).toBeInTheDocument());
		expect(screen.getByRole('button', { name: 'Start rip' })).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Start rip' })).toHaveAttribute(
			'title',
			'Waiting for MakeMKV to read the disc'
		);
		expect(screen.queryByTestId('makemkv-failure')).toBeNull();
	});

	it('turns Start on once the titles are in', async () => {
		show(load({ state: 'ready' }));
		await waitFor(() => expect(screen.getByRole('button', { name: 'Start rip' })).toBeEnabled());
		expect(screen.getByText('Ready: Review & Start')).toBeInTheDocument();
	});
});

describe('DiscReviewWidget, MakeMKV could not read the disc', () => {
	it('keeps the card, shows why in the shared alert, keeps Start off and Cancel on', async () => {
		show(
			load({
				state: 'failed',
				failure: { reason: 'timed_out', detail: 'timed out', output_tail: [] },
				message: 'MakeMKV took too long to read this disc and was stopped.'
			})
		);
		const alert = await screen.findByTestId('makemkv-failure');
		expect(alert).toHaveClass('alert');
		expect(alert).toHaveTextContent('MakeMKV took too long to read this disc and was stopped.');
		expect(alert).toHaveTextContent('Cancel discards this job.');
		expect(screen.getByText('MakeMKV cannot read this disc')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Start rip' })).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
		expect(startWaitingJob).not.toHaveBeenCalled();
	});

	it('falls back to a plain sentence when the backend sent none', async () => {
		show(load({ state: 'failed' }));
		expect(await screen.findByTestId('makemkv-failure')).toHaveTextContent('MakeMKV could not read this disc.');
	});
});

describe('DiscReviewWidget, versions of the film', () => {
	it('shows the Versions row with the job policy and saves a change as a job field', async () => {
		show(load({ state: 'ready' }, { tick_one_version: true }));
		const select = await screen.findByRole('combobox', { name: 'Versions to rip' });
		expect(select).toHaveValue('one');
		await fireEvent.change(select, { target: { value: 'all' } });
		await waitFor(() => expect(patchJob).toHaveBeenCalledWith('job_1', { tick_one_version: false }));
	});

	it('shows the versions as one row and its choice in the Info table', async () => {
		show(load({ state: 'ready' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Info' }));
		const summary = await screen.findByRole('button', { name: /6 versions of the film: keeping #3/ });
		await fireEvent.click(summary);
		expect(screen.getByRole('radio', { name: /Angle 2/ })).toBeInTheDocument();
		expect(screen.getByText('00334.mpls:2')).toBeInTheDocument();
	});
});
