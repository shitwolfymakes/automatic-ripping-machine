import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';
import DashboardPage from '../+page.svelte';
import { createJob } from '$lib/components/__fixtures__/job';

// --- Shared mock job fixtures (v3 JobView shape) ---
const ACTIVE_JOB = createJob({
	id: 'job_1',
	title: 'Ripping Movie',
	status: 'ripping',
	year: 2024,
	disc_type: 'bluray'
});

const COMPLETED_JOB = createJob({
	id: 'job_2',
	title: 'Old Movie',
	status: 'ripped',
	year: 2023,
	disc_type: 'dvd'
});

vi.mock('$lib/api/dashboard', () => ({
	fetchDashboard: vi.fn(() =>
		Promise.resolve({
			db_available: true,
			arm_online: true,
			active_jobs: [ACTIVE_JOB],
			system_info: null,
			drives_online: 1,
			drive_names: { drv_1: 'Main Drive' },
			notification_count: 2,
			ripping_enabled: true,
			makemkv_key_valid: null,
			makemkv_key_checked_at: null,
			transcoder_online: false,
			transcoder_stats: null,
			transcoder_system_stats: null,
			active_transcodes: [],
			system_stats: null,
			transcoder_info: null
		})
	)
}));

vi.mock('$lib/api/jobs', () => ({
	fetchJobs: vi.fn(() => Promise.resolve([COMPLETED_JOB])),
	bulkDeleteJobs: vi.fn(() => Promise.resolve({ deleted_ids: [], skipped_non_terminal: [] })),
	abandonJob: vi.fn(),
	deleteJob: vi.fn()
}));

vi.mock('$lib/api/logs', () => ({
	fetchStructuredLogContent: vi.fn(() => Promise.resolve({ entries: [] }))
}));

/** Render dashboard and wait for initial data to load */
async function renderDashboard() {
	renderComponent(DashboardPage);
	await waitFor(() => expect(screen.getByText('Dashboard')).toBeInTheDocument());
}

/** Render dashboard, wait for jobs, then switch to table view */
async function renderDashboardTable() {
	await renderDashboard();
	await fireEvent.click(screen.getByText('Table'));
	await waitFor(() => expect(screen.getByText('Title')).toBeInTheDocument());
}

describe('Dashboard job grouping logic', () => {
	function groupJobs(jobs: Array<{ status: string | null; id: string }>) {
		const scanning = jobs.filter((j) => j.status?.toLowerCase() === 'identifying');
		const waiting = jobs.filter((j) => j.status?.toLowerCase() === 'waiting');
		const active = jobs.filter((j) => {
			const s = j.status?.toLowerCase();
			return s !== 'waiting' && s !== 'transcoding' && s !== 'waiting_transcode' && s !== 'identifying';
		});
		return { scanning, waiting, active };
	}

	it('identifying jobs go to scanning group, not active', () => {
		const jobs = [
			{ id: 'a', status: 'identifying' },
			{ id: 'b', status: 'ripping' }
		];
		const { scanning, active } = groupJobs(jobs);
		expect(scanning).toHaveLength(1);
		expect(scanning[0].id).toBe('a');
		expect(active).toHaveLength(1);
		expect(active[0].id).toBe('b');
	});

	it('waiting jobs excluded from both scanning and active', () => {
		const jobs = [
			{ id: 'a', status: 'identifying' },
			{ id: 'b', status: 'waiting' },
			{ id: 'c', status: 'ripping' }
		];
		const { scanning, waiting, active } = groupJobs(jobs);
		expect(scanning).toHaveLength(1);
		expect(waiting).toHaveLength(1);
		expect(active).toHaveLength(1);
	});
});

describe('Dashboard Page', () => {
	afterEach(() => cleanup());

	describe('rendering', () => {
		it.each([
			['Dashboard', 'dashboard heading'],
			['Ripping Movie', 'active jobs'],
			['Old Movie', 'completed jobs'],
			['All Jobs', 'All Jobs heading']
		])('renders "%s" (%s)', async (text) => {
			await renderDashboard();
			await waitFor(() => expect(screen.getByText(text)).toBeInTheDocument());
		});
	});

	describe('view mode toggle', () => {
		afterEach(() => cleanup());

		it('renders Cards and Table toggle buttons', async () => {
			await renderDashboard();
			expect(screen.getByText('Cards')).toBeInTheDocument();
			expect(screen.getByText('Table')).toBeInTheDocument();
		});

		it.each(['Title', 'Year', 'Status', 'Type', 'Disc'])(
			'table view shows %s column header',
			async (header) => {
				await renderDashboardTable();
				expect(screen.getByText(header)).toBeInTheDocument();
			}
		);
	});

	it('renders the All Jobs list from the flat fetchJobs array', async () => {
		await renderDashboard();
		await waitFor(() => expect(screen.getByText('Old Movie')).toBeInTheDocument());
	});

	it('shows active rips section when ripping jobs exist', async () => {
		await renderDashboard();
		await waitFor(() => expect(screen.getByText('Ripping Movie')).toBeInTheDocument());
	});

	it('shows no jobs found when job list is empty', async () => {
		const { fetchJobs } = await import('$lib/api/jobs');
		(fetchJobs as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
		renderComponent(DashboardPage);
		await waitFor(() => expect(screen.getByText('No jobs found.')).toBeInTheDocument());
	});

	it('calls fetchJobs (no pagination/search/sort params in v3)', async () => {
		const { fetchJobs } = await import('$lib/api/jobs');
		await renderDashboard();
		await waitFor(() => expect(fetchJobs).toHaveBeenCalled());
		// v3 GET /api/jobs takes only status/drive_id/limit/offset.
		const call = (fetchJobs as ReturnType<typeof vi.fn>).mock.calls[0][0];
		expect(call).not.toHaveProperty('page');
		expect(call).not.toHaveProperty('per_page');
		expect(call).not.toHaveProperty('sort_by');
	});
});
