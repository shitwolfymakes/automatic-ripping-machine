import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';
import AllJobsPanel from '../AllJobsPanel.svelte';
import { DashboardJobs } from '$lib/stores/dashboard-jobs.svelte';
import { createJob } from '$lib/__fixtures__/job';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper, not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

// jsdom cannot run Web Animations, so an outro would keep the selection bar
// mounted forever; a transition with no duration finishes synchronously.
vi.mock('svelte/transition', () => ({
	fade: () => ({ duration: 0 }),
	slide: () => ({ duration: 0 })
}));

vi.mock('$lib/api/jobs', () => ({
	fetchJobsPage: vi.fn(),
	bulkDeleteJobs: vi.fn()
}));

const JOB = createJob({ id: 'job_2', title: 'Old Movie', status: 'ripped' });

async function mocks() {
	const api = await import('$lib/api/jobs');
	return {
		fetchJobsPage: api.fetchJobsPage as ReturnType<typeof vi.fn>,
		bulkDeleteJobs: api.bulkDeleteJobs as ReturnType<typeof vi.fn>
	};
}

async function setRole(r: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
	auth.__setRole(r);
}

async function renderPanel(jobs: JobView[] = [JOB], total = jobs.length) {
	const m = await mocks();
	m.fetchJobsPage.mockResolvedValue({ jobs, total });
	const list = new DashboardJobs();
	renderComponent(AllJobsPanel, { jobs: list });
	return { list, ...m };
}

type JobView = ReturnType<typeof createJob>;

async function renderLoaded(jobs: JobView[] = [JOB], total = jobs.length) {
	const r = await renderPanel(jobs, total);
	await r.list.load();
	await waitFor(() => expect(screen.getByText('Old Movie')).toBeInTheDocument());
	return r;
}

describe('AllJobsPanel', () => {
	beforeEach(async () => {
		await setRole('admin');
		const { setUiPref } = await import('$lib/stores/ui-prefs');
		setUiPref('dashboardView', 'card');
	});

	afterEach(() => {
		cleanup();
		vi.restoreAllMocks();
		vi.clearAllMocks();
	});

	it('shows the job count, singular and plural', async () => {
		const { list } = await renderLoaded();
		expect(screen.getByText('1 job')).toBeInTheDocument();
		list.total = 3;
		await waitFor(() => expect(screen.getByText('3 jobs')).toBeInTheDocument());
	});

	it('shows skeleton cards while loading, then the cards', async () => {
		const { fetchJobsPage } = await mocks();
		fetchJobsPage.mockReturnValue(new Promise(() => {}));
		const list = new DashboardJobs();
		const { container } = renderComponent(AllJobsPanel, { jobs: list });
		expect(container.querySelector('.dashboard-jobs-grid')).not.toBeNull();
		expect(container.querySelector('table')).toBeNull();
	});

	it('shows a skeleton table while loading in table view', async () => {
		const { fetchJobsPage } = await mocks();
		fetchJobsPage.mockReturnValue(new Promise(() => {}));
		const list = new DashboardJobs();
		const { container } = renderComponent(AllJobsPanel, { jobs: list });
		await fireEvent.click(screen.getByText('Table'));
		expect(container.querySelectorAll('tbody tr')).toHaveLength(12);
		// no admin checkbox in the skeleton header
		expect(container.querySelector('thead input[type="checkbox"]')).toBeNull();
	});

	it('opens in table view when the Settings default says so', async () => {
		const { setUiPref } = await import('$lib/stores/ui-prefs');
		setUiPref('dashboardView', 'table');
		await renderLoaded();
		expect(screen.getByText('Table')).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByRole('table')).toBeInTheDocument();
	});

	it('toggles between cards and table without touching the saved default', async () => {
		const { uiPrefs } = await import('$lib/stores/ui-prefs');
		const { get } = await import('svelte/store');
		await renderLoaded();
		expect(screen.getByText('Cards')).toHaveAttribute('aria-pressed', 'true');
		expect(screen.queryByRole('table')).toBeNull();
		await fireEvent.click(screen.getByText('Table'));
		expect(screen.getByRole('table')).toBeInTheDocument();
		expect(screen.getByText('Table')).toHaveAttribute('aria-pressed', 'true');
		await fireEvent.click(screen.getByText('Cards'));
		expect(screen.queryByRole('table')).toBeNull();
		expect(get(uiPrefs).dashboardView).toBe('card');
	});

	it('shows the empty message when there are no jobs', async () => {
		const { list } = await renderPanel([], 0);
		await list.load();
		await waitFor(() => expect(screen.getByText('No jobs found.')).toBeInTheDocument());
	});

	it('select-all in the table header selects and deselects every row', async () => {
		const { list } = await renderLoaded();
		await fireEvent.click(screen.getByText('Table'));
		const [all] = screen.getAllByRole('checkbox');
		await fireEvent.click(all);
		expect([...list.selected]).toEqual(['job_2']);
		await fireEvent.click(screen.getAllByRole('checkbox')[0]);
		expect(list.selected.size).toBe(0);
	});

	it('opens the selection bar while jobs are checked and clears it again', async () => {
		await renderLoaded();
		await fireEvent.click(screen.getByText('Table'));
		expect(screen.queryByTestId('jobs-selection-bar')).toBeNull();
		await fireEvent.click(screen.getAllByRole('checkbox')[1]);
		expect(await screen.findByTestId('jobs-selection-bar')).toHaveTextContent('1 selected');
		await fireEvent.click(screen.getByText('Clear selection'));
		await waitFor(() => expect(screen.queryByTestId('jobs-selection-bar')).toBeNull());
	});

	it('hides the bulk menu, checkboxes and selection bar from guests', async () => {
		await setRole('guest');
		const { list } = await renderLoaded();
		await fireEvent.click(screen.getByText('Table'));
		list.selected.add('job_2');
		expect(screen.queryByText(/Actions/)).toBeNull();
		expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
		expect(screen.queryByTestId('jobs-selection-bar')).toBeNull();
	});

	it('Delete selected bulk-deletes the selection, reports it and reloads', async () => {
		vi.spyOn(window, 'confirm').mockReturnValue(true);
		const { list, bulkDeleteJobs, fetchJobsPage } = await renderLoaded();
		bulkDeleteJobs.mockResolvedValue({ deleted_ids: ['job_2'], skipped_non_terminal: [] });
		list.selected.add('job_2');
		fetchJobsPage.mockClear();
		await fireEvent.click(await screen.findByText('Delete selected'));
		await waitFor(() => expect(screen.getByText('Deleted 1 job(s)')).toBeInTheDocument());
		expect(window.confirm).toHaveBeenCalledWith('Are you sure you want to delete 1 selected job(s)?');
		expect(bulkDeleteJobs).toHaveBeenCalledWith({ job_ids: ['job_2'] });
		expect(list.selected.size).toBe(0);
		expect(fetchJobsPage).toHaveBeenCalledTimes(1);
		expect(document.querySelector('.dashboard-jobs-feedback')).toHaveAttribute('data-tone', 'success');
	});

	it('does nothing when the confirmation is declined', async () => {
		vi.spyOn(window, 'confirm').mockReturnValue(false);
		const { list, bulkDeleteJobs } = await renderLoaded();
		list.selected.add('job_2');
		await fireEvent.click(await screen.findByText('Delete selected'));
		expect(bulkDeleteJobs).not.toHaveBeenCalled();
		expect(document.querySelector('.dashboard-jobs-feedback')).toBeNull();
		expect(list.selected.size).toBe(1);
	});

	it('the Actions menu bulk-deletes by status', async () => {
		vi.spyOn(window, 'confirm').mockReturnValue(true);
		const { bulkDeleteJobs } = await renderLoaded();
		bulkDeleteJobs.mockResolvedValue({ deleted_ids: ['a'], skipped_non_terminal: ['b'] });
		await fireEvent.click(screen.getByText(/Actions/));
		await fireEvent.click(await screen.findByText('Delete All Failed'));
		await waitFor(() => expect(bulkDeleteJobs).toHaveBeenCalledWith({ status: 'failed' }));
		await waitFor(() => expect(screen.getByText('Deleted 1, skipped 1 in-flight job(s)')).toBeInTheDocument());
		expect(document.querySelector('.dashboard-jobs-feedback')).toHaveAttribute('data-tone', 'error');
	});

	it('shows the error message when the bulk delete fails, and Dismiss closes it', async () => {
		vi.spyOn(window, 'confirm').mockReturnValue(true);
		const { list, bulkDeleteJobs } = await renderLoaded();
		bulkDeleteJobs.mockRejectedValue(new Error('boom'));
		list.selected.add('job_2');
		await fireEvent.click(await screen.findByText('Delete selected'));
		await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument());
		expect(document.querySelector('.dashboard-jobs-feedback')).toHaveAttribute('data-tone', 'error');
		await fireEvent.click(screen.getByLabelText('Dismiss'));
		expect(screen.queryByText('boom')).toBeNull();
	});

	it('falls back to a generic message when a non-Error is thrown', async () => {
		vi.spyOn(window, 'confirm').mockReturnValue(true);
		const { list, bulkDeleteJobs } = await renderLoaded();
		bulkDeleteJobs.mockRejectedValue('nope');
		list.selected.add('job_2');
		await fireEvent.click(await screen.findByText('Delete selected'));
		await waitFor(() => expect(screen.getByText('Bulk action failed')).toBeInTheDocument());
	});

	it('pages and filters through the jobs instance', async () => {
		const { fetchJobsPage } = await renderLoaded([JOB], 100);
		await waitFor(() => expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 1–48 of 100'));
		await fireEvent.click(screen.getByText('2'));
		await waitFor(() => expect(fetchJobsPage).toHaveBeenLastCalledWith({ status: undefined, limit: 48, offset: 48 }));
		await fireEvent.change(screen.getByDisplayValue('All Status'), { target: { value: 'failed' } });
		await waitFor(() => expect(fetchJobsPage).toHaveBeenLastCalledWith({ status: 'failed', limit: 48, offset: 0 }));
	});
});
