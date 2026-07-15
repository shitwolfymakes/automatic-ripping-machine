import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';

// vi.mock factories are hoisted — all values must be inline (no top-level vars).
vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	const store = writable({
		db_available: true,
		arm_online: true,
		active_jobs: [
			{ job_id: 1, status: 'ripping', title: 'Movie A' },
			{ job_id: 2, status: 'transcoding', title: 'Movie B' }
		],
		drives_online: 2,
		drive_names: {},
		notification_count: 3,
		ripping_enabled: true,
		makemkv_key_valid: true,
		makemkv_key_checked_at: null,
		transcoder_online: true,
		transcoder_stats: { worker_running: true, pending: 4 },
		active_transcodes: [{ id: 't1' }]
	});
	return {
		dashboard: { ...store, start: vi.fn(), stop: vi.fn(), error: writable(null) }
	};
});

vi.mock('$lib/stores/resources.svelte', async () => {
	const { readable } = await import('svelte/store');
	return {
		resources: readable([
			{
				role: 'backend',
				hostname: 'backend-1',
				version: '1',
				snapshot: {
					cpu_percent: 42,
					cpu_temp: 0,
					memory: { total_gb: 16, used_gb: 8, free_gb: 8, percent: 50 },
					storage: [{ name: 'Raw', path: '/raw', total_gb: 100, used_gb: 20, free_gb: 80, percent: 20 }]
				}
			}
		]),
		startResources: vi.fn(),
		stopResources: vi.fn()
	};
});

import MobileStatsPanel from '$lib/components/MobileStatsPanel.svelte';

// jsdom can't navigate; prevent the default so anchor clicks don't log
// "Not implemented: navigation to another Document".
const preventNav = (e: Event) => e.preventDefault();
beforeEach(() => document.addEventListener('click', preventNav));
afterEach(() => {
	document.removeEventListener('click', preventNav);
	cleanup();
});

describe('MobileStatsPanel', () => {
	it('renders the four service-health rows', () => {
		renderComponent(MobileStatsPanel);
		expect(screen.getByText('ARM')).toBeInTheDocument();
		expect(screen.getByText('DB')).toBeInTheDocument();
		expect(screen.getByText('Transcode')).toBeInTheDocument();
		expect(screen.getByText('Key')).toBeInTheDocument();
	});

	it('renders live activity counts from the dashboard store', () => {
		renderComponent(MobileStatsPanel);
		expect(screen.getByText(/2 drives/)).toBeInTheDocument();
		// One ripping job (transcoding job excluded from the ripping count)
		expect(screen.getByText(/1 ripping/)).toBeInTheDocument();
		expect(screen.getByText(/1 transcoding/)).toBeInTheDocument();
		expect(screen.getByText(/4 queued/)).toBeInTheDocument();
		expect(screen.getByText(/3 notifications/)).toBeInTheDocument();
	});

	it('renders the resource stats panel (CPU/Mem/Storage)', () => {
		renderComponent(MobileStatsPanel);
		expect(screen.getByText('CPU')).toBeInTheDocument();
		expect(screen.getByText(/42/)).toBeInTheDocument();
		expect(screen.getByText('Raw')).toBeInTheDocument();
	});

	it('fires onnavigate when any link inside the panel is clicked', async () => {
		const onnavigate = vi.fn();
		renderComponent(MobileStatsPanel, { props: { onnavigate } });
		await fireEvent.click(screen.getByText('ARM'));
		expect(onnavigate).toHaveBeenCalledTimes(1);
	});

	it('does not fire onnavigate for non-link clicks', async () => {
		const onnavigate = vi.fn();
		renderComponent(MobileStatsPanel, { props: { onnavigate } });
		await fireEvent.click(screen.getByText('CPU'));
		expect(onnavigate).not.toHaveBeenCalled();
	});
});
