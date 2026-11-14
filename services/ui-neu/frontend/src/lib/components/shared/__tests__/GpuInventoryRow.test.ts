import { describe, it, expect, afterEach } from 'vitest';
import { createRawSnippet } from 'svelte';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import type { GpuView } from '$lib/types/api.gen';
import GpuInventoryRow from '../GpuInventoryRow.svelte';

function gpu(over: Partial<GpuView> = {}): GpuView {
	return {
		id: 'gpu_1',
		vendor: 'vaapi',
		device_path: '/dev/dri/renderD128',
		encoder_kinds: ['h264'],
		status: 'available',
		enabled: true,
		claimed_by_task_id: null,
		last_seen_at: null,
		probed_at: null,
		probe_error: null,
		...over
	} as GpuView;
}

const dot = () => document.querySelector('.status-dot') as HTMLElement;

describe('GpuInventoryRow', () => {
	afterEach(() => cleanup());

	it('shows the vendor, the device path and an available state', () => {
		renderComponent(GpuInventoryRow, { props: { gpu: gpu() } });
		expect(screen.getByText('VAAPI')).toBeInTheDocument();
		expect(screen.getByText('/dev/dri/renderD128')).toHaveAttribute('title', '/dev/dri/renderD128');
		expect(screen.getByText('available')).toBeInTheDocument();
		expect(dot()).toHaveAttribute('data-status', 'ok');
	});

	it('names the vendors people know', () => {
		renderComponent(GpuInventoryRow, { props: { gpu: gpu({ vendor: 'qsv' }) } });
		expect(screen.getByText('Quick Sync')).toBeInTheDocument();
	});

	it('upper-cases a vendor it has no friendly name for', () => {
		renderComponent(GpuInventoryRow, { props: { gpu: gpu({ vendor: 'amf' as GpuView['vendor'] }) } });
		expect(screen.getByText('AMF')).toBeInTheDocument();
	});

	it('shows a busy device as a warning', () => {
		renderComponent(GpuInventoryRow, { props: { gpu: gpu({ status: 'busy', claimed_by_task_id: 'txt_1' }) } });
		expect(screen.getByText('busy')).toBeInTheDocument();
		expect(dot()).toHaveAttribute('data-status', 'warn');
	});

	it('a disabled device reads disabled whatever its status', () => {
		renderComponent(GpuInventoryRow, { props: { gpu: gpu({ enabled: false, status: 'busy' }) } });
		expect(screen.getByText('disabled')).toBeInTheDocument();
		expect(dot()).toHaveAttribute('data-status', 'off');
	});

	it('renders the caller’s kinds and controls snippets around the state', () => {
		const kinds = createRawSnippet(() => ({ render: () => '<span>H264 available</span>' }));
		const controls = createRawSnippet(() => ({ render: () => '<button type="button">Re-probe</button>' }));
		renderComponent(GpuInventoryRow, { props: { gpu: gpu(), kinds, controls } });
		expect(screen.getByText('H264 available')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Re-probe' })).toBeInTheDocument();
	});
});
