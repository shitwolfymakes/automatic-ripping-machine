import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import DriveCard from './DriveCard.svelte';
import type { DriveView as Drive } from '$lib/types/api.gen';
vi.mock('$lib/api/drives', () => ({
	updateDrive: vi.fn(() => Promise.resolve()),
	scanDrive: vi.fn(() => Promise.resolve()),
	deleteDrive: vi.fn(() => Promise.resolve()),
	ejectDrive: vi.fn(() => Promise.resolve())
}));

function createDrive(overrides: Partial<Drive> = {}): Drive {
	return {
		id: 'drv_1',
		hostname: 'arm-host',
		device_path: '/dev/sr0',
		display_name: 'Main Drive',
		status: 'online',
		last_seen_at: null,
		media_status: null,
		media_status_at: null,
		default_session_id: null,
		rip_speed: null,
		drive_mode: null,
		uhd_capable: false,
		prescan_cache_mb: null,
		prescan_timeout: null,
		prescan_retries: null,
		disc_enum_timeout: null,
		created_at: null,
		updated_at: null,
		current_job: null,
		...overrides
	};
}

function renderDrive(overrides: Partial<Drive> = {}) {
	return renderComponent(DriveCard, { props: { drive: createDrive(overrides) } });
}

describe('DriveCard', () => {
	afterEach(() => cleanup());

	describe('rendering', () => {
		it('renders drive name, device path, 4K toggle, and action bar', () => {
			renderDrive();
			expect(screen.getByText('Main Drive')).toBeInTheDocument();
			expect(screen.getByText('Idle')).toBeInTheDocument();
			const matches = screen.getAllByText('/dev/sr0');
			expect(matches.length).toBeGreaterThan(0);
			// Action bar buttons
			expect(screen.getByText('Eject')).toBeInTheDocument();
			expect(screen.getByText('Insert')).toBeInTheDocument();
			expect(screen.getByText('Scan')).toBeInTheDocument();
			expect(screen.queryByText('Remove')).not.toBeInTheDocument();
		});

		it('shows hostname when available', () => {
			renderDrive({ hostname: 'media-box' });
			expect(screen.getByText(/media-box/)).toBeInTheDocument();
		});

		it('shows the 4K toggle', () => {
			renderDrive();
			expect(screen.getByText('4K')).toBeInTheDocument();
		});

		it('shows media status badge when present', () => {
			renderDrive({ media_status: 'loaded' });
			expect(screen.getByText('loaded')).toBeInTheDocument();
		});

		it('falls back to device path when no display name', () => {
			renderDrive({ display_name: null });
			const matches = screen.getAllByText('/dev/sr0');
			expect(matches.find((el) => el.tagName === 'H3')).toBeDefined();
		});

		it('falls back to Drive id when no display name or device path', () => {
			renderDrive({ display_name: null, device_path: '' });
			expect(screen.getByText('Drive drv_1')).toBeInTheDocument();
		});

		it('shows Stale badge and Remove button for offline drives', () => {
			renderDrive({ status: 'offline' });
			expect(screen.getByText('Stale')).toBeInTheDocument();
			expect(screen.getByText('Remove')).toBeInTheDocument();
		});
	});

	describe('prescan overrides badge', () => {
		it('shows custom badge when prescan overrides are set', () => {
			renderDrive({ prescan_cache_mb: 64, prescan_timeout: 600 });
			expect(screen.getByText('2 custom')).toBeInTheDocument();
		});

		it('hides custom badge when no prescan overrides', () => {
			renderDrive();
			expect(screen.queryByText(/custom/)).not.toBeInTheDocument();
		});
	});

	describe('prescan settings panel', () => {
		it('shows prescan inputs in settings panel', async () => {
			renderDrive();
			await fireEvent.click(screen.getByTitle('Drive settings'));
			expect(screen.getByText('Drive Settings')).toBeInTheDocument();
			expect(screen.getByText('Pre-scan Cache')).toBeInTheDocument();
			expect(screen.getByText('Pre-scan Timeout')).toBeInTheDocument();
			expect(screen.getByText('Pre-scan Retries')).toBeInTheDocument();
			expect(screen.getByText('Enum Timeout')).toBeInTheDocument();
		});

		it('shows tooltips for prescan fields', async () => {
			renderDrive();
			await fireEvent.click(screen.getByTitle('Drive settings'));
			expect(screen.getByText(/Community recommends 64-128/)).toBeInTheDocument();
			expect(screen.getByText(/Community recommends 600/)).toBeInTheDocument();
			expect(screen.getByText(/Community recommends 3-5/)).toBeInTheDocument();
			expect(screen.getByText(/Community recommends 120/)).toBeInTheDocument();
		});

		it('populates prescan inputs from drive values', async () => {
			renderDrive({ prescan_cache_mb: 128, prescan_retries: 5 });
			await fireEvent.click(screen.getByTitle('Drive settings'));
			const cacheInput = screen.getByLabelText(/Pre-scan Cache/) as HTMLInputElement;
			const retriesInput = screen.getByLabelText(/Pre-scan Retries/) as HTMLInputElement;
			expect(cacheInput.value).toBe('128');
			expect(retriesInput.value).toBe('5');
		});

		it('saves prescan field on blur', async () => {
			const { updateDrive } = await import('$lib/api/drives');
			renderDrive();
			await fireEvent.click(screen.getByTitle('Drive settings'));
			const cacheInput = screen.getByLabelText(/Pre-scan Cache/) as HTMLInputElement;
			await fireEvent.input(cacheInput, { target: { value: '64' } });
			await fireEvent.blur(cacheInput);
			expect(updateDrive).toHaveBeenCalledWith('drv_1', { prescan_cache_mb: 64 });
		});
	});

	describe('interactions', () => {
		it('enters and exits edit mode via Rename button', async () => {
			renderDrive();
			await fireEvent.click(screen.getByText('Rename'));
			expect(screen.getByDisplayValue('Main Drive')).toBeInTheDocument();
			expect(screen.getByText('Save')).toBeInTheDocument();
			await fireEvent.click(screen.getByText('Cancel'));
			expect(screen.getByText('Rename')).toBeInTheDocument();
		});
	});

	describe('skeleton', () => {
		it('renders a SkeletonCard when drive prop is omitted', () => {
			const { container } = renderComponent(DriveCard, { props: {} });
			expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
		});
	});
});
