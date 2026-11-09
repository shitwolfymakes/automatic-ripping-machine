// One drive row of the lifecycle lists, rendered directly.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, within, cleanup } from '$lib/test-utils';
import DriveLifecycleRow from '../DriveLifecycleRow.svelte';
import type { DriveView } from '$lib/types/api.gen';

type Defaults = NonNullable<Parameters<typeof renderComponent>[1]>;

function drive(over: Partial<DriveView> = {}): DriveView {
	return {
		id: 'drv_1',
		hostname: 'arm-ripper-abc',
		device_path: '/dev/sr0',
		display_name: null,
		status: 'online',
		last_seen_at: null,
		media_status: null,
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

function renderRow(props: Record<string, unknown> = {}) {
	const callbacks = { onenroll: vi.fn(), ontoggleignore: vi.fn() };
	renderComponent(DriveLifecycleRow, {
		props: {
			drive: drive(),
			ignored: false,
			isNew: false,
			busy: undefined,
			error: undefined,
			enrollDisabledReason: null,
			...callbacks,
			...props
		}
	} as Defaults);
	return callbacks;
}

describe('DriveLifecycleRow', () => {
	afterEach(cleanup);

	it('shows the name, the path with its by-id name, the serial and a dash for no last-seen', () => {
		renderRow({ drive: drive({ connection: 'usb', media_status: 'loaded' } as Partial<DriveView>) });
		const row = screen.getByTestId('detected-row-drv_1');
		expect(within(row).getByText('PIONEER BD-RW BDR-S12JX')).toBeInTheDocument();
		expect(row.querySelector('code')?.textContent).toBe('/dev/sr0  usb-X_AAAABBBB000E-0:0');
		expect(within(row).getByText('USB')).toBeInTheDocument();
		expect(within(row).getByText('Disc in drive')).toBeInTheDocument();
		expect(within(row).getByText('AAAABBBB000E')).toHaveAttribute('data-warn', 'false');
		expect(row.querySelector('.drive-lifecycle-lists-seen')?.textContent).toBe('-');
	});

	it('shows the bare path without a by-id name, a warned serial and a formatted last-seen', () => {
		renderRow({ drive: drive({ by_id_name: null, serial: null, last_seen_at: '2026-01-02T03:04:05Z' }) });
		const row = screen.getByTestId('detected-row-drv_1');
		expect(row.querySelector('code')?.textContent).toBe('/dev/sr0');
		expect(row.querySelector('.drive-lifecycle-lists-serial')).toHaveAttribute('data-warn', 'true');
		expect(row.querySelector('.drive-lifecycle-lists-seen')?.textContent).not.toBe('-');
	});

	it('shows the New badge and data-new only on a new detected row', () => {
		renderRow({ isNew: true });
		expect(screen.getByText('New')).toBeInTheDocument();
		expect(screen.getByTestId('detected-row-drv_1')).toHaveAttribute('data-new', 'true');
	});

	it('hides the New badge on an ignored row even when new', () => {
		renderRow({ isNew: true, ignored: true });
		expect(screen.queryByText('New')).toBeNull();
		expect(screen.getByTestId('ignored-row-drv_1')).toHaveAttribute('data-new', 'false');
	});

	it('hides the New badge on a detected row that is not new', () => {
		renderRow();
		expect(screen.queryByText('New')).toBeNull();
		expect(screen.getByTestId('detected-row-drv_1')).toHaveAttribute('data-new', 'false');
	});

	it('calls ontoggleignore from Ignore on a detected row', async () => {
		const cb = renderRow();
		expect(screen.queryByTestId('unignore-drv_1')).toBeNull();
		await fireEvent.click(screen.getByTestId('ignore-drv_1'));
		expect(cb.ontoggleignore).toHaveBeenCalledTimes(1);
	});

	it('calls ontoggleignore from Un-ignore on an ignored row', async () => {
		const cb = renderRow({ ignored: true });
		expect(screen.queryByTestId('ignore-drv_1')).toBeNull();
		await fireEvent.click(screen.getByTestId('unignore-drv_1'));
		expect(cb.ontoggleignore).toHaveBeenCalledTimes(1);
	});

	it('calls onenroll from Enroll', async () => {
		const cb = renderRow();
		await fireEvent.click(screen.getByTestId('enroll-drv_1'));
		expect(cb.onenroll).toHaveBeenCalledTimes(1);
	});

	it('disables every button while busy', () => {
		renderRow({ busy: 'other' });
		expect(screen.getByTestId('ignore-drv_1')).toBeDisabled();
		expect(screen.getByTestId('enroll-drv_1')).toBeDisabled();
	});

	it('disables Un-ignore while busy on an ignored row', () => {
		renderRow({ busy: 'other', ignored: true });
		expect(screen.getByTestId('unignore-drv_1')).toBeDisabled();
	});

	it('disables only Enroll when enrolling is not possible', () => {
		renderRow({ enrollDisabledReason: 'Ripper is down' });
		expect(screen.getByTestId('enroll-drv_1')).toBeDisabled();
		expect(screen.getByTestId('ignore-drv_1')).not.toBeDisabled();
	});

	it('disables Enroll with a title and shows Not connected for an absent drive', () => {
		renderRow({ drive: drive({ present: false }) });
		const enroll = screen.getByTestId('enroll-drv_1');
		expect(enroll).toBeDisabled();
		expect(enroll).toHaveAttribute('title', 'Not connected; plug the drive in to enroll it');
		expect(screen.getByTestId('not-connected-drv_1')).toHaveTextContent('Not connected');
		expect(screen.queryByText('Not enrolled')).toBeNull();
	});

	it('shows the Starting ripper strip while enrolling', () => {
		renderRow({ busy: 'enroll' });
		expect(screen.getByText('Starting ripper...')).toBeInTheDocument();
		expect(screen.queryByText('Not enrolled')).toBeNull();
	});

	it('shows the failure strip, data-failed and Retry for an error on a detected row', () => {
		renderRow({ error: 'boom' });
		expect(screen.getByTestId('lifecycle-error-drv_1')).toHaveTextContent('boom');
		expect(screen.getByTestId('detected-row-drv_1')).toHaveAttribute('data-failed', 'true');
		expect(screen.getByTestId('enroll-drv_1')).toHaveTextContent('Retry');
	});

	it('shows Enroll, not Retry, for an error on an ignored row', () => {
		renderRow({ error: 'boom', ignored: true });
		expect(screen.getByTestId('lifecycle-error-drv_1')).toHaveTextContent('boom');
		expect(screen.getByTestId('enroll-drv_1')).toHaveTextContent('Enroll');
		expect(screen.getByTestId('enroll-drv_1')).not.toHaveTextContent('Retry');
	});

	it('uses last_error on a detected row', () => {
		renderRow({ drive: drive({ last_error: 'stale failure' }) });
		expect(screen.getByTestId('lifecycle-error-drv_1')).toHaveTextContent('stale failure');
		expect(screen.getByTestId('enroll-drv_1')).toHaveTextContent('Retry');
	});

	it('ignores last_error on an ignored row', () => {
		renderRow({ drive: drive({ last_error: 'stale failure' }), ignored: true });
		expect(screen.queryByTestId('lifecycle-error-drv_1')).toBeNull();
		expect(screen.getByTestId('ignored-row-drv_1')).toHaveAttribute('data-failed', 'false');
	});

	it('shows Not enrolled on an idle detected row', () => {
		renderRow();
		expect(screen.getByText('Not enrolled')).toBeInTheDocument();
	});

	it('shows no strip on an idle ignored row', () => {
		renderRow({ ignored: true });
		expect(screen.queryByText('Not enrolled')).toBeNull();
		expect(screen.queryByTestId('not-connected-drv_1')).toBeNull();
		expect(screen.queryByTestId('lifecycle-error-drv_1')).toBeNull();
	});
});
