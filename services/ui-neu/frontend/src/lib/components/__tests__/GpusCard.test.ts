import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import type { WSEnvelope } from '$lib/api/ws';

const mockFetchGpus = vi.fn();
const mockUpdateGpu = vi.fn();
const mockDeleteGpu = vi.fn();
const mockProbeGpu = vi.fn();
const mockProbeAllGpus = vi.fn();
vi.mock('$lib/api/gpus', () => ({
	fetchGpus: (...a: unknown[]) => mockFetchGpus(...a),
	updateGpu: (...a: unknown[]) => mockUpdateGpu(...a),
	deleteGpu: (...a: unknown[]) => mockDeleteGpu(...a),
	probeGpu: (...a: unknown[]) => mockProbeGpu(...a),
	probeAllGpus: (...a: unknown[]) => mockProbeAllGpus(...a)
}));
vi.mock('$lib/stores/auth', () => ({ isAdmin: readable(true) }));
const mockRefreshEncoders = vi.fn();
vi.mock('$lib/stores/encoders.svelte', () => ({
	encodersStore: { refresh: (...a: unknown[]) => mockRefreshEncoders(...a) }
}));

const subscribeMock = vi.fn();
let wsHandler: ((env: WSEnvelope) => void) | null = null;
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		subscribe: (topic: string, handler: (env: WSEnvelope) => void) => {
			wsHandler = handler;
			return subscribeMock(topic, handler);
		}
	}
}));

import GpusCard from '../settings/GpusCard.svelte';

const qsv = {
	id: 'gpu_1',
	vendor: 'qsv',
	device_path: '/dev/dri/renderD128',
	encoder_kinds: ['h264', 'h265'],
	status: 'available',
	enabled: true,
	claimed_by_task_id: null,
	last_seen_at: null,
	probed_at: '2026-09-01T00:00:00Z',
	probe_error: null
};

function probedEvent(gpuId: string): WSEnvelope {
	return {
		op: 'event',
		event_id: 'evt_1',
		event_type: 'gpu.probed',
		emitted_at: '2026-09-26T00:00:00Z',
		topic: 'transcode.events',
		job_id: null,
		track_id: null,
		payload: { gpu_id: gpuId }
	};
}

beforeEach(() => {
	mockFetchGpus.mockReset();
	mockUpdateGpu.mockReset();
	mockDeleteGpu.mockReset();
	mockProbeGpu.mockReset();
	mockProbeAllGpus.mockReset();
	mockRefreshEncoders.mockReset();
	subscribeMock.mockReset();
	subscribeMock.mockImplementation(() => vi.fn());
	wsHandler = null;
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

	it('shows "Never probed" when probed_at is null', async () => {
		mockFetchGpus.mockResolvedValue([{ ...qsv, probed_at: null }]);
		render(GpusCard);
		await waitFor(() => expect(screen.getByText('Never probed')).toBeInTheDocument());
	});

	it('shows "Verified nothing" when probed with an empty encoder_kinds list', async () => {
		mockFetchGpus.mockResolvedValue([{ ...qsv, encoder_kinds: [] }]);
		render(GpusCard);
		await waitFor(() => expect(screen.getByText('Verified nothing')).toBeInTheDocument());
	});

	it('shows the probe_error text when set', async () => {
		mockFetchGpus.mockResolvedValue([{ ...qsv, probe_error: 'vainfo exited 1' }]);
		render(GpusCard);
		await waitFor(() => expect(screen.getByText('vainfo exited 1')).toBeInTheDocument());
	});

	it('toggling calls updateGpu and applies the response', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockUpdateGpu.mockResolvedValue({ ...qsv, enabled: false });
		render(GpusCard);
		await waitFor(() => expect(screen.getByRole('switch')).toBeInTheDocument());
		await fireEvent.click(screen.getByRole('switch'));
		await waitFor(() => expect(mockUpdateGpu).toHaveBeenCalledWith('gpu_1', false));
		await waitFor(() => expect(screen.getByText('disabled')).toBeInTheDocument());
		expect(mockRefreshEncoders).toHaveBeenCalledTimes(1);
	});

	it('a failed toggle does not refresh encoder availability', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockUpdateGpu.mockRejectedValue(new Error('HTTP 500'));
		render(GpusCard);
		await waitFor(() => expect(screen.getByRole('switch')).toBeInTheDocument());
		await fireEvent.click(screen.getByRole('switch'));
		await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
		expect(mockRefreshEncoders).not.toHaveBeenCalled();
	});

	it('the footer says rows come from discovery and encoders from a per-device probe', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		render(GpusCard);
		await waitFor(() =>
			expect(
				screen.getByText(/Rows come from device discovery; each device's encoders are verified by a per-device probe\./)
			).toBeInTheDocument()
		);
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
		expect(mockRefreshEncoders).toHaveBeenCalledTimes(1);
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
		expect(mockRefreshEncoders).not.toHaveBeenCalled();
	});

	it('Re-probe (admin, per row) calls probeGpu', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockProbeGpu.mockResolvedValue(undefined);
		render(GpusCard);
		await waitFor(() => expect(screen.getByLabelText(/Re-probe qsv/)).toBeInTheDocument());
		await fireEvent.click(screen.getByLabelText(/Re-probe qsv/));
		await waitFor(() => expect(mockProbeGpu).toHaveBeenCalledWith('gpu_1'));
	});

	it('Re-probe all calls probeAllGpus', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockProbeAllGpus.mockResolvedValue(undefined);
		render(GpusCard);
		await waitFor(() => expect(screen.getByRole('button', { name: 'Re-probe all' })).toBeInTheDocument());
		await fireEvent.click(screen.getByRole('button', { name: 'Re-probe all' }));
		await waitFor(() => expect(mockProbeAllGpus).toHaveBeenCalled());
	});

	it('a 409 probe response shows its detail', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockProbeGpu.mockRejectedValue(new Error('That device is claimed by a running transcode.'));
		render(GpusCard);
		await waitFor(() => expect(screen.getByLabelText(/Re-probe qsv/)).toBeInTheDocument());
		await fireEvent.click(screen.getByLabelText(/Re-probe qsv/));
		await waitFor(() =>
			expect(screen.getByRole('alert').textContent).toContain('That device is claimed by a running transcode.')
		);
	});

	it('a gpu.probed WS event for a row triggers a refetch', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		render(GpusCard);
		await waitFor(() => expect(screen.getByText('QSV')).toBeInTheDocument());
		expect(mockFetchGpus).toHaveBeenCalledTimes(1);

		mockFetchGpus.mockResolvedValue([{ ...qsv, encoder_kinds: ['h264', 'h265', 'av1'] }]);
		expect(wsHandler).not.toBeNull();
		wsHandler?.(probedEvent('gpu_1'));

		await waitFor(() => expect(mockFetchGpus).toHaveBeenCalledTimes(2));
		// Encoder availability follows gpu.probed in the encoders store.
		expect(mockRefreshEncoders).not.toHaveBeenCalled();
	});

	it('a transcode.events envelope with a different event_type does not trigger a refetch', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		render(GpusCard);
		await waitFor(() => expect(screen.getByText('QSV')).toBeInTheDocument());
		expect(mockFetchGpus).toHaveBeenCalledTimes(1);

		expect(wsHandler).not.toBeNull();
		wsHandler?.({ ...probedEvent('gpu_1'), event_type: 'transcode.progress' });

		expect(mockFetchGpus).toHaveBeenCalledTimes(1);
		expect(mockRefreshEncoders).not.toHaveBeenCalled();
	});

	it('releases the subscription on destroy', async () => {
		const unsub = vi.fn();
		subscribeMock.mockReturnValue(unsub);
		mockFetchGpus.mockResolvedValue([qsv]);
		const { unmount } = render(GpusCard);
		await waitFor(() => expect(subscribeMock).toHaveBeenCalledWith('transcode.events', expect.any(Function)));
		unmount();
		expect(unsub).toHaveBeenCalledTimes(1);
	});
});
