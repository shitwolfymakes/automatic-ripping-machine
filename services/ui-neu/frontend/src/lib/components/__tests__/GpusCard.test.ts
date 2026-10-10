import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/svelte';
import { readable } from 'svelte/store';

const mockFetchGpus = vi.fn();
const mockUpdateGpu = vi.fn();
const mockDeleteGpu = vi.fn();
vi.mock('$lib/api/gpus', () => ({
	fetchGpus: (...a: unknown[]) => mockFetchGpus(...a),
	updateGpu: (...a: unknown[]) => mockUpdateGpu(...a),
	deleteGpu: (...a: unknown[]) => mockDeleteGpu(...a)
}));
vi.mock('$lib/stores/auth', () => ({ isAdmin: readable(true) }));

import GpusCard from '../settings/GpusCard.svelte';

const qsv = {
	id: 'gpu_1',
	vendor: 'qsv',
	device_path: '/dev/dri/renderD128',
	encoder_kinds: ['h264', 'h265'],
	status: 'available',
	enabled: true,
	claimed_by_task_id: null,
	last_seen_at: null
};

beforeEach(() => {
	mockFetchGpus.mockReset();
	mockUpdateGpu.mockReset();
	mockDeleteGpu.mockReset();
});
afterEach(() => cleanup());

describe('GpusCard', () => {
	it('renders inventory rows with vendor, device and encoder kinds', async () => {
		mockFetchGpus.mockResolvedValue([qsv, { ...qsv, id: 'gpu_2', vendor: 'vaapi', enabled: false }]);
		render(GpusCard);
		await waitFor(() => expect(screen.getByText('QSV')).toBeInTheDocument());
		expect(screen.getByText('VAAPI')).toBeInTheDocument();
		expect(screen.getAllByText('/dev/dri/renderD128')).toHaveLength(2);
		expect(screen.getAllByText('h265')).toHaveLength(2);
		expect(screen.getByText('disabled')).toBeInTheDocument();
	});

	it('shows the empty state with the reseed explanation', async () => {
		mockFetchGpus.mockResolvedValue([]);
		render(GpusCard);
		await waitFor(() => expect(screen.getByTestId('gpus-empty')).toBeInTheDocument());
		expect(screen.getByTestId('gpus-empty').textContent).toContain('CPU');
	});

	it('toggling calls updateGpu and applies the response', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockUpdateGpu.mockResolvedValue({ ...qsv, enabled: false });
		render(GpusCard);
		await waitFor(() => expect(screen.getByRole('switch')).toBeInTheDocument());
		await fireEvent.click(screen.getByRole('switch'));
		await waitFor(() => expect(mockUpdateGpu).toHaveBeenCalledWith('gpu_1', false));
		await waitFor(() => expect(screen.getByText('disabled')).toBeInTheDocument());
	});

	it('delete asks for confirmation, then removes the row', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockDeleteGpu.mockResolvedValue(undefined);
		render(GpusCard);
		await waitFor(() => expect(screen.getByLabelText(/Delete qsv/)).toBeInTheDocument());
		await fireEvent.click(screen.getByLabelText(/Delete qsv/));
		// ConfirmDialog appears; confirm.
		const confirm = await screen.findByRole('button', { name: 'Delete' });
		await fireEvent.click(confirm);
		await waitFor(() => expect(mockDeleteGpu).toHaveBeenCalledWith('gpu_1'));
		await waitFor(() => expect(screen.queryByText('QSV')).not.toBeInTheDocument());
	});

	it('a 409 delete shows the in-use message and keeps the row', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockDeleteGpu.mockRejectedValue(new Error('HTTP 409'));
		render(GpusCard);
		await waitFor(() => expect(screen.getByLabelText(/Delete qsv/)).toBeInTheDocument());
		await fireEvent.click(screen.getByLabelText(/Delete qsv/));
		const confirm = await screen.findByRole('button', { name: 'Delete' });
		await fireEvent.click(confirm);
		await waitFor(() =>
			expect(screen.getByRole('alert').textContent).toContain('in use by a running transcode')
		);
		expect(screen.getByText('QSV')).toBeInTheDocument();
	});
});
