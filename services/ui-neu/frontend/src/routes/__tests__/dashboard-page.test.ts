import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';
import DashboardPage from '../+page.svelte';
import { createJob } from '$lib/components/__fixtures__/job';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

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
			drives_online: 1,
			drive_names: { drv_1: 'Main Drive' },
			notification_count: 2,
			ripping_enabled: true,
			makemkv_key_valid: null,
			makemkv_key_checked_at: null,
			transcoder_online: false,
			transcoder_stats: null,
			active_transcodes: []
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
		const waiting = jobs.filter((j) => {
			const s = j.status?.toLowerCase();
			return s === 'awaiting_user_id' || s === 'ripped_awaiting_identify';
		});
		const scanning = jobs.filter((j) => j.status?.toLowerCase() === 'created');
		const active = jobs.filter((j) => j.status?.toLowerCase() === 'ripping');
		const finishing = jobs.filter((j) => {
			const s = j.status?.toLowerCase();
			return s === 'identified' || s === 'ripped' || s === 'ripped_partial';
		});
		return { scanning, waiting, active, finishing };
	}

	it('created jobs go to scanning, not active', () => {
		const { scanning, active } = groupJobs([
			{ id: 'a', status: 'created' },
			{ id: 'b', status: 'ripping' }
		]);
		expect(scanning.map((j) => j.id)).toEqual(['a']);
		expect(active.map((j) => j.id)).toEqual(['b']);
	});

	it('awaiting_user_id + ripped_awaiting_identify go to waiting', () => {
		const { waiting } = groupJobs([
			{ id: 'a', status: 'awaiting_user_id' },
			{ id: 'b', status: 'ripped_awaiting_identify' },
			{ id: 'c', status: 'ripping' }
		]);
		expect(waiting.map((j) => j.id).sort()).toEqual(['a', 'b']);
	});

	it('ripping is the only ACTIVE-RIPS status', () => {
		const { active } = groupJobs([
			{ id: 'a', status: 'ripping' },
			{ id: 'b', status: 'ripped' },
			{ id: 'c', status: 'created' }
		]);
		expect(active.map((j) => j.id)).toEqual(['a']);
	});

	it('identified + ripped + ripped_partial go to finishing', () => {
		const { finishing } = groupJobs([
			{ id: 'a', status: 'identified' },
			{ id: 'b', status: 'ripped' },
			{ id: 'c', status: 'ripped_partial' },
			{ id: 'd', status: 'ripping' }
		]);
		expect(finishing.map((j) => j.id).sort()).toEqual(['a', 'b', 'c']);
	});

	it('all 7 non-terminal statuses are partitioned with no gaps/overlaps', () => {
		const jobs = [
			{ id: '1', status: 'created' },
			{ id: '2', status: 'awaiting_user_id' },
			{ id: '3', status: 'identified' },
			{ id: '4', status: 'ripping' },
			{ id: '5', status: 'ripped' },
			{ id: '6', status: 'ripped_partial' },
			{ id: '7', status: 'ripped_awaiting_identify' }
		];
		const { scanning, waiting, active, finishing } = groupJobs(jobs);
		const all = [...scanning, ...waiting, ...active, ...finishing].map((j) => j.id).sort();
		expect(all).toEqual(['1', '2', '3', '4', '5', '6', '7']);
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

		it.each(['Title', 'Year', 'Rip', 'Transcode', 'Type', 'Disc'])(
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

	describe('guest write-control gating', () => {
		afterEach(async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('admin');
		});

		it('hides the bulk actions menu and selection checkboxes for guests', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('guest');
			await renderDashboardTable();
			expect(screen.queryByText(/Actions/)).not.toBeInTheDocument();
			expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
		});

		it('shows the bulk actions menu and selection checkboxes for admins', async () => {
			await renderDashboardTable();
			expect(screen.getByText(/Actions/)).toBeInTheDocument();
			expect(screen.queryAllByRole('checkbox').length).toBeGreaterThan(0);
		});
	});
});
