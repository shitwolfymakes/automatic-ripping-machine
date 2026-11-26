// The full drive card's header and rename row, rendered directly. The drives
// API is mocked the same way as in DriveCard.branches.test.ts.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import DriveCardHeader from '../DriveCardHeader.svelte';
import type { DriveView as Drive } from '$lib/types/api.gen';
import { createDrive } from '../../../__fixtures__/drive';
import { DETACHED_LABEL } from '$lib/drives/drives';

vi.mock('$lib/api/drives', () => ({
	updateDrive: vi.fn(() => Promise.resolve())
}));
import { updateDrive } from '$lib/api/drives';
const updateDriveMock = vi.mocked(updateDrive);

type Defaults = NonNullable<Parameters<typeof renderComponent>[1]>;

function renderHeader(overrides: Partial<Drive> = {}, props: Record<string, unknown> = {}) {
	return renderComponent(DriveCardHeader, {
		props: { drive: createDrive(overrides), ...props }
	} as Defaults);
}

function nameInput() {
	return screen.getByRole('textbox') as HTMLInputElement;
}

async function openRename() {
	await fireEvent.click(screen.getByRole('button', { name: 'Rename' }));
}

beforeEach(() => {
	updateDriveMock.mockReset();
	updateDriveMock.mockResolvedValue(undefined as never);
});

afterEach(() => {
	cleanup();
});

describe('DriveCardHeader title', () => {
	it('shows the display name', () => {
		renderHeader();
		expect(screen.getByRole('heading', { name: 'Main Drive' })).toBeTruthy();
	});

	it('falls back to the device path', () => {
		renderHeader({ display_name: null });
		expect(screen.getByRole('heading', { name: '/dev/sr0' })).toBeTruthy();
	});

	it('falls back to Drive and the id', () => {
		renderHeader({ display_name: null, device_path: '' });
		expect(screen.getByRole('heading', { name: 'Drive drv_1' })).toBeTruthy();
	});
});

describe('DriveCardHeader status slot', () => {
	it('shows an error label with a title carrying last_error', () => {
		renderHeader({ status: 'error', last_error: 'boom' });
		expect(screen.getByTitle('error: boom').textContent).toBe('error: boom');
		expect(screen.queryByRole('button', { name: 'Rename' })).toBeNull();
	});

	it('shows a bare error label when there is no last_error', () => {
		renderHeader({ status: 'error', last_error: null });
		expect(screen.getByTitle('error').textContent).toBe('error');
	});

	it('shows the detached pill for a detached drive', () => {
		renderHeader({ media_status: 'detached' });
		expect(screen.getByText(DETACHED_LABEL)).toBeTruthy();
		expect(screen.queryByTestId('drive-status-label')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Rename' })).toBeNull();
	});

	it('shows the status pill for an offline but present drive', () => {
		renderHeader({ status: 'offline', present: true });
		expect(screen.getByTestId('drive-status-label').textContent).toBe('offline');
		expect(screen.queryByRole('button', { name: 'Rename' })).toBeNull();
	});

	it('shows Rename for an online drive', () => {
		renderHeader();
		expect(screen.getByRole('button', { name: 'Rename' })).toBeTruthy();
	});

	it('hides Rename while editing', async () => {
		renderHeader();
		await openRename();
		expect(screen.queryByRole('button', { name: 'Rename' })).toBeNull();
	});
});

describe('DriveCardHeader job badge', () => {
	it('shows the job status badge when there is a current job', () => {
		renderHeader({
			current_job: { id: 'job_1', status: 'ripping', title: 'Disc' }
		} as Partial<Drive>);
		expect(screen.queryByText('Idle')).toBeNull();
		expect(screen.getByText(/ripping/i)).toBeTruthy();
	});

	it('shows Idle when there is no current job', () => {
		renderHeader();
		expect(screen.getByText('Idle')).toBeTruthy();
	});
});

describe('DriveCardHeader rename', () => {
	it('opens the field prefilled with the display name', async () => {
		renderHeader();
		await openRename();
		expect(nameInput().value).toBe('Main Drive');
	});

	it('opens a blank field when there is no display name', async () => {
		renderHeader({ display_name: null });
		await openRename();
		expect(nameInput().value).toBe('');
	});

	it('saves the typed name on Enter, closes the field and calls onupdate', async () => {
		const onupdate = vi.fn();
		renderHeader({}, { onupdate });
		await openRename();
		await fireEvent.input(nameInput(), { target: { value: 'Living room' } });
		await fireEvent.keyDown(nameInput(), { key: 'Enter' });
		await waitFor(() => expect(screen.queryByRole('textbox')).toBeNull());
		expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: 'Living room' });
		expect(onupdate).toHaveBeenCalledTimes(1);
	});

	it('cancels on Escape without saving', async () => {
		renderHeader();
		await openRename();
		await fireEvent.keyDown(nameInput(), { key: 'Escape' });
		expect(screen.queryByRole('textbox')).toBeNull();
		expect(updateDriveMock).not.toHaveBeenCalled();
	});

	it('ignores other keys', async () => {
		renderHeader();
		await openRename();
		await fireEvent.keyDown(nameInput(), { key: 'a' });
		expect(nameInput()).toBeTruthy();
		expect(updateDriveMock).not.toHaveBeenCalled();
	});

	it('saves from the Save button', async () => {
		const onupdate = vi.fn();
		renderHeader({}, { onupdate });
		await openRename();
		await fireEvent.input(nameInput(), { target: { value: 'Other' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(screen.queryByRole('textbox')).toBeNull());
		expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: 'Other' });
		expect(onupdate).toHaveBeenCalledTimes(1);
	});

	it('closes the field from the Cancel button', async () => {
		renderHeader();
		await openRename();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(screen.queryByRole('textbox')).toBeNull();
	});

	it('keeps the field open when the save fails', async () => {
		updateDriveMock.mockRejectedValueOnce(new Error('nope'));
		const onupdate = vi.fn();
		renderHeader({}, { onupdate });
		await openRename();
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(updateDriveMock).toHaveBeenCalled());
		await waitFor(() =>
			expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(false)
		);
		expect(nameInput()).toBeTruthy();
		expect(onupdate).not.toHaveBeenCalled();
	});

	it('disables the input and both buttons while the save is in flight', async () => {
		let resolve!: () => void;
		updateDriveMock.mockReturnValueOnce(new Promise<void>((r) => (resolve = r)) as never);
		renderHeader();
		await openRename();
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(nameInput().disabled).toBe(true));
		expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: 'Cancel' }) as HTMLButtonElement).disabled).toBe(true);
		resolve();
		await waitFor(() => expect(screen.queryByRole('textbox')).toBeNull());
	});

	it('saves without an onupdate', async () => {
		renderHeader();
		await openRename();
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(screen.queryByRole('textbox')).toBeNull());
	});
});
