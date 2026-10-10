import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import DriveMaintenance from './DriveMaintenance.svelte';
vi.mock('$lib/api/drives', () => ({ rescanDrives: vi.fn() }));
import { rescanDrives } from '$lib/api/drives';
const rescanMock = vi.mocked(rescanDrives);
const summary = { online: 1, stale: 0, detected: 2, ignored: 1, enrolled: 1, absent: 1, pruned: 0 };

describe('DriveMaintenance', () => {
	afterEach(() => { cleanup(); vi.clearAllMocks(); });

	it('Rescan calls the API without force, reports the counts, and notifies the parent', async () => {
		rescanMock.mockResolvedValueOnce(summary);
		const onrescanned = vi.fn();
		renderComponent(DriveMaintenance, { props: { onrescanned } });
		await fireEvent.click(screen.getByTestId('drive-rescan'));
		await waitFor(() => expect(screen.getByTestId('drive-rescan-summary')).toHaveTextContent('2 detected · 1 enrolled · 1 ignored'));
		expect(rescanMock).toHaveBeenCalledWith(false);
		expect(onrescanned).toHaveBeenCalledWith(summary);
		expect(screen.queryByText(/removed/)).not.toBeInTheDocument();
	});

	it('Force Rescan opens the confirmation and only prunes after confirm', async () => {
		rescanMock.mockResolvedValueOnce({ ...summary, pruned: 3 });
		renderComponent(DriveMaintenance, { props: { onrescanned: vi.fn() } });
		await fireEvent.click(screen.getByTestId('drive-force-rescan'));
		expect(screen.getByRole('dialog')).toBeInTheDocument();
		expect(screen.getByText('Remove missing drives?')).toBeInTheDocument();
		expect(screen.getByText(/Enrolled and ignored drives are kept/)).toBeInTheDocument();
		expect(rescanMock).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByText('Remove and scan'));
		await waitFor(() => expect(screen.getByTestId('drive-rescan-summary')).toHaveTextContent('3 removed'));
		expect(rescanMock).toHaveBeenCalledWith(true);
		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
	});

	it('Cancel closes the confirmation without calling the API', async () => {
		renderComponent(DriveMaintenance, { props: { onrescanned: vi.fn() } });
		await fireEvent.click(screen.getByTestId('drive-force-rescan'));
		await fireEvent.click(screen.getByText('Cancel'));
		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
		expect(rescanMock).not.toHaveBeenCalled();
	});

	it('shows the backend error', async () => {
		rescanMock.mockRejectedValueOnce(new Error('drive scanner unavailable'));
		renderComponent(DriveMaintenance, { props: { onrescanned: vi.fn() } });
		await fireEvent.click(screen.getByTestId('drive-rescan'));
		await waitFor(() => expect(screen.getByTestId('drive-rescan-error')).toHaveTextContent('drive scanner unavailable'));
	});
});
