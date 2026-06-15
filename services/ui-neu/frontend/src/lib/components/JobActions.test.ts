import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import JobActions from './JobActions.svelte';
import { createJob } from './__fixtures__/job';

// Mock the API module. fixJobPermissions is MISSING in v3 (rejects at runtime),
// but the button stays wired so we mock it here to keep the success-path test.
vi.mock('$lib/api/jobs', () => ({
	abandonJob: vi.fn(() => Promise.resolve()),
	deleteJob: vi.fn(() => Promise.resolve()),
	fixJobPermissions: vi.fn(() => Promise.resolve())
}));

import { abandonJob, deleteJob, fixJobPermissions } from '$lib/api/jobs';
const mockAbandon = vi.mocked(abandonJob);
const mockDelete = vi.mocked(deleteJob);
const mockFixPerms = vi.mocked(fixJobPermissions);

// Mock window.confirm
vi.stubGlobal('confirm', vi.fn(() => true));

describe('JobActions', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
		vi.mocked(confirm).mockReturnValue(true);
	});

	describe('rendering', () => {
		it('shows Abandon button for active jobs', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripping' }) }
			});
			expect(screen.getByText('Abandon')).toBeInTheDocument();
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

		it('shows Fix Permissions button only for ripped status', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripped' }) }
			});
			expect(screen.getByText('Fix Permissions')).toBeInTheDocument();
		});

		it('does not show Fix Permissions for failed jobs', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'failed' }) }
			});
			expect(screen.queryByText('Fix Permissions')).not.toBeInTheDocument();
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

		it('calls fixJobPermissions when Fix Permissions is clicked', async () => {
			const onaction = vi.fn();
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripped' }), onaction }
			});
			await fireEvent.click(screen.getByText('Fix Permissions'));
			await waitFor(() => {
				expect(mockFixPerms).toHaveBeenCalledWith('job_1');
				expect(onaction).toHaveBeenCalled();
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
			expect(deleteBtn).toHaveClass('text-xs');
		});

		it('renders standard buttons when compact is false', () => {
			renderComponent(JobActions, {
				props: { job: createJob({ status: 'ripped' }), compact: false }
			});
			const deleteBtn = screen.getByText('Delete');
			expect(deleteBtn).toHaveClass('text-xs');
		});
	});
});
