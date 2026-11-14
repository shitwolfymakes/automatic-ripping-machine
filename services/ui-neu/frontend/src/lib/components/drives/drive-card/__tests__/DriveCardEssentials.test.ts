// The drive card's essentials variant, rendered directly. The drives API is
// mocked the same way as in DriveCard.branches.test.ts.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import DriveCardEssentials from '../DriveCardEssentials.svelte';
import type { DriveView as Drive } from '$lib/types/api.gen';
import { createDrive } from '../../../__fixtures__/drive';

vi.mock('$lib/api/drives', () => ({
	updateDrive: vi.fn(() => Promise.resolve())
}));
import { updateDrive } from '$lib/api/drives';
const updateDriveMock = vi.mocked(updateDrive);

type Defaults = NonNullable<Parameters<typeof renderComponent>[1]>;

function renderEssentials(overrides: Partial<Drive> = {}, props: Record<string, unknown> = {}) {
	return renderComponent(DriveCardEssentials, {
		props: { drive: createDrive(overrides), ...props }
	} as Defaults);
}

function nameInput() {
	return screen.getByLabelText(/Friendly name/) as HTMLInputElement;
}

function uhdCheckbox() {
	return screen.getByRole('checkbox') as HTMLInputElement;
}

beforeEach(() => {
	updateDriveMock.mockReset();
	updateDriveMock.mockResolvedValue(undefined as never);
});

afterEach(() => {
	cleanup();
});

describe('DriveCardEssentials header', () => {
	it('shows the drive title', () => {
		renderEssentials();
		expect(screen.getByRole('heading', { level: 3 }).textContent).toBe('Main Drive');
	});

	it('shows the device path with the by-id name', () => {
		const { container } = renderEssentials();
		expect(container.querySelector('code')?.textContent).toBe('/dev/sr0  usb-VENDOR_MODEL_SN123-0:0');
	});

	it('shows the device path alone without a by-id name', () => {
		const { container } = renderEssentials({ by_id_name: null });
		expect(container.querySelector('code')?.textContent).toBe('/dev/sr0');
	});

	it('shows a connection chip when the drive has a connection', () => {
		renderEssentials({ connection: 'usb' });
		expect(screen.getByText('USB')).toBeTruthy();
	});

	it('shows no connection chip without a connection', () => {
		renderEssentials({ connection: null });
		expect(screen.queryByText('USB')).toBeNull();
		expect(screen.getByText('Unknown')).toBeTruthy();
	});
});

describe('DriveCardEssentials status strip', () => {
	it('shows the last error first', () => {
		renderEssentials({ last_error: 'boom', present: false, notice: 'n' });
		expect(screen.getByText('The ripper for this drive reported a problem.')).toBeTruthy();
		expect(screen.queryByText('Not connected')).toBeNull();
	});

	it('shows not connected when the drive is not present', () => {
		renderEssentials({ present: false });
		expect(screen.getByText('Not connected')).toBeTruthy();
	});

	it('shows not connected when the media is detached', () => {
		renderEssentials({ media_status: 'detached' });
		expect(screen.getByText('Not connected')).toBeTruthy();
	});

	it('shows ripping while a job is ripping', () => {
		renderEssentials({
			current_job: { status: 'ripping' } as Drive['current_job'],
			notice: 'n'
		});
		expect(screen.getByText('Ripping')).toBeTruthy();
	});

	it('shows a notice as a disc ejected strip', () => {
		renderEssentials({ notice: 'Rejected: already ripped' });
		expect(screen.getByText('Disc ejected')).toBeTruthy();
		expect(screen.getByText('Rejected: already ripped')).toBeTruthy();
	});

	it('shows ready when the drive is online', () => {
		renderEssentials();
		expect(screen.getByText('Ready')).toBeTruthy();
	});

	it('shows starting when the drive is not online', () => {
		renderEssentials({ status: 'offline' });
		expect(screen.getByText('Starting ripper...')).toBeTruthy();
	});
});

describe('DriveCardEssentials name field', () => {
	it('starts from the display name', () => {
		renderEssentials();
		expect(nameInput().value).toBe('Main Drive');
	});

	it('starts blank without a display name', () => {
		renderEssentials({ display_name: null });
		expect(nameInput().value).toBe('');
	});

	it('uses vendor and model as the placeholder', () => {
		renderEssentials();
		expect(nameInput().placeholder).toBe('VENDOR MODEL');
	});

	it('falls back to the example placeholder', () => {
		renderEssentials({ vendor: null, model: null });
		expect(nameInput().placeholder).toBe('Living room Blu-ray');
	});

	it('saves the trimmed name on blur and confirms it', async () => {
		renderEssentials();
		await fireEvent.input(nameInput(), { target: { value: '  Den  ' } });
		await fireEvent.blur(nameInput());
		await waitFor(() => expect(screen.getByText('Name saved')).toBeTruthy());
		expect(updateDriveMock).toHaveBeenCalledExactlyOnceWith('drv_1', { display_name: 'Den' });
	});

	it('saves on Enter', async () => {
		renderEssentials();
		await fireEvent.input(nameInput(), { target: { value: 'Den' } });
		await fireEvent.keyDown(nameInput(), { key: 'Enter' });
		await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: 'Den' }));
	});

	it('ignores other keys', async () => {
		renderEssentials();
		await fireEvent.input(nameInput(), { target: { value: 'Den' } });
		await fireEvent.keyDown(nameInput(), { key: 'a' });
		expect(updateDriveMock).not.toHaveBeenCalled();
	});

	it('sends null for a blank name', async () => {
		renderEssentials();
		await fireEvent.input(nameInput(), { target: { value: '   ' } });
		await fireEvent.blur(nameInput());
		await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: null }));
	});

	it('sends nothing when the name is unchanged', async () => {
		renderEssentials();
		await fireEvent.input(nameInput(), { target: { value: ' Main Drive ' } });
		await fireEvent.blur(nameInput());
		expect(updateDriveMock).not.toHaveBeenCalled();
	});

	it('sends nothing when a drive without a display name is left blank', async () => {
		renderEssentials({ display_name: null });
		await fireEvent.input(nameInput(), { target: { value: '  ' } });
		await fireEvent.blur(nameInput());
		expect(updateDriveMock).not.toHaveBeenCalled();
	});

	it('sends nothing on blur without typing', async () => {
		renderEssentials();
		await fireEvent.blur(nameInput());
		expect(updateDriveMock).not.toHaveBeenCalled();
	});

	it('shows the Error message when saving the name fails', async () => {
		updateDriveMock.mockRejectedValue(new Error('nope'));
		renderEssentials();
		await fireEvent.input(nameInput(), { target: { value: 'Den' } });
		await fireEvent.blur(nameInput());
		await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('nope'));
	});

	it('shows a generic message when saving the name fails with a non-Error', async () => {
		updateDriveMock.mockRejectedValue('bad');
		renderEssentials();
		await fireEvent.input(nameInput(), { target: { value: 'Den' } });
		await fireEvent.blur(nameInput());
		await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Saving the name failed'));
	});

	it('calls onupdate after the name is saved', async () => {
		const onupdate = vi.fn();
		renderEssentials({}, { onupdate });
		await fireEvent.input(nameInput(), { target: { value: 'Den' } });
		await fireEvent.blur(nameInput());
		await waitFor(() => expect(onupdate).toHaveBeenCalledOnce());
	});
});

describe('DriveCardEssentials 4K checkbox', () => {
	it('is unchecked when the drive is not UHD capable', () => {
		renderEssentials({ uhd_capable: false });
		expect(uhdCheckbox().checked).toBe(false);
	});

	it('is checked when the drive is UHD capable', () => {
		renderEssentials({ uhd_capable: true });
		expect(uhdCheckbox().checked).toBe(true);
	});

	it('saves a change and confirms it', async () => {
		renderEssentials();
		await fireEvent.click(uhdCheckbox());
		await waitFor(() => expect(screen.getByText('4K setting saved')).toBeTruthy());
		expect(updateDriveMock).toHaveBeenCalledExactlyOnceWith('drv_1', { uhd_capable: true });
	});

	it('calls onupdate after the 4K setting is saved', async () => {
		const onupdate = vi.fn();
		renderEssentials({}, { onupdate });
		await fireEvent.click(uhdCheckbox());
		await waitFor(() => expect(onupdate).toHaveBeenCalledOnce());
	});

	it('shows the Error message when saving the 4K setting fails', async () => {
		updateDriveMock.mockRejectedValue(new Error('denied'));
		renderEssentials();
		await fireEvent.click(uhdCheckbox());
		await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('denied'));
	});

	it('shows a generic message when saving the 4K setting fails with a non-Error', async () => {
		updateDriveMock.mockRejectedValue('bad');
		renderEssentials();
		await fireEvent.click(uhdCheckbox());
		await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Saving the 4K setting failed'));
	});

	it('replaces the saved message with a later error', async () => {
		renderEssentials();
		await fireEvent.click(uhdCheckbox());
		await waitFor(() => expect(screen.getByText('4K setting saved')).toBeTruthy());
		updateDriveMock.mockRejectedValue(new Error('denied'));
		await fireEvent.click(uhdCheckbox());
		await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('denied'));
		expect(screen.queryByText('4K setting saved')).toBeNull();
	});
});
