import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import type { GpuView } from '$lib/types/api.gen';
import GpuEncoderChips from '../GpuEncoderChips.svelte';

afterEach(cleanup);

const gpu: GpuView = {
	id: 'gpu_1',
	vendor: 'qsv',
	device_path: '/dev/dri/renderD128',
	encoder_kinds: [],
	status: 'available',
	enabled: true,
	claimed_by_task_id: null,
	last_seen_at: null,
	probed_at: null,
	probe_error: null
};

describe('GpuEncoderChips', () => {
	it('shows only "Not tested" for a GPU that was never probed', () => {
		renderComponent(GpuEncoderChips, { props: { gpu } });
		expect(screen.getByText('Not tested')).toBeInTheDocument();
		expect(screen.queryByText('Nothing verified')).not.toBeInTheDocument();
		expect(screen.queryByText(/available/)).not.toBeInTheDocument();
	});

	it('shows only "Nothing verified" for a tested GPU with no encoders', () => {
		renderComponent(GpuEncoderChips, { props: { gpu: { ...gpu, probed_at: '2026-09-01T00:00:00Z' } } });
		expect(screen.getByText('Nothing verified')).toBeInTheDocument();
		expect(screen.queryByText('Not tested')).not.toBeInTheDocument();
		expect(screen.queryByText(/available/)).not.toBeInTheDocument();
	});

	it('shows one upper-cased "available" chip per verified encoder', () => {
		renderComponent(GpuEncoderChips, {
			props: { gpu: { ...gpu, probed_at: '2026-09-01T00:00:00Z', encoder_kinds: ['h264', 'hevc'] } }
		});
		expect(screen.getByText('H264 available')).toBeInTheDocument();
		expect(screen.getByText('HEVC available')).toBeInTheDocument();
		expect(screen.queryByText('Not tested')).not.toBeInTheDocument();
		expect(screen.queryByText('Nothing verified')).not.toBeInTheDocument();
	});
});
