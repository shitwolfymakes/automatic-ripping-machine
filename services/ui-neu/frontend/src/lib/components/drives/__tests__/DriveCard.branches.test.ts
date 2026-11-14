// The drive card's settings panel, rename flow, essentials variant and failure
// paths that DriveCard.test.ts and the other tests rendering it leave out. The
// API modules are mocked the same way as in DriveCard.test.ts; the slide-over
// and the confirm dialog render for real.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/testing/render';
import DriveCard from '../DriveCard.svelte';
import type { DriveView as Drive, SessionView } from '$lib/types/api.gen';
import { createDrive } from '../../__fixtures__/drive';

vi.mock('$lib/api/drives', () => ({
	updateDrive: vi.fn(() => Promise.resolve()),
	unenrollDrive: vi.fn(() => Promise.resolve())
}));
vi.mock('$lib/api/jobs', () => ({
	triggerManual: vi.fn(() => Promise.resolve({ drive_id: 'drv_1', session_id: null }))
}));
import { triggerManual } from '$lib/api/jobs';
import { updateDrive, unenrollDrive } from '$lib/api/drives';
const triggerManualMock = vi.mocked(triggerManual);
const updateDriveMock = vi.mocked(updateDrive);
const unenrollDriveMock = vi.mocked(unenrollDrive);

type Defaults = NonNullable<Parameters<typeof renderComponent>[1]>;

function renderDrive(overrides: Partial<Drive> = {}, props: Record<string, unknown> = {}) {
	return renderComponent(DriveCard, {
		props: { drive: createDrive(overrides), sessions: [], ...props }
	} as Defaults);
}

function renderEssentials(overrides: Partial<Drive> = {}, props: Record<string, unknown> = {}) {
	return renderDrive(overrides, { variant: 'essentials', ...props });
}

async function openSettings() {
	await fireEvent.click(screen.getByTitle('Drive settings'));
}

function input(label: RegExp): HTMLInputElement {
	return screen.getByLabelText(label) as HTMLInputElement;
}

async function typeInto(el: HTMLInputElement, value: string) {
	await fireEvent.input(el, { target: { value } });
}

async function typeAndBlur(el: HTMLInputElement, value: string) {
	await typeInto(el, value);
	await fireEvent.blur(el);
}

const SESSIONS = [
	{ id: 'ses_1', name: 'Movies', is_builtin: false },
	{ id: 'ses_2', name: 'Stock', is_builtin: true }
] as SessionView[];

describe('DriveCard branches', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('prescan settings', () => {
		const FIELDS = [
			{ label: /Pre-scan Cache/, key: 'prescan_cache_mb', min: 1, max: 1024 },
			{ label: /Pre-scan Timeout/, key: 'prescan_timeout', min: 30, max: 3600 },
			{ label: /Pre-scan Retries/, key: 'prescan_retries', min: 1, max: 10 },
			{ label: /Enum Timeout/, key: 'disc_enum_timeout', min: 10, max: 600 }
		] as const;

		it('fills every prescan input from the drive while the panel is closed', async () => {
			renderDrive({ prescan_cache_mb: 64, prescan_timeout: 600, prescan_retries: 3, disc_enum_timeout: 120 });
			await openSettings();
			expect(FIELDS.map((f) => input(f.label).value)).toEqual(['64', '600', '3', '120']);
		});

		describe.each(FIELDS)('$key', ({ label, key, min, max }) => {
			it('saves the typed value', async () => {
				const onupdate = vi.fn();
				renderDrive({}, { onupdate });
				await openSettings();
				await typeAndBlur(input(label), String(min));
				expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { [key]: min });
				await waitFor(() => expect(onupdate).toHaveBeenCalled());
			});

			it('sends null when the input is emptied', async () => {
				renderDrive({ [key]: max });
				await openSettings();
				await typeAndBlur(input(label), '');
				expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { [key]: null });
			});

			it('sends nothing for a value below the minimum', async () => {
				renderDrive();
				await openSettings();
				await typeAndBlur(input(label), String(min - 1));
				expect(updateDriveMock).not.toHaveBeenCalled();
			});

			it('sends nothing for a value above the maximum', async () => {
				renderDrive();
				await openSettings();
				await typeAndBlur(input(label), String(max + 1));
				expect(updateDriveMock).not.toHaveBeenCalled();
			});

			it('stores null and clears the input when the value equals the global default', async () => {
				renderDrive({ [key]: max }, { globalDefaults: { [key]: min } });
				await openSettings();
				const el = input(label);
				expect(el.placeholder).toBe(String(min));
				await typeAndBlur(el, String(min));
				expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { [key]: null });
				expect(el.value).toBe('');
			});

			it('sends nothing when the value is unchanged', async () => {
				renderDrive({ [key]: max });
				await openSettings();
				await fireEvent.blur(input(label));
				expect(updateDriveMock).not.toHaveBeenCalled();
			});

			it('sends nothing when an empty input already means no override', async () => {
				renderDrive();
				await openSettings();
				await fireEvent.blur(input(label));
				expect(updateDriveMock).not.toHaveBeenCalled();
			});

			it('puts the server value back when the save fails', async () => {
				updateDriveMock.mockRejectedValueOnce(new Error('nope'));
				renderDrive({ [key]: max });
				await openSettings();
				const el = input(label);
				await typeAndBlur(el, String(min));
				await waitFor(() => expect(el.value).toBe(String(max)));
			});

			it('empties the input when a save fails and the drive had no override', async () => {
				updateDriveMock.mockRejectedValueOnce(new Error('nope'));
				renderDrive();
				await openSettings();
				const el = input(label);
				await typeAndBlur(el, String(min));
				await waitFor(() => expect(el.value).toBe(''));
			});

			it('saves when Enter blurs the focused input', async () => {
				renderDrive();
				await openSettings();
				const el = input(label);
				el.focus();
				await typeInto(el, String(min));
				await fireEvent.keyDown(el, { key: 'Enter' });
				await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { [key]: min }));
			});

			it('ignores other keys', async () => {
				renderDrive();
				await openSettings();
				const el = input(label);
				await typeInto(el, String(min));
				await fireEvent.keyDown(el, { key: 'a' });
				expect(updateDriveMock).not.toHaveBeenCalled();
				expect(el.value).toBe(String(min));
			});

			it('Escape drops the edit, closes the panel and shows the server value on reopening', async () => {
				renderDrive({ [key]: max });
				await openSettings();
				const el = input(label);
				await typeInto(el, String(min));
				await fireEvent.keyDown(el, { key: 'Escape' });
				await waitFor(() => expect(screen.getByTitle('Drive settings')).toHaveAttribute('aria-pressed', 'false'));
				await openSettings();
				expect(input(label).value).toBe(String(max));
				expect(updateDriveMock).not.toHaveBeenCalled();
			});

			it('Escape on a drive with no override leaves the input empty on reopening', async () => {
				renderDrive();
				await openSettings();
				const el = input(label);
				await typeInto(el, String(min));
				await fireEvent.keyDown(el, { key: 'Escape' });
				await waitFor(() => expect(screen.getByTitle('Drive settings')).toHaveAttribute('aria-pressed', 'false'));
				await openSettings();
				expect(input(label).value).toBe('');
			});
		});
	});

	describe('rip speed', () => {
		it('fills the input from the drive while the panel is closed', async () => {
			renderDrive({ rip_speed: 4 });
			await openSettings();
			expect(input(/Rip Speed/).value).toBe('4');
		});

		it('sends nothing when the speed is unchanged', async () => {
			renderDrive({ rip_speed: 4 });
			await openSettings();
			await fireEvent.blur(input(/Rip Speed/));
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('sends nothing when an empty input already means max speed', async () => {
			renderDrive();
			await openSettings();
			await fireEvent.blur(input(/Rip Speed/));
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('sends null when the input is emptied', async () => {
			renderDrive({ rip_speed: 4 });
			await openSettings();
			await typeAndBlur(input(/Rip Speed/), '');
			expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { rip_speed: null });
		});

		it.each(['0', '100'])('sends nothing for %s, which is out of range', async (value) => {
			renderDrive();
			await openSettings();
			await typeAndBlur(input(/Rip Speed/), value);
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('puts the server speed back when the save fails', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('nope'));
			renderDrive({ rip_speed: 4 });
			await openSettings();
			const el = input(/Rip Speed/);
			await typeAndBlur(el, '8');
			await waitFor(() => expect(el.value).toBe('4'));
		});

		it('empties the input when a save fails and the drive had no speed', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('nope'));
			renderDrive();
			await openSettings();
			const el = input(/Rip Speed/);
			await typeAndBlur(el, '8');
			await waitFor(() => expect(el.value).toBe(''));
		});

		it('saves when Enter blurs the focused input', async () => {
			renderDrive();
			await openSettings();
			const el = input(/Rip Speed/);
			el.focus();
			await typeInto(el, '8');
			await fireEvent.keyDown(el, { key: 'Enter' });
			await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { rip_speed: 8 }));
		});

		it('ignores other keys', async () => {
			renderDrive();
			await openSettings();
			const el = input(/Rip Speed/);
			await typeInto(el, '8');
			await fireEvent.keyDown(el, { key: 'a' });
			expect(updateDriveMock).not.toHaveBeenCalled();
			expect(el.value).toBe('8');
		});

		it.each([
			['a saved speed', 4, '4'],
			['no saved speed', null, '']
		])('Escape closes the panel and shows %s on reopening', async (_label, saved, shown) => {
			renderDrive({ rip_speed: saved });
			await openSettings();
			const el = input(/Rip Speed/);
			await typeInto(el, '8');
			await fireEvent.keyDown(el, { key: 'Escape' });
			await waitFor(() => expect(screen.getByTitle('Drive settings')).toHaveAttribute('aria-pressed', 'false'));
			await openSettings();
			expect(input(/Rip Speed/).value).toBe(shown);
			expect(updateDriveMock).not.toHaveBeenCalled();
		});
	});

	describe('settings panel', () => {
		it('closes from the slide-over and releases the gear button', async () => {
			renderDrive();
			await openSettings();
			expect(screen.getByTitle('Drive settings')).toHaveAttribute('aria-pressed', 'true');
			await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
			await waitFor(() => expect(screen.getByTitle('Drive settings')).toHaveAttribute('aria-pressed', 'false'));
		});

		it.each([
			['the device path without a name', { display_name: null }, '/dev/sr0 settings'],
			['the word Drive without a name or a path', { display_name: null, device_path: '' }, 'Drive settings']
		] as [string, Partial<Drive>, string][])('titles the panel with %s', async (_label, overrides, title) => {
			renderDrive(overrides);
			await openSettings();
			expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
		});

		it('flags built-in sessions in the default session picker', async () => {
			renderDrive({}, { sessions: SESSIONS });
			await openSettings();
			const options = Array.from((screen.getByTestId('drive-default-session') as HTMLSelectElement).options);
			expect(options.map((o) => o.textContent?.trim())).toEqual(['- none -', 'Movies', 'Stock (built-in)']);
		});

		it('saves a chosen default session and clears it with null', async () => {
			renderDrive({ default_session_id: 'ses_1' }, { sessions: SESSIONS });
			await openSettings();
			const select = screen.getByTestId('drive-default-session');
			await fireEvent.change(select, { target: { value: 'ses_2' } });
			expect(updateDriveMock).toHaveBeenLastCalledWith('drv_1', { default_session_id: 'ses_2' });
			await fireEvent.change(select, { target: { value: '' } });
			expect(updateDriveMock).toHaveBeenLastCalledWith('drv_1', { default_session_id: null });
		});

		it('shows the Error message when saving the default session fails', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('session gone'));
			renderDrive({}, { sessions: SESSIONS });
			await openSettings();
			await fireEvent.change(screen.getByTestId('drive-default-session'), { target: { value: 'ses_1' } });
			await waitFor(() => expect(screen.getByTestId('drive-default-session-error')).toHaveTextContent('session gone'));
		});

		it('shows a generic message when saving the default session fails with a non-Error', async () => {
			updateDriveMock.mockRejectedValueOnce('boom');
			renderDrive({}, { sessions: SESSIONS });
			await openSettings();
			await fireEvent.change(screen.getByTestId('drive-default-session'), { target: { value: 'ses_1' } });
			await waitFor(() =>
				expect(screen.getByTestId('drive-default-session-error')).toHaveTextContent('Failed to set default session')
			);
		});
	});

	describe('manual rip', () => {
		it('shows a generic message when the trigger fails with a non-Error', async () => {
			triggerManualMock.mockRejectedValueOnce('boom');
			renderDrive();
			await fireEvent.click(screen.getByTestId('drive-start-rip'));
			await waitFor(() => expect(screen.getByTestId('drive-manual-error')).toHaveTextContent('Manual rip failed'));
		});

		it('ignores a second click that lands while the first trigger is in flight', async () => {
			let release: () => void = () => {};
			triggerManualMock.mockImplementationOnce(
				() =>
					new Promise((resolve) => {
						release = () => resolve({ drive_id: 'drv_1', session_id: null });
					})
			);
			const onupdate = vi.fn();
			renderDrive({}, { onupdate });
			const button = screen.getByTestId('drive-start-rip');
			button.click();
			button.click();
			expect(triggerManualMock).toHaveBeenCalledTimes(1);
			release();
			await waitFor(() => expect(onupdate).toHaveBeenCalledTimes(1));
		});
	});

	describe('unenroll', () => {
		it.each([
			['the model when the name is blank', { display_name: '' }, 'Unenroll MODEL?'],
			['the hostname when the name and model are blank', { display_name: null, model: null }, 'Unenroll arm-host?']
		] as [string, Partial<Drive>, string][])('names the drive by %s', async (_label, overrides, title) => {
			renderDrive(overrides);
			await fireEvent.click(screen.getByTestId('drive-unenroll'));
			expect(await screen.findByRole('dialog')).toHaveTextContent(title);
		});

		it('shows a generic message when unenrolling fails with a non-Error', async () => {
			unenrollDriveMock.mockRejectedValueOnce('boom');
			renderDrive();
			await fireEvent.click(screen.getByTestId('drive-unenroll'));
			await fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Unenroll' }));
			await waitFor(() => expect(screen.getByTestId('drive-unenroll-error')).toHaveTextContent('Unenroll failed'));
		});
	});

	describe('rename', () => {
		it('Save sends the new name and closes edit mode', async () => {
			const onupdate = vi.fn();
			renderDrive({}, { onupdate });
			await fireEvent.click(screen.getByText('Rename'));
			await typeInto(screen.getByDisplayValue('Main Drive') as HTMLInputElement, 'Den Drive');
			await fireEvent.click(screen.getByText('Save'));
			expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: 'Den Drive' });
			await waitFor(() => expect(screen.getByText('Rename')).toBeInTheDocument());
			expect(onupdate).toHaveBeenCalled();
		});

		it('starts from an empty field when the drive has no name', async () => {
			renderDrive({ display_name: null });
			await fireEvent.click(screen.getByText('Rename'));
			expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('');
		});

		it('Enter in the field saves', async () => {
			renderDrive();
			await fireEvent.click(screen.getByText('Rename'));
			const field = screen.getByDisplayValue('Main Drive') as HTMLInputElement;
			await typeInto(field, 'Den Drive');
			await fireEvent.keyDown(field, { key: 'Enter' });
			await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: 'Den Drive' }));
		});

		it('Escape in the field cancels without a request', async () => {
			renderDrive();
			await fireEvent.click(screen.getByText('Rename'));
			await fireEvent.keyDown(screen.getByDisplayValue('Main Drive'), { key: 'Escape' });
			expect(screen.getByText('Rename')).toBeInTheDocument();
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('other keys leave edit mode open', async () => {
			renderDrive();
			await fireEvent.click(screen.getByText('Rename'));
			await fireEvent.keyDown(screen.getByDisplayValue('Main Drive'), { key: 'a' });
			expect(screen.getByText('Save')).toBeInTheDocument();
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('keeps edit mode open when Save fails', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('nope'));
			const onupdate = vi.fn();
			renderDrive({}, { onupdate });
			await fireEvent.click(screen.getByText('Rename'));
			await fireEvent.click(screen.getByText('Save'));
			await waitFor(() => expect(updateDriveMock).toHaveBeenCalled());
			await waitFor(() => expect(screen.getByText('Save')).not.toBeDisabled());
			expect(screen.queryByText('Rename')).not.toBeInTheDocument();
			expect(onupdate).not.toHaveBeenCalled();
		});
	});

	describe('4K and rip mode', () => {
		it('the 4K checkbox sends the flipped flag', async () => {
			const onupdate = vi.fn();
			renderDrive({}, { onupdate });
			await fireEvent.click(screen.getByRole('checkbox'));
			expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { uhd_capable: true });
			await waitFor(() => expect(onupdate).toHaveBeenCalled());
		});

		it('ignores a failed 4K save and re-enables the checkbox', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('nope'));
			const onupdate = vi.fn();
			renderDrive({}, { onupdate });
			await fireEvent.click(screen.getByRole('checkbox'));
			await waitFor(() => expect(screen.getByRole('checkbox')).not.toBeDisabled());
			expect(onupdate).not.toHaveBeenCalled();
		});

		it('sends the chosen mode and null for the default', async () => {
			renderDrive({ drive_mode: 'manual' });
			const select = screen.getByLabelText('Rip mode');
			await fireEvent.change(select, { target: { value: 'auto' } });
			expect(updateDriveMock).toHaveBeenLastCalledWith('drv_1', { drive_mode: 'auto' });
			await fireEvent.change(select, { target: { value: '' } });
			expect(updateDriveMock).toHaveBeenLastCalledWith('drv_1', { drive_mode: null });
		});

		it('ignores a failed mode save and re-enables the select', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('nope'));
			const onupdate = vi.fn();
			renderDrive({}, { onupdate });
			await fireEvent.change(screen.getByLabelText('Rip mode'), { target: { value: 'manual' } });
			await waitFor(() => expect(screen.getByLabelText('Rip mode')).not.toBeDisabled());
			expect(onupdate).not.toHaveBeenCalled();
		});
	});

	describe('full card details', () => {
		it('shows the speed chip and the prescan override count', () => {
			renderDrive({ rip_speed: 4, disc_enum_timeout: 120 });
			expect(screen.getByText('4x speed')).toBeInTheDocument();
			expect(screen.getByText('1 custom')).toBeInTheDocument();
		});

		// The chips' intro is local to their own block, so it plays only when the
		// chip appears while the chip row is already on screen.
		it('reveals the speed chip when a polled update adds a speed', async () => {
			const { rerender } = renderDrive({ prescan_retries: 3 });
			expect(screen.queryByText(/x speed/)).not.toBeInTheDocument();
			await rerender({ drive: createDrive({ prescan_retries: 3, rip_speed: 4 }) });
			expect(await screen.findByText('4x speed')).toBeInTheDocument();
		});

		it('reveals the prescan chip when a polled update adds an override', async () => {
			const { rerender } = renderDrive({ rip_speed: 4 });
			expect(screen.queryByText(/custom/)).not.toBeInTheDocument();
			await rerender({ drive: createDrive({ rip_speed: 4, prescan_cache_mb: 64 }) });
			expect(await screen.findByText('1 custom')).toBeInTheDocument();
		});

		it('swaps the card for the skeleton when the drive goes away', async () => {
			const { rerender } = renderDrive();
			await rerender({ drive: undefined });
			expect(screen.queryByText('Main Drive')).not.toBeInTheDocument();
		});

		it('relabels a session in both pickers when it is renamed under the same id', async () => {
			const { rerender } = renderDrive({}, { sessions: SESSIONS });
			await openSettings();
			await rerender({ sessions: [{ ...SESSIONS[0], name: 'Films' }, SESSIONS[1]] });
			const picker = screen.getByTestId('drive-session-select') as HTMLSelectElement;
			const defaults = screen.getByTestId('drive-default-session') as HTMLSelectElement;
			await waitFor(() => expect(picker.options[1].textContent?.trim()).toBe('Films'));
			expect(defaults.options[1].textContent?.trim()).toBe('Films');
			expect(picker.options[1].value).toBe('ses_1');
		});

		it('lists a session with no id or name as an empty option', async () => {
			renderDrive({}, { sessions: [{ id: null, name: null, is_builtin: false } as unknown as SessionView] });
			await openSettings();
			const picker = screen.getByTestId('drive-session-select') as HTMLSelectElement;
			expect(picker.options[1].textContent?.trim()).toBe('');
			const defaults = screen.getByTestId('drive-default-session') as HTMLSelectElement;
			expect(defaults.options[1].textContent?.trim()).toBe('');
		});

		it('shows the prescan chip without a speed chip', () => {
			renderDrive({ prescan_retries: 3 });
			expect(screen.queryByText(/x speed/)).not.toBeInTheDocument();
			expect(screen.getByText('1 custom')).toBeInTheDocument();
		});

		it('shows only the speed chip when no prescan value is set', () => {
			renderDrive({ rip_speed: 2 });
			expect(screen.getByText('2x speed')).toBeInTheDocument();
			expect(screen.queryByText(/custom/)).not.toBeInTheDocument();
		});

		it('writes the media status with a space instead of the underscore', () => {
			renderDrive({ media_status: 'not_ready' });
			expect(screen.getByText('not ready')).toBeInTheDocument();
		});

		it('hides the Host row without a hostname', () => {
			renderDrive({ hostname: '' });
			expect(screen.queryByText('Host:')).not.toBeInTheDocument();
		});

		it('links the current rip to its job page', () => {
			renderDrive({ current_job: { id: 'job_9', title: 'Some Movie', status: 'ripping' } });
			expect(screen.getByRole('link', { name: 'Some Movie' })).toHaveAttribute('href', '/jobs/job_9');
		});

		it('falls back to Active Job when the current rip has no title', () => {
			renderDrive({ current_job: { id: 'job_9', title: '', status: 'ripping' } });
			expect(screen.getByRole('link', { name: 'Active Job' })).toHaveAttribute('href', '/jobs/job_9');
		});

		it('flags built-in sessions in the manual rip picker', () => {
			renderDrive({}, { sessions: SESSIONS });
			const options = Array.from((screen.getByTestId('drive-session-select') as HTMLSelectElement).options);
			expect(options.map((o) => o.textContent?.trim())).toEqual(['- none -', 'Movies', 'Stock (built-in)']);
		});
	});

	describe('essentials variant', () => {
		it('shows the connection chip when the drive reports one', () => {
			renderEssentials({ connection: 'usb' });
			expect(screen.getByText('USB')).toBeInTheDocument();
		});

		it('shows no connection chip when the drive reports none', () => {
			renderEssentials({ connection: null });
			expect(screen.queryByText('USB')).not.toBeInTheDocument();
		});

		it('leaves the by-id name out of the path line when there is none', () => {
			renderEssentials({ by_id_name: null });
			expect(screen.getByText('/dev/sr0', { selector: 'code' }).textContent).toBe('/dev/sr0');
		});

		it('shows the ripper error first', () => {
			renderEssentials({ last_error: 'ripper crashed', status: 'error' });
			expect(screen.getByText('The ripper for this drive reported a problem.')).toBeInTheDocument();
			expect(screen.getByText('ripper crashed')).toBeInTheDocument();
		});

		it.each([
			['an absent drive', { present: false }],
			['a detached disc status', { media_status: 'detached' }]
		] as [string, Partial<Drive>][])('shows Not connected for %s', (_label, overrides) => {
			renderEssentials(overrides);
			expect(screen.getByText('Not connected')).toBeInTheDocument();
		});

		it('shows Ripping while a job rips', () => {
			renderEssentials({ current_job: { id: 'job_1', title: 'X', status: 'ripping' } });
			expect(screen.getByText('Ripping')).toBeInTheDocument();
		});

		it('shows the ejected-disc notice', () => {
			renderEssentials({ notice: 'Disc was already ripped' });
			expect(screen.getByText('Disc ejected')).toBeInTheDocument();
			expect(screen.getByText('Disc was already ripped')).toBeInTheDocument();
		});

		it('shows Ready for an online drive', () => {
			renderEssentials();
			expect(screen.getByText('Ready')).toBeInTheDocument();
		});

		it('shows Starting ripper for a drive that is not online yet', () => {
			renderEssentials({ status: 'offline', present: true });
			expect(screen.getByText('Starting ripper...')).toBeInTheDocument();
		});

		it.each([
			['the vendor and model', {}, 'VENDOR MODEL'],
			['an example name', { vendor: null, model: null }, 'Living room Blu-ray']
		] as [string, Partial<Drive>, string][])('suggests %s as the name placeholder', (_label, overrides, expected) => {
			renderEssentials({ display_name: null, ...overrides });
			expect(input(/Friendly name/).placeholder).toBe(expected);
		});

		it('saves a changed name on blur and says so', async () => {
			const onupdate = vi.fn();
			renderEssentials({}, { onupdate });
			await typeAndBlur(input(/Friendly name/), 'Den Drive');
			expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: 'Den Drive' });
			expect(await screen.findByText('Name saved')).toBeInTheDocument();
			expect(onupdate).toHaveBeenCalled();
		});

		it('saves a changed name on Enter', async () => {
			renderEssentials();
			const field = input(/Friendly name/);
			await typeInto(field, 'Den Drive');
			await fireEvent.keyDown(field, { key: 'Enter' });
			await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: 'Den Drive' }));
		});

		it('ignores other keys in the name field', async () => {
			renderEssentials();
			const field = input(/Friendly name/);
			await typeInto(field, 'Den Drive');
			await fireEvent.keyDown(field, { key: 'a' });
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('sends nothing when the name was never edited', async () => {
			renderEssentials();
			await fireEvent.blur(input(/Friendly name/));
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('sends nothing when the name is unchanged once trimmed', async () => {
			renderEssentials();
			await typeAndBlur(input(/Friendly name/), '  Main Drive  ');
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('sends null for a blank name', async () => {
			renderEssentials();
			await typeAndBlur(input(/Friendly name/), '   ');
			expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: null });
		});

		it('sends a name on a drive that had none', async () => {
			renderEssentials({ display_name: null });
			await typeAndBlur(input(/Friendly name/), 'Den Drive');
			expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { display_name: 'Den Drive' });
		});

		it('shows the Error message when saving the name fails', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('name taken'));
			renderEssentials();
			await typeAndBlur(input(/Friendly name/), 'Den Drive');
			expect(await screen.findByRole('alert')).toHaveTextContent('name taken');
		});

		it('shows a generic message when saving the name fails with a non-Error', async () => {
			updateDriveMock.mockRejectedValueOnce('boom');
			renderEssentials();
			await typeAndBlur(input(/Friendly name/), 'Den Drive');
			expect(await screen.findByRole('alert')).toHaveTextContent('Saving the name failed');
		});

		it('saves the 4K setting and says so', async () => {
			const onupdate = vi.fn();
			renderEssentials({}, { onupdate });
			await fireEvent.click(screen.getByRole('checkbox'));
			expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { uhd_capable: true });
			expect(await screen.findByText('4K setting saved')).toBeInTheDocument();
			expect(onupdate).toHaveBeenCalled();
		});

		it('shows the Error message when saving the 4K setting fails', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('drive busy'));
			renderEssentials();
			await fireEvent.click(screen.getByRole('checkbox'));
			expect(await screen.findByRole('alert')).toHaveTextContent('drive busy');
		});

		it('shows a generic message when saving the 4K setting fails with a non-Error', async () => {
			updateDriveMock.mockRejectedValueOnce('boom');
			renderEssentials();
			await fireEvent.click(screen.getByRole('checkbox'));
			expect(await screen.findByRole('alert')).toHaveTextContent('Saving the 4K setting failed');
		});
	});
});
