import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import JobActions from './JobActions.svelte';
import { createJob } from './__fixtures__/job';

// Mock the API module. Fix-permissions has no v3 backend, so the component
// renders no control for it.
vi.mock('$lib/api/jobs', () => ({
	abandonJob: vi.fn(() => Promise.resolve()),
	deleteJob: vi.fn(() => Promise.resolve()),
	ripAgain: vi.fn(() => Promise.resolve({ started_job_id: null, armed: true }))
}));

import { abandonJob, deleteJob, ripAgain } from '$lib/api/jobs';
const mockAbandon = vi.mocked(abandonJob);
const mockDelete = vi.mocked(deleteJob);
const mockRipAgain = vi.mocked(ripAgain);

// Mock window.confirm
vi.stubGlobal(
	'confirm',
	vi.fn(() => true)
);

describe('JobActions', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
		vi.mocked(confirm).mockReturnValue(true);
	});

	describe('rip again (D-132)', () => {
		it('is offered for a ripped job only', () => {
			renderComponent(JobActions, { props: { job: createJob({ status: 'ripped_partial' }) } });
			expect(screen.getByRole('button', { name: 'Rip again' })).toBeInTheDocument();
			cleanup();
			renderComponent(JobActions, { props: { job: createJob({ status: 'failed' }) } });
			expect(screen.queryByRole('button', { name: 'Rip again' })).toBeNull();
		});

		it('says the next insert rips it when nothing is held', async () => {
			const onaction = vi.fn();
			renderComponent(JobActions, { props: { job: createJob({ id: 'job_old', status: 'ripped' }), onaction } });
			await fireEvent.click(screen.getByRole('button', { name: 'Rip again' }));
			expect(mockRipAgain).toHaveBeenCalledWith('job_old');
			await waitFor(() =>
				expect(screen.getByText('The next time this disc goes in, ARM rips it again')).toBeInTheDocument()
			);
			expect(onaction).toHaveBeenCalled();
		});

		it('says it started the held copy when there was one', async () => {
			mockRipAgain.mockResolvedValueOnce({ started_job_id: 'job_new', armed: false });
			renderComponent(JobActions, { props: { job: createJob({ status: 'ripped' }) } });
			await fireEvent.click(screen.getByRole('button', { name: 'Rip again' }));
			await waitFor(() =>
				expect(screen.getByText('Started ripping the copy waiting in the drive')).toBeInTheDocument()
			);
		});
	});

	describe('rendering', () => {
		it('shows Abandon button for active jobs', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripping' }) }
			});
			expect(screen.getByText('Abandon')).toBeInTheDocument();
		});

		it('offers Abandon on a held review disc', () => {
			renderComponent(JobActions, { props: { job: createJob({ status: 'awaiting_review' }) } });
			expect(screen.getByRole('button', { name: /Abandon/ })).toBeInTheDocument();
		});

		it('shows Delete button for completed jobs', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripped' }) }
			});
			expect(screen.getByText('Delete')).toBeInTheDocument();
		});

		it('shows Delete button for failed jobs', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'failed' }) }
			});
			expect(screen.getByText('Delete')).toBeInTheDocument();
		});

		it('never shows a Fix Permissions control (removed)', () => {
			const statuses = ['ripped', 'ripped_partial', 'failed', 'abandoned'] as const;
			for (const status of statuses) {
				cleanup();
				renderComponent(JobActions, { props: { job: createJob({ status }) } });
				expect(screen.queryByText('Fix Permissions')).not.toBeInTheDocument();
			}
		});

		it('shows Abandon for in-flight jobs', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'identified' }) }
			});
			// identified is non-terminal/active, so Abandon should show.
			expect(screen.getByText('Abandon')).toBeInTheDocument();
		});

		it('shows only Delete for abandoned status', () => {
			// abandoned is terminal: Delete is available but no Abandon / Fix Perms.
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'abandoned' }) }
			});
			expect(screen.getByText('Delete')).toBeInTheDocument();
			expect(screen.queryByText('Abandon')).not.toBeInTheDocument();
			expect(screen.queryByText('Fix Permissions')).not.toBeInTheDocument();
		});
	});

	describe('interactions', () => {
		it('calls abandonJob when Abandon is clicked and confirmed', async () => {
			const onaction = vi.fn();
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripping' }), onaction }
			});
			await fireEvent.click(screen.getByText('Abandon'));
			await waitFor(() => {
				expect(mockAbandon).toHaveBeenCalledWith('job_1');
				expect(onaction).toHaveBeenCalled();
			});
		});

		it('calls deleteJob when Delete is clicked and confirmed', async () => {
			const onaction = vi.fn();
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripped' }), onaction }
			});
			await fireEvent.click(screen.getByText('Delete'));
			await waitFor(() => {
				expect(mockDelete).toHaveBeenCalledWith('job_1');
			});
		});

		it('shows success feedback after action', async () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripping' }) }
			});
			await fireEvent.click(screen.getByText('Abandon'));
			await waitFor(() => {
				expect(screen.getByText('Job abandoned')).toBeInTheDocument();
			});
		});

		it('shows error feedback on API failure', async () => {
			mockAbandon.mockRejectedValueOnce(new Error('Server error'));
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripping' }) }
			});
			await fireEvent.click(screen.getByText('Abandon'));
			await waitFor(() => {
				expect(screen.getByText('Server error')).toBeInTheDocument();
			});
		});

		it('does not call API when confirm is cancelled', async () => {
			vi.mocked(confirm).mockReturnValueOnce(false);
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripping' }) }
			});
			await fireEvent.click(screen.getByText('Abandon'));
			expect(mockAbandon).not.toHaveBeenCalled();
		});

		it('shows Delete button for ripped_partial status', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripped_partial' }) }
			});
			expect(screen.getByText('Delete')).toBeInTheDocument();
		});

		it('calls ondelete callback instead of onaction when deleting', async () => {
			const ondelete = vi.fn();
			const onaction = vi.fn();
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripped' }), ondelete, onaction }
			});
			await fireEvent.click(screen.getByText('Delete'));
			await waitFor(() => {
				expect(ondelete).toHaveBeenCalled();
				expect(onaction).not.toHaveBeenCalled();
			});
		});
	});

	describe('props', () => {
		it('renders compact buttons when compact is true', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripped' }), compact: true }
			});
			const deleteBtn = screen.getByText('Delete');
			expect(deleteBtn).toHaveClass('job-actions-pill', 'job-actions-pill-danger');
			expect(deleteBtn).toHaveAttribute('data-compact', 'true');
		});

		it('renders standard buttons when compact is false', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripped' }), compact: false }
			});
			const deleteBtn = screen.getByText('Delete');
			expect(deleteBtn).toHaveClass('job-actions-pill', 'job-actions-pill-danger');
			expect(deleteBtn).toHaveAttribute('data-compact', 'false');
		});
	});
});
