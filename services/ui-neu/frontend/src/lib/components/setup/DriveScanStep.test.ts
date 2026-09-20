import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor } from '$lib/test-utils';
import DriveScanStep from './DriveScanStep.svelte';

function mockFetchJson(data: unknown) {
	vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(data) })));
}

const sampleDrive = { id: 'drv_1', display_name: 'Main Drive', device_path: '/dev/sr0', hostname: 'arm-host', status: 'online' };

describe('DriveScanStep', () => {
	afterEach(() => { cleanup(); vi.restoreAllMocks(); });

	it('renders heading and no-drives message when empty', async () => {
		mockFetchJson([]);
		renderComponent(DriveScanStep);
		expect(screen.getByText('Optical Drives')).toBeInTheDocument();
		await waitFor(() => expect(screen.getByText('No optical drives detected')).toBeInTheDocument());
	});

	it('shows drive name, device path, and hostname', async () => {
		mockFetchJson([sampleDrive]);
		renderComponent(DriveScanStep);
		await waitFor(() => {
			expect(screen.getByText('Main Drive')).toBeInTheDocument();
			expect(screen.getByText('/dev/sr0')).toBeInTheDocument();
			expect(screen.getByText(/arm-host/)).toBeInTheDocument();
		});
	});

	it('renders scan again button', async () => {
		mockFetchJson([]);
		renderComponent(DriveScanStep);
		await waitFor(() => expect(screen.getByText('Scan Again')).toBeInTheDocument());
	});

	it('shows error on fetch failure', async () => {
		vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false })));
		renderComponent(DriveScanStep);
		await waitFor(() => expect(screen.getByText('Failed to load drives')).toBeInTheDocument());
	});
});
