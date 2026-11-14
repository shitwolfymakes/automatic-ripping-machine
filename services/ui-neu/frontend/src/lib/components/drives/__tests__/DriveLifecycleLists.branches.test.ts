import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';
import DriveLifecycleLists from '../DriveLifecycleLists.svelte';
import type { DriveView } from '$lib/types/api.gen';

// Branch pins for DriveLifecycleLists, beside DriveLifecycleLists.test.ts. It
// covers every branch of the component, so nothing here is left unreachable.

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

function ignoredDrive(id: string, over: Partial<DriveView> = {}): DriveView {
	return drive({ id, lifecycle: 'ignored', ...over });
}

/** A promise the test settles by hand, so a row can be held pending. */
function deferred() {
	let resolve!: () => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<DriveView>((res, rej) => {
		resolve = () => res(drive());
		reject = rej;
	});
	return { promise, resolve, reject };
}

async function openIgnored() {
	await fireEvent.click(screen.getByTestId('ignored-toggle'));
}

describe('DriveLifecycleLists branches', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('falls back to "Action failed" when an action rejects with a non-Error', async () => {
		vi.mocked(enrollDrive).mockRejectedValueOnce('boom');
		renderComponent(DriveLifecycleLists, {
			props: { detected: [drive({ id: 'a' })], ignored: [], onchanged: vi.fn() }
		});
		await fireEvent.click(screen.getByTestId('enroll-a'));
		await waitFor(() => expect(screen.getByTestId('lifecycle-error-a')).toHaveTextContent('Action failed'));
	});

	describe('busy state', () => {
		it('Ignore disables only that row buttons while pending', async () => {
			const d = deferred();
			vi.mocked(ignoreDrive).mockImplementationOnce(() => d.promise);
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a' }), drive({ id: 'b' })], ignored: [], onchanged: vi.fn() }
			});
			await fireEvent.click(screen.getByTestId('ignore-a'));
			expect(screen.getByTestId('ignore-a')).toBeDisabled();
			expect(screen.getByTestId('enroll-a')).toBeDisabled();
			expect(screen.getByTestId('ignore-b')).toBeEnabled();
			expect(screen.getByTestId('enroll-b')).toBeEnabled();
			expect(within(screen.getByTestId('detected-row-a')).queryByText('Starting ripper...')).toBeNull();
			d.resolve();
			await waitFor(() => expect(screen.getByTestId('ignore-a')).toBeEnabled());
		});

		it('Un-ignore disables only that row buttons while pending', async () => {
			const d = deferred();
			vi.mocked(unignoreDrive).mockImplementationOnce(() => d.promise);
			renderComponent(DriveLifecycleLists, {
				props: { detected: [], ignored: [ignoredDrive('i1'), ignoredDrive('i2')], onchanged: vi.fn() }
			});
			await openIgnored();
			await fireEvent.click(screen.getByTestId('unignore-i1'));
			expect(screen.getByTestId('unignore-i1')).toBeDisabled();
			expect(screen.getByTestId('enroll-i1')).toBeDisabled();
			expect(screen.getByTestId('unignore-i2')).toBeEnabled();
			expect(screen.getByTestId('enroll-i2')).toBeEnabled();
			d.resolve();
			await waitFor(() => expect(screen.getByTestId('unignore-i1')).toBeEnabled());
		});

		it('Enroll disables only that row buttons and shows the Starting ripper strip', async () => {
			const d = deferred();
			vi.mocked(enrollDrive).mockImplementationOnce(() => d.promise);
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a' }), drive({ id: 'b' })], ignored: [], onchanged: vi.fn() }
			});
			await fireEvent.click(screen.getByTestId('enroll-a'));
			expect(screen.getByTestId('enroll-a')).toBeDisabled();
			expect(screen.getByTestId('ignore-a')).toBeDisabled();
			expect(screen.getByTestId('enroll-b')).toBeEnabled();
			expect(screen.getByTestId('ignore-b')).toBeEnabled();
			expect(within(screen.getByTestId('detected-row-a')).getByText('Starting ripper...')).toBeInTheDocument();
			expect(within(screen.getByTestId('detected-row-b')).queryByText('Starting ripper...')).toBeNull();
			d.resolve();
			await waitFor(() => expect(screen.getByTestId('enroll-a')).toBeEnabled());
			expect(within(screen.getByTestId('detected-row-a')).queryByText('Starting ripper...')).toBeNull();
		});
	});

	describe('errors', () => {
		it('clears the same row error when its next action starts, and keeps other rows errors', async () => {
			vi.mocked(ignoreDrive).mockRejectedValueOnce(new Error('first failure'));
			vi.mocked(enrollDrive).mockRejectedValueOnce(new Error('b failure'));
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a' }), drive({ id: 'b' })], ignored: [], onchanged: vi.fn() }
			});
			await fireEvent.click(screen.getByTestId('ignore-a'));
			await waitFor(() => expect(screen.getByTestId('lifecycle-error-a')).toHaveTextContent('first failure'));
			await fireEvent.click(screen.getByTestId('enroll-b'));
			await waitFor(() => expect(screen.getByTestId('lifecycle-error-b')).toHaveTextContent('b failure'));

			const d = deferred();
			vi.mocked(ignoreDrive).mockImplementationOnce(() => d.promise);
			await fireEvent.click(screen.getByTestId('ignore-a'));
			expect(screen.queryByTestId('lifecycle-error-a')).toBeNull();
			expect(screen.getByTestId('lifecycle-error-b')).toHaveTextContent('b failure');
			expect(screen.getByTestId('detected-row-a')).toHaveAttribute('data-failed', 'false');
			expect(screen.getByTestId('detected-row-b')).toHaveAttribute('data-failed', 'true');
			d.resolve();
			await waitFor(() => expect(screen.getByTestId('ignore-a')).toBeEnabled());
		});

		it('replaces a failed Enroll error with the busy strip on retry', async () => {
			vi.mocked(enrollDrive).mockRejectedValueOnce(new Error('first failure'));
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a' })], ignored: [], onchanged: vi.fn() }
			});
			await fireEvent.click(screen.getByTestId('enroll-a'));
			await waitFor(() => expect(screen.getByTestId('enroll-a')).toHaveTextContent('Retry'));
			const d = deferred();
			vi.mocked(enrollDrive).mockImplementationOnce(() => d.promise);
			await fireEvent.click(screen.getByTestId('enroll-a'));
			expect(screen.queryByTestId('lifecycle-error-a')).toBeNull();
			expect(within(screen.getByTestId('detected-row-a')).getByText('Starting ripper...')).toBeInTheDocument();
			d.resolve();
			await waitFor(() => expect(screen.getByTestId('enroll-a')).toBeEnabled());
			expect(screen.getByTestId('enroll-a')).toHaveTextContent('Enroll');
		});

		it('keeps Enroll, not Retry, on an ignored row that errored', async () => {
			vi.mocked(unignoreDrive).mockRejectedValueOnce(new Error('unignore failed'));
			renderComponent(DriveLifecycleLists, {
				props: { detected: [], ignored: [ignoredDrive('i')], onchanged: vi.fn() }
			});
			await openIgnored();
			await fireEvent.click(screen.getByTestId('unignore-i'));
			await waitFor(() => expect(screen.getByTestId('lifecycle-error-i')).toHaveTextContent('unignore failed'));
			expect(screen.getByTestId('enroll-i')).toHaveTextContent('Enroll');
			expect(screen.getByTestId('enroll-i')).not.toHaveTextContent('Retry');
		});

		it('shows Retry on a detected row that errored', async () => {
			vi.mocked(ignoreDrive).mockRejectedValueOnce(new Error('ignore failed'));
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a' })], ignored: [], onchanged: vi.fn() }
			});
			expect(screen.getByTestId('enroll-a')).toHaveTextContent('Enroll');
			await fireEvent.click(screen.getByTestId('ignore-a'));
			await waitFor(() => expect(screen.getByTestId('enroll-a')).toHaveTextContent('Retry'));
		});
	});

	describe('last_error', () => {
		it('shows on a detected row, with Retry', () => {
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a', last_error: 'ImageNotFound' })], ignored: [], onchanged: vi.fn() }
			});
			expect(screen.getByTestId('lifecycle-error-a')).toHaveTextContent('ImageNotFound');
			expect(screen.getByTestId('enroll-a')).toHaveTextContent('Retry');
			expect(screen.getByTestId('detected-row-a')).toHaveAttribute('data-failed', 'true');
		});

		it('is ignored on an ignored row', async () => {
			renderComponent(DriveLifecycleLists, {
				props: { detected: [], ignored: [ignoredDrive('i', { last_error: 'ImageNotFound' })], onchanged: vi.fn() }
			});
			await openIgnored();
			expect(screen.queryByTestId('lifecycle-error-i')).toBeNull();
			expect(screen.getByTestId('ignored-row-i')).toHaveAttribute('data-failed', 'false');
			expect(screen.getByTestId('enroll-i')).toHaveTextContent('Enroll');
		});
	});

	describe('onchanged', () => {
		it('fires after each successful action, including Un-ignore', async () => {
			const onchanged = vi.fn();
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a' })], ignored: [ignoredDrive('i')], onchanged }
			});
			await openIgnored();
			await fireEvent.click(screen.getByTestId('unignore-i'));
			await waitFor(() => expect(onchanged).toHaveBeenCalledTimes(1));
			await fireEvent.click(screen.getByTestId('enroll-i'));
			await waitFor(() => expect(onchanged).toHaveBeenCalledTimes(2));
			expect(enrollDrive).toHaveBeenCalledWith('i');
		});

		it('does not fire after a failed action', async () => {
			const onchanged = vi.fn();
			vi.mocked(enrollDrive).mockRejectedValueOnce(new Error('nope'));
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a' })], ignored: [], onchanged }
			});
			await fireEvent.click(screen.getByTestId('enroll-a'));
			await waitFor(() => expect(screen.getByTestId('lifecycle-error-a')).toBeInTheDocument());
			expect(onchanged).not.toHaveBeenCalled();
		});
	});

	describe('New badge', () => {
		it('is not shown on ignored rows, even ones absent at first render', async () => {
			const { rerender } = renderComponent(DriveLifecycleLists, {
				props: { detected: [], ignored: [ignoredDrive('i1')], onchanged: vi.fn() }
			});
			await rerender({ detected: [], ignored: [ignoredDrive('i1'), ignoredDrive('i2')], onchanged: vi.fn() });
			await openIgnored();
			expect(screen.getByTestId('ignored-row-i2')).toHaveAttribute('data-new', 'false');
			expect(within(screen.getByTestId('ignored-row-i2')).queryByText('New')).toBeNull();
			expect(within(screen.getByTestId('ignored-row-i1')).queryByText('New')).toBeNull();
		});

		it('is shown only on the detected row that was not there at first render', async () => {
			const { rerender } = renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a' })], ignored: [], onchanged: vi.fn() }
			});
			await rerender({ detected: [drive({ id: 'a' }), drive({ id: 'b' })], ignored: [], onchanged: vi.fn() });
			expect(screen.getByTestId('detected-row-a')).toHaveAttribute('data-new', 'false');
			expect(screen.getByTestId('detected-row-b')).toHaveAttribute('data-new', 'true');
		});
	});

	describe('absent drive', () => {
		it('shows Not connected and a disabled titled Enroll on an ignored row', async () => {
			renderComponent(DriveLifecycleLists, {
				props: { detected: [], ignored: [ignoredDrive('i', { present: false })], onchanged: vi.fn() }
			});
			await openIgnored();
			expect(screen.getByTestId('not-connected-i')).toHaveTextContent('Not connected');
			expect(screen.getByTestId('enroll-i')).toBeDisabled();
			expect(screen.getByTestId('enroll-i')).toHaveAttribute('title', 'Not connected; plug the drive in to enroll it');
			expect(screen.getByTestId('unignore-i')).toBeEnabled();
		});

		it('shows Not connected on a detected row', () => {
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a', present: false })], ignored: [], onchanged: vi.fn() }
			});
			expect(screen.getByTestId('not-connected-a')).toHaveTextContent('Not connected');
			expect(screen.getByTestId('enroll-a')).toBeDisabled();
		});

		it('shows an error strip, not Not connected, when an absent row also has an error', () => {
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a', present: false, last_error: 'boom' })], ignored: [], onchanged: vi.fn() }
			});
			expect(screen.getByTestId('lifecycle-error-a')).toHaveTextContent('boom');
			expect(screen.queryByTestId('not-connected-a')).toBeNull();
		});
	});

	describe('Not enrolled strip', () => {
		it('shows on an idle detected row', () => {
			renderComponent(DriveLifecycleLists, {
				props: { detected: [drive({ id: 'a' })], ignored: [], onchanged: vi.fn() }
			});
			expect(within(screen.getByTestId('detected-row-a')).getByText('Not enrolled')).toBeInTheDocument();
		});

		it('does not show on an idle ignored row', async () => {
			renderComponent(DriveLifecycleLists, {
				props: { detected: [], ignored: [ignoredDrive('i')], onchanged: vi.fn() }
			});
			await openIgnored();
			expect(within(screen.getByTestId('ignored-row-i')).queryByText('Not enrolled')).toBeNull();
		});
	});
});
