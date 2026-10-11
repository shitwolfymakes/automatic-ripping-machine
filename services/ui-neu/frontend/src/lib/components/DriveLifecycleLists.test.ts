import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';
import DriveLifecycleLists from './DriveLifecycleLists.svelte';
import type { DriveView } from '$lib/types/api.gen';
vi.mock('$lib/api/drives', () => ({
	enrollDrive: vi.fn(() => Promise.resolve({})),
	ignoreDrive: vi.fn(() => Promise.resolve({})),
	unignoreDrive: vi.fn(() => Promise.resolve({}))
}));
import { enrollDrive, ignoreDrive, unignoreDrive } from '$lib/api/drives';

function drive(over: Partial<DriveView> = {}): DriveView {
	return {
		id: 'drv_1',
		hostname: 'arm-ripper-abc',
		device_path: '/dev/sr0',
		display_name: null,
		status: 'online',
		last_seen_at: null,
		media_status: null,
		media_status_at: null,
		default_session_id: null,
		rip_speed: null,
		drive_mode: null,
		uhd_capable: null,
		prescan_cache_mb: null,
		prescan_timeout: null,
		prescan_retries: null,
		disc_enum_timeout: null,
		created_at: null,
		updated_at: null,
		lifecycle: 'detected',
		present: true,
		identity_kind: 'by_id',
		serial: 'AAAABBBB000E',
		by_id_name: 'usb-X_AAAABBBB000E-0:0',
		vendor: 'PIONEER',
		model: 'BD-RW BDR-S12JX',
		last_error: null,
		current_job: null,
		...over
	} as DriveView;
}

describe('DriveLifecycleLists', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('renders detected rows with model, serial, node and actions', () => {
		renderComponent(DriveLifecycleLists, {
			props: { detected: [drive({ id: 'drv_d' })], ignored: [], onchanged: vi.fn() }
		});
		const row = screen.getByTestId('detected-row-drv_d');
		expect(row).toHaveTextContent('BD-RW BDR-S12JX');
		expect(row).toHaveTextContent('AAAABBBB000E');
		expect(row).toHaveTextContent('/dev/sr0');
		expect(screen.getByTestId('enroll-drv_d')).toBeInTheDocument();
		expect(screen.getByTestId('ignore-drv_d')).toBeInTheDocument();
		expect(screen.queryByTestId('ignored-toggle')).not.toBeInTheDocument();
	});

	it('renders last_seen_at as a localized date/time, not the raw ISO string', () => {
		renderComponent(DriveLifecycleLists, {
			props: {
				detected: [drive({ id: 'drv_d', last_seen_at: '2026-01-02T03:04:05Z' })],
				ignored: [],
				onchanged: vi.fn()
			}
		});
		const row = screen.getByTestId('detected-row-drv_d');
		expect(row).not.toHaveTextContent('2026-01-02T03:04:05Z');
		expect(row).toHaveTextContent(new Date('2026-01-02T03:04:05Z').toLocaleString());
	});

	it('shows - when last_seen_at is null', () => {
		renderComponent(DriveLifecycleLists, {
			props: { detected: [drive({ id: 'drv_d', last_seen_at: null })], ignored: [], onchanged: vi.fn() }
		});
		expect(screen.getByTestId('detected-row-drv_d')).toHaveTextContent('-');
	});

	it('flags a port-identity drive', () => {
		renderComponent(DriveLifecycleLists, {
			props: {
				detected: [drive({ id: 'drv_p', serial: null, identity_kind: 'port' })],
				ignored: [],
				onchanged: vi.fn()
			}
		});
		expect(screen.getByTestId('detected-row-drv_p')).toHaveTextContent('no serial, identified by port');
	});

	it('shows the empty state', () => {
		renderComponent(DriveLifecycleLists, { props: { detected: [], ignored: [], onchanged: vi.fn() } });
		expect(screen.getByTestId('detected-empty')).toHaveTextContent('No unenrolled drives.');
	});

	it('Enroll and Ignore call the API and notify', async () => {
		const onchanged = vi.fn();
		renderComponent(DriveLifecycleLists, { props: { detected: [drive({ id: 'drv_d' })], ignored: [], onchanged } });
		await fireEvent.click(screen.getByTestId('enroll-drv_d'));
		await waitFor(() => expect(onchanged).toHaveBeenCalledTimes(1));
		expect(enrollDrive).toHaveBeenCalledWith('drv_d');
		await fireEvent.click(screen.getByTestId('ignore-drv_d'));
		await waitFor(() => expect(onchanged).toHaveBeenCalledTimes(2));
		expect(ignoreDrive).toHaveBeenCalledWith('drv_d');
	});

	it('Ignored section is collapsed with a count and offers Un-ignore + Enroll', async () => {
		renderComponent(DriveLifecycleLists, {
			props: { detected: [], ignored: [drive({ id: 'drv_i', lifecycle: 'ignored' })], onchanged: vi.fn() }
		});
		const toggle = screen.getByTestId('ignored-toggle');
		expect(toggle).toHaveTextContent('Ignored (1)');
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(screen.queryByTestId('ignored-row-drv_i')).not.toBeInTheDocument();
		await fireEvent.click(toggle);
		expect(screen.getByTestId('ignored-toggle')).toHaveTextContent('Ignored (1)');
		expect(screen.getByTestId('unignore-drv_i')).toBeInTheDocument();
		expect(screen.getByTestId('enroll-drv_i')).toBeInTheDocument();
		await fireEvent.click(screen.getByTestId('unignore-drv_i'));
		await waitFor(() => expect(unignoreDrive).toHaveBeenCalledWith('drv_i'));
	});

	it('surfaces a backend error', async () => {
		vi.mocked(enrollDrive).mockRejectedValueOnce(new Error('ImageNotFound: arm-ripper:latest'));
		renderComponent(DriveLifecycleLists, {
			props: { detected: [drive({ id: 'drv_d' })], ignored: [], onchanged: vi.fn() }
		});
		await fireEvent.click(screen.getByTestId('enroll-drv_d'));
		await waitFor(() => expect(screen.getByTestId('lifecycle-error-drv_d')).toHaveTextContent('ImageNotFound'));
	});

	it('shows Starting ripper while enrolling, then a per-drive error with Retry', async () => {
		let reject!: (e: Error) => void;
		vi.mocked(enrollDrive).mockImplementationOnce(() => new Promise((_, r) => (reject = r)));
		renderComponent(DriveLifecycleLists, {
			props: { detected: [drive({ id: 'a' }), drive({ id: 'b' })], ignored: [], onchanged: vi.fn() }
		});
		await fireEvent.click(screen.getByTestId('enroll-a'));
		expect(within(screen.getByTestId('detected-row-a')).getByText('Starting ripper...')).toBeInTheDocument();
		expect(screen.getByTestId('enroll-b')).not.toBeDisabled();
		reject(new Error('device /dev/sr2 is busy'));
		await waitFor(() => expect(screen.getByTestId('lifecycle-error-a')).toHaveTextContent('device /dev/sr2 is busy'));
		expect(screen.getByTestId('lifecycle-error-a')).toHaveTextContent('Other drives are not affected.');
		expect(screen.getByTestId('enroll-a')).toHaveTextContent('Retry');
		expect(screen.queryByTestId('lifecycle-error-b')).toBeNull();
	});

	it('shows a backend last_error as a failed enroll', () => {
		renderComponent(DriveLifecycleLists, {
			props: { detected: [drive({ id: 'a', last_error: 'ImageNotFound' })], ignored: [], onchanged: vi.fn() }
		});
		expect(screen.getByTestId('lifecycle-error-a')).toHaveTextContent('ImageNotFound');
	});

	it('disables Enroll with a reason', () => {
		renderComponent(DriveLifecycleLists, {
			props: {
				detected: [drive({ id: 'a' })],
				ignored: [],
				onchanged: vi.fn(),
				enrollDisabledReason: 'Fix the ripper service first.'
			}
		});
		expect(screen.getByTestId('enroll-a')).toBeDisabled();
		expect(screen.getByTestId('enroll-disabled-reason')).toHaveTextContent('Fix the ripper service first.');
	});

	it('renders connection and media chips', () => {
		renderComponent(DriveLifecycleLists, {
			props: {
				detected: [drive({ id: 'a', connection: 'usb', media_status: 'loaded' } as Partial<DriveView>)],
				ignored: [],
				onchanged: vi.fn()
			}
		});
		const row = screen.getByTestId('detected-row-a');
		expect(row).toHaveTextContent('USB');
		expect(row).toHaveTextContent('Disc in drive');
		expect(row).toHaveTextContent('PIONEER BD-RW BDR-S12JX');
	});

	it('flags a drive that appears after the first render as New', async () => {
		const { rerender } = renderComponent(DriveLifecycleLists, {
			props: { detected: [drive({ id: 'a' })], ignored: [], onchanged: vi.fn() }
		});
		expect(within(screen.getByTestId('detected-row-a')).queryByText('New')).toBeNull();
		await rerender({ detected: [drive({ id: 'a' }), drive({ id: 'b' })], ignored: [], onchanged: vi.fn() });
		expect(within(screen.getByTestId('detected-row-b')).getByText('New')).toBeInTheDocument();
	});
});
