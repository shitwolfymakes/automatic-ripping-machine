import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { WSEnvelope } from '$lib/api/ws';
import { ApiError } from '$lib/api/client';

// Branch pins for GpusCard, beside GpusCard.test.ts. One branch cannot be
// reached from the rendered component, so nothing here forces it:
// - The no-target early return in removeConfirmed: the only caller is the
//   delete dialog's confirm button, and that dialog renders only while a
//   delete target is set, so the target is always there when it runs.

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
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await import('svelte/store');
	const _admin = writable(true);
	return {
		isAdmin: { subscribe: _admin.subscribe },
		// Test-only helper, not part of the real module's public API.
		__setAdmin: (v: boolean) => _admin.set(v)
	};
});
const mockRefreshEncoders = vi.fn();
vi.mock('$lib/stores/encoders.svelte', () => ({
	encodersStore: { refresh: (...a: unknown[]) => mockRefreshEncoders(...a) }
}));

const subscribeMock = vi.fn();
let wsHandler: ((env: WSEnvelope) => void) | null = null;
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		start: vi.fn(),
		subscribe: (topic: string, handler: (env: WSEnvelope) => void) => {
			wsHandler = handler;
			return subscribeMock(topic, handler);
		}
	}
}));

import GpusCard from '../GpusCard.svelte';

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
const vaapi = { ...qsv, id: 'gpu_2', vendor: 'vaapi', device_path: '/dev/dri/renderD129' };

function probedEvent(payload: Record<string, unknown>): WSEnvelope {
	return {
		op: 'event',
		event_id: 'evt_1',
		event_type: 'gpu.probed',
		emitted_at: '2026-09-26T00:00:00Z',
		topic: 'transcode.events',
		job_id: null,
		track_id: null,
		payload
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
afterEach(async () => {
	cleanup();
	vi.useRealTimers();
	await setAdmin(true);
});

async function setAdmin(v: boolean) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setAdmin: (v: boolean) => void };
	auth.__setAdmin(v);
}

describe('GpusCard probes', () => {
	it('re-probing a device that is already being probed keeps it in testing', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockProbeGpu.mockResolvedValue(undefined);
		renderComponent(GpusCard);
		const button = await screen.findByLabelText(/Re-probe qsv/);
		await fireEvent.click(button);
		expect(await screen.findByText('Testing encoders...')).toBeInTheDocument();
		await waitFor(() => expect(button).not.toBeDisabled());

		await fireEvent.click(button);
		await waitFor(() => expect(mockProbeGpu).toHaveBeenCalledTimes(2));
		await waitFor(() => expect(button).not.toBeDisabled());
		expect(screen.getByText('Testing encoders...')).toBeInTheDocument();
	});

	it('shows "Couldn\'t test" when a probe has no result after two minutes', async () => {
		vi.useFakeTimers();
		mockFetchGpus.mockResolvedValue([qsv]);
		mockProbeGpu.mockResolvedValue(undefined);
		renderComponent(GpusCard);
		await vi.advanceTimersByTimeAsync(0);
		await fireEvent.click(screen.getByLabelText(/Re-probe qsv/));
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.getByText('Testing encoders...')).toBeInTheDocument();

		await vi.advanceTimersByTimeAsync(120_000);
		expect(screen.queryByText('Testing encoders...')).not.toBeInTheDocument();
		expect(screen.getByText("Couldn't test")).toBeInTheDocument();
	});

	it('a gpu.probed event without a gpu_id still reloads the list', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		renderComponent(GpusCard);
		await screen.findByText('Quick Sync');
		expect(mockFetchGpus).toHaveBeenCalledTimes(1);

		wsHandler?.(probedEvent({}));

		await waitFor(() => expect(mockFetchGpus).toHaveBeenCalledTimes(2));
	});
});

describe('GpusCard failures', () => {
	it('says so when the inventory cannot be loaded', async () => {
		mockFetchGpus.mockRejectedValue(new Error('HTTP 500'));
		renderComponent(GpusCard);
		expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the GPU inventory.');
	});

	it('a re-probe rejected with a non-Error shows the generic message', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockProbeGpu.mockRejectedValue('boom');
		renderComponent(GpusCard);
		await fireEvent.click(await screen.findByLabelText(/Re-probe qsv/));
		expect(await screen.findByRole('alert')).toHaveTextContent('Re-probe failed.');
	});

	it('Test encoders failing with an Error shows its message', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockProbeAllGpus.mockRejectedValue(new Error('Probe queue is full.'));
		renderComponent(GpusCard);
		await fireEvent.click(await screen.findByRole('button', { name: /test encoders/i }));
		expect(await screen.findByRole('alert')).toHaveTextContent('Probe queue is full.');
	});

	it('Test encoders failing with a non-Error shows the generic message', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockProbeAllGpus.mockRejectedValue('boom');
		renderComponent(GpusCard);
		await fireEvent.click(await screen.findByRole('button', { name: /test encoders/i }));
		expect(await screen.findByRole('alert')).toHaveTextContent('Re-probe failed.');
	});

	it('a delete refused for a reason other than 409 shows the generic message', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockDeleteGpu.mockRejectedValue(new ApiError(500, 'server error', {}));
		renderComponent(GpusCard);
		await fireEvent.click(await screen.findByLabelText(/Delete qsv/));
		await fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('Deleting the GPU failed.');
		expect(screen.getByText('Quick Sync')).toBeInTheDocument();
	});

	it('a delete failing with a plain Error shows the generic message', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		mockDeleteGpu.mockRejectedValue(new Error('network down'));
		renderComponent(GpusCard);
		await fireEvent.click(await screen.findByLabelText(/Delete qsv/));
		await fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('Deleting the GPU failed.');
	});
});

describe('GpusCard list', () => {
	it('toggling one GPU of two leaves the other as it was', async () => {
		mockFetchGpus.mockResolvedValue([qsv, vaapi]);
		mockUpdateGpu.mockResolvedValue({ ...qsv, enabled: false });
		renderComponent(GpusCard);
		await fireEvent.click(await screen.findByRole('switch', { name: /Enable qsv/ }));

		await waitFor(() => expect(mockUpdateGpu).toHaveBeenCalledWith('gpu_1', false));
		await waitFor(() =>
			expect(screen.getByRole('switch', { name: /Enable qsv/ })).toHaveAttribute('aria-checked', 'false')
		);
		expect(screen.getByRole('switch', { name: /Enable vaapi/ })).toHaveAttribute('aria-checked', 'true');
	});

	it('a GPU tested with no encoders shows "Nothing verified"', async () => {
		mockFetchGpus.mockResolvedValue([qsv, { ...vaapi, encoder_kinds: [] }]);
		renderComponent(GpusCard);
		expect(await screen.findByText('Nothing verified')).toBeInTheDocument();
		expect(screen.getAllByText('H264 available')).toHaveLength(1);
	});

	it('a non-admin sees the rows without switches or row buttons', async () => {
		await setAdmin(false);
		mockFetchGpus.mockResolvedValue([qsv]);
		renderComponent(GpusCard);
		await screen.findByText('Quick Sync');

		expect(screen.queryByRole('switch')).not.toBeInTheDocument();
		expect(screen.queryByLabelText(/Re-probe qsv/)).not.toBeInTheDocument();
		expect(screen.queryByLabelText(/Delete qsv/)).not.toBeInTheDocument();
	});

	it('cancelling the delete dialog closes it without deleting', async () => {
		mockFetchGpus.mockResolvedValue([qsv]);
		renderComponent(GpusCard);
		await fireEvent.click(await screen.findByLabelText(/Delete qsv/));
		await fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

		await waitFor(() => expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument());
		expect(mockDeleteGpu).not.toHaveBeenCalled();
		expect(screen.getByText('Quick Sync')).toBeInTheDocument();
	});
});
