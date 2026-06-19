import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import LogsPage from '../+page.svelte';

const JOBS = [
	{ id: 'job_a', drive_id: 'drv_1', disc_type: 'dvd', status: 'failed', title: 'Alpha', year: 2001 },
	{ id: 'job_b', drive_id: 'drv_1', disc_type: 'dvd', status: 'ripped', title: 'Bravo', year: 2002 }
];

vi.mock('$lib/api/jobs', () => ({
	fetchJobs: vi.fn(() => Promise.resolve(JOBS))
}));

describe('Logs job-list page', () => {
	afterEach(() => cleanup());

	it('renders the page heading', async () => {
		renderComponent(LogsPage);
		expect(screen.getByText('Logs')).toBeInTheDocument();
	});

	it('lists jobs with links to /logs/:job_id', async () => {
		renderComponent(LogsPage);
		await waitFor(() => {
			expect(screen.getByText('Alpha')).toBeInTheDocument();
			expect(screen.getByText('Bravo')).toBeInTheDocument();
		});
		expect(screen.getByText('Alpha').closest('a')).toHaveAttribute('href', '/logs/job_a');
	});

	it('filters by free text over title', async () => {
		renderComponent(LogsPage);
		await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
		const search = screen.getByPlaceholderText(/search/i);
		await fireEvent.input(search, { target: { value: 'brav' } });
		await waitFor(() => {
			expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
			expect(screen.getByText('Bravo')).toBeInTheDocument();
		});
	});

	it('filters by status', async () => {
		renderComponent(LogsPage);
		await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
		// JobFilterBar renders a <select> of statuses; pick "failed"
		const select = screen.getByRole('combobox');
		await fireEvent.change(select, { target: { value: 'failed' } });
		await waitFor(() => {
			expect(screen.getByText('Alpha')).toBeInTheDocument(); // Alpha is failed
			expect(screen.queryByText('Bravo')).not.toBeInTheDocument(); // Bravo is ripped
		});
	});

	it('shows the empty state when there are no jobs', async () => {
		const { fetchJobs } = await import('$lib/api/jobs');
		vi.mocked(fetchJobs).mockResolvedValueOnce([]);
		renderComponent(LogsPage);
		await waitFor(() => expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument());
	});
});
