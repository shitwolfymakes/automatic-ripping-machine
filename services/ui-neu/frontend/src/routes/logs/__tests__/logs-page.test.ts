import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';
import LogsPage from '../+page.svelte';

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();

const JOBS = [
	{
		id: 'job_alpha9A41',
		drive_id: 'drv_1',
		disc_type: 'bluray',
		media_type: 'tv',
		season: 1,
		disc_number: 1,
		disc_total: 4,
		status: 'failed',
		title: 'Alpha',
		year: 2001,
		metadata_json: {}
	},
	{
		id: 'job_b',
		drive_id: 'drv_iso_with_a_long_name',
		disc_type: 'bluray',
		media_type: 'movie',
		status: 'ripped',
		title: 'Bravo',
		year: null,
		metadata_json: {}
	},
	{
		id: 'job_c',
		drive_id: null,
		disc_type: 'dvd',
		status: 'ripped',
		title: null,
		year: 2003,
		metadata_json: {}
	}
];

const INDEX = [
	{ job_id: 'job_b', size_bytes: 10, modified_at: minutesAgo(42) },
	{ job_id: 'job_c', size_bytes: 10, modified_at: 'not a date' },
	{ job_id: 'job_alpha9A41', size_bytes: 10, modified_at: minutesAgo(60 * 24 * 10) }
];

vi.mock('$lib/api/jobs', () => ({
	fetchAllJobs: vi.fn(() => Promise.resolve({ jobs: JOBS, total: JOBS.length }))
}));
// drv_iso_with_a_long_name is a retired virtual drive: the ISO chip must
// still come from it.
vi.mock('$lib/stores/dashboard', async () => {
	const { readable } = await import('svelte/store');
	return {
		dashboard: readable({
			drive_names: {},
			drive_source_kinds: { drv_iso_with_a_long_name: 'iso' }
		})
	};
});

vi.mock('$lib/api/logs', () => ({
	fetchJobLogIndex: vi.fn(() => Promise.resolve(INDEX))
}));

function rows(): HTMLElement[] {
	return screen.getAllByRole('row').slice(1);
}

async function ready() {
	renderComponent(LogsPage);
	await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
}

describe('Logs job-list page', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('renders the panel header with the count, status filter and search', async () => {
		await ready();
		expect(screen.getByRole('heading', { name: 'Job logs' })).toBeInTheDocument();
		expect(screen.getByText('3 jobs')).toBeInTheDocument();
		expect(screen.getByRole('combobox')).toBeInTheDocument();
		const search = screen.getByPlaceholderText('Search title or id');
		expect(search).toHaveAttribute('aria-label', 'Search jobs by title or id');
	});

	it('loads every job, not one page', async () => {
		const { fetchAllJobs } = await import('$lib/api/jobs');
		await ready();
		expect(fetchAllJobs).toHaveBeenCalledWith();
	});

	it('shows the columns in order', async () => {
		await ready();
		const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
		expect(headers).toEqual(['Title', 'Status', 'Type', 'Disc', 'Drive', 'Last modified']);
	});

	it('orders rows by last modified, jobs without a log last', async () => {
		await ready();
		const order = rows().map((r) => within(r).getByRole('link').getAttribute('href'));
		expect(order).toEqual(['/logs/job_b', '/logs/job_alpha9A41', '/logs/job_c']);
	});

	it('renders each column of a row', async () => {
		await ready();
		const [bravo, alpha, nolog] = rows();

		// Title: link + id beneath, title falls back to the id
		expect(within(alpha).getByRole('link', { name: 'Alpha' })).toHaveAttribute('href', '/logs/job_alpha9A41');
		const shortId = within(alpha).getByText('job_9a41');
		expect(shortId).toHaveAttribute('title', 'job_alpha9A41');
		expect(within(nolog).getByRole('link', { name: 'job_c' })).toHaveAttribute('href', '/logs/job_c');

		// Status
		expect(within(alpha).getByText('Failed')).toBeInTheDocument();

		// Type chips
		expect(within(alpha).getByText('Series')).toBeInTheDocument();
		expect(within(alpha).getByText('Blu-ray')).toBeInTheDocument();
		expect(within(bravo).getByText('Movie')).toBeInTheDocument();
		expect(within(bravo).getByText('ISO')).toBeInTheDocument();

		// Disc
		expect(within(alpha).getByText('S1 · Disc 1/4')).toBeInTheDocument();
		expect(bravo.querySelector('[data-label="Disc"]')?.textContent?.trim()).toBe('-');

		// Drive, truncated with a tooltip
		const drive = bravo.querySelector('[data-label="Drive"] [title]');
		expect(drive).toHaveAttribute('title', 'drv_iso_with_a_long_name');
		expect(nolog.querySelector('[data-label="Drive"]')?.textContent?.trim()).toBe('-');

		// No Year column
		expect(alpha.querySelector('[data-label="Year"]')).toBeNull();
		expect(within(alpha).queryByText('2001')).not.toBeInTheDocument();

		// Last modified: relative over absolute
		expect(within(bravo).getByText('42 min ago')).toBeInTheDocument();
		// older than six days: only the absolute date, no relative line
		const alphaWhen = alpha.querySelector('[data-label="Last modified"]')!;
		expect(alphaWhen.textContent).not.toMatch(/ago|Yesterday|Just now/);
		expect(alphaWhen.textContent?.trim()).toMatch(/\d{1,2}:\d{2}/);
		// an unparseable modified_at reads as no log
		expect(within(nolog).getByText('No log yet')).toBeInTheDocument();
		expect(nolog.textContent).not.toMatch(/Invalid Date/);
	});

	it('wraps the table so it scrolls instead of clipping', async () => {
		await ready();
		expect(screen.getByRole('table').parentElement).toHaveClass('overflow-x-auto');
	});

	it('shows the error state when the jobs fail to load', async () => {
		const { fetchAllJobs } = await import('$lib/api/jobs');
		vi.mocked(fetchAllJobs).mockRejectedValueOnce(new Error('jobs down'));
		renderComponent(LogsPage);
		await waitFor(() => expect(screen.getByText(/Failed to load: jobs down/)).toBeInTheDocument());
	});

	it('filters by free text over title and id, showing the shown count', async () => {
		await ready();
		const search = screen.getByPlaceholderText('Search title or id');
		await fireEvent.input(search, { target: { value: 'BRAV' } });
		await waitFor(() => expect(screen.queryByText('Alpha')).not.toBeInTheDocument());
		expect(screen.getByText('Bravo')).toBeInTheDocument();
		expect(screen.getByText('1 of 3 jobs')).toBeInTheDocument();
		await fireEvent.input(search, { target: { value: 'job_c' } });
		await waitFor(() => expect(rows()).toHaveLength(1));
	});

	it('filters by status', async () => {
		await ready();
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'failed' } });
		await waitFor(() => expect(screen.queryByText('Bravo')).not.toBeInTheDocument());
		expect(screen.getByText('Alpha')).toBeInTheDocument();
	});

	it('says no jobs match when the filters exclude everything', async () => {
		await ready();
		await fireEvent.input(screen.getByPlaceholderText('Search title or id'), { target: { value: 'zzz' } });
		await waitFor(() => expect(screen.getByText('No jobs match.')).toBeInTheDocument());
		expect(screen.getByText('0 of 3 jobs')).toBeInTheDocument();
	});

	it('still lists the jobs when the log index fails', async () => {
		const { fetchJobLogIndex } = await import('$lib/api/logs');
		vi.mocked(fetchJobLogIndex).mockRejectedValueOnce(new Error('boom'));
		await ready();
		expect(rows()).toHaveLength(3);
		expect(screen.getAllByText('No log yet')).toHaveLength(3);
	});

	it('uses the singular for one job', async () => {
		const { fetchAllJobs } = await import('$lib/api/jobs');
		vi.mocked(fetchAllJobs).mockResolvedValueOnce({ jobs: [JOBS[0]], total: 1 } as never);
		await ready();
		expect(screen.getByText('1 job')).toBeInTheDocument();
	});

	it('shows the empty state when there are no jobs', async () => {
		const { fetchAllJobs } = await import('$lib/api/jobs');
		vi.mocked(fetchAllJobs).mockResolvedValueOnce({ jobs: [], total: 0 });
		renderComponent(LogsPage);
		await waitFor(() => expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument());
	});
});
