// The drive card's settings slide-over, rendered directly. The drives API is
// mocked the same way as in DriveCard.branches.test.ts; the slide-over renders
// for real.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import DriveSettingsPanel from '../DriveSettingsPanel.svelte';
import type { DriveView as Drive, SessionView } from '$lib/types/api.gen';
import { createDrive } from '../../../__fixtures__/drive';

vi.mock('$lib/api/drives', () => ({
	updateDrive: vi.fn(() => Promise.resolve())
}));
import { updateDrive } from '$lib/api/drives';
const updateDriveMock = vi.mocked(updateDrive);

type Defaults = NonNullable<Parameters<typeof renderComponent>[1]>;

const SESSIONS = [
	{ id: 'ses_1', name: 'Movies', is_builtin: false },
	{ id: 'ses_2', name: 'Stock', is_builtin: true }
] as SessionView[];

const FIELDS = [
	{
		label: /Pre-scan Cache/,
		key: 'prescan_cache_mb',
		min: 1,
		max: 1024,
		unit: '(MB)',
		tooltip: 'Community recommends 64-128 for scratched or damaged discs'
	},
	{
		label: /Pre-scan Timeout/,
		key: 'prescan_timeout',
		min: 30,
		max: 3600,
		unit: '(s)',
		tooltip: 'Community recommends 600 for slow or damaged DVD/BD media'
	},
	{
		label: /Pre-scan Retries/,
		key: 'prescan_retries',
		min: 1,
		max: 10,
		unit: null,
		tooltip: 'Community recommends 3-5 retries for problematic drives'
	},
	{
		label: /Enum Timeout/,
		key: 'disc_enum_timeout',
		min: 10,
		max: 600,
		unit: '(s)',
		tooltip: 'Community recommends 120 for drives that are slow to spin up'
	}
] as const;

function renderPanel(overrides: Partial<Drive> = {}, props: Record<string, unknown> = {}) {
	return renderComponent(DriveSettingsPanel, {
		props: { drive: createDrive(overrides), open: true, sessions: SESSIONS, ...props }
	} as Defaults);
}

// The card mounts the panel closed and opens it later, which is when the
// inputs hold the drive's values (they sync while the panel is closed).
async function renderSyncedPanel(overrides: Partial<Drive> = {}, props: Record<string, unknown> = {}) {
	const result = renderPanel(overrides, { ...props, open: false });
	await result.rerender({ open: true });
	return result;
}

function input(label: RegExp): HTMLInputElement {
	return screen.getByLabelText(label) as HTMLInputElement;
}

function sessionSelect(): HTMLSelectElement {
	return screen.getByTestId('drive-default-session') as HTMLSelectElement;
}

async function typeInto(el: HTMLInputElement, value: string) {
	await fireEvent.input(el, { target: { value } });
}

async function typeAndBlur(el: HTMLInputElement, value: string) {
	await typeInto(el, value);
	await fireEvent.blur(el);
}

async function expectPanelClosed() {
	await waitFor(() => expect(screen.queryByTestId('drive-default-session')).toBeNull());
}

function deferredUpdate() {
	let resolve: () => void = () => {};
	updateDriveMock.mockReturnValueOnce(
		new Promise<void>((r) => {
			resolve = r;
		}) as never
	);
	return () => resolve();
}

beforeEach(() => {
	updateDriveMock.mockReset();
	updateDriveMock.mockResolvedValue(undefined as never);
});

afterEach(() => {
	cleanup();
});

describe('DriveSettingsPanel panel', () => {
	it('titles the panel with the display name', () => {
		renderPanel({ display_name: 'Living Room' });
		expect(screen.getByText('Living Room settings')).toBeTruthy();
	});

	it('titles the panel with the device path when there is no display name', () => {
		renderPanel({ display_name: null, device_path: '/dev/sr7' });
		expect(screen.getByText('/dev/sr7 settings')).toBeTruthy();
	});

	it('titles the panel Drive when there is no display name or device path', () => {
		renderPanel({ display_name: null, device_path: '' });
		expect(screen.getByText('Drive settings')).toBeTruthy();
	});

	it('renders nothing while closed', () => {
		renderPanel({}, { open: false });
		expect(screen.queryByTestId('drive-default-session')).toBeNull();
		expect(screen.queryByText('Main Drive settings')).toBeNull();
	});
});

describe('DriveSettingsPanel default session', () => {
	it('shows the drive default and lists the sessions with a built-in suffix', () => {
		renderPanel({ default_session_id: 'ses_2' });
		expect(sessionSelect().value).toBe('ses_2');
		expect(Array.from(sessionSelect().options).map((o) => o.textContent)).toEqual([
			'- none -',
			'Movies',
			'Stock (built-in)'
		]);
	});

	it('keeps the default and shows new names when the sessions re-render with the same ids', async () => {
		const { rerender } = renderPanel({ default_session_id: 'ses_2' });
		await rerender({ sessions: SESSIONS.map((s, i) => ({ ...s, name: i === 0 ? 'Films' : s.name })) });
		expect(Array.from(sessionSelect().options).map((o) => o.textContent)).toEqual([
			'- none -',
			'Films',
			'Stock (built-in)'
		]);
		expect(sessionSelect().value).toBe('ses_2');
	});

	it('shows none when the drive has no default session', () => {
		renderPanel();
		expect(sessionSelect().value).toBe('');
	});

	it('saves the chosen session id', async () => {
		const onupdate = vi.fn();
		renderPanel({}, { onupdate });
		await fireEvent.change(sessionSelect(), { target: { value: 'ses_1' } });
		await waitFor(() => expect(onupdate).toHaveBeenCalledTimes(1));
		expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { default_session_id: 'ses_1' });
	});

	it('sends null when none is chosen', async () => {
		renderPanel({ default_session_id: 'ses_1' });
		await fireEvent.change(sessionSelect(), { target: { value: '' } });
		await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { default_session_id: null }));
	});

	it('shows the error message when the save fails with an Error', async () => {
		updateDriveMock.mockRejectedValueOnce(new Error('Session is gone'));
		renderPanel();
		await fireEvent.change(sessionSelect(), { target: { value: 'ses_1' } });
		expect((await screen.findByTestId('drive-default-session-error')).textContent).toBe('Session is gone');
	});

	it('shows a fallback message when the save fails with a non-Error', async () => {
		updateDriveMock.mockRejectedValueOnce('nope');
		renderPanel();
		await fireEvent.change(sessionSelect(), { target: { value: 'ses_1' } });
		expect((await screen.findByTestId('drive-default-session-error')).textContent).toBe(
			'Failed to set default session'
		);
	});

	it('clears an earlier error when the next save starts', async () => {
		updateDriveMock.mockRejectedValueOnce(new Error('boom'));
		renderPanel();
		await fireEvent.change(sessionSelect(), { target: { value: 'ses_1' } });
		await screen.findByTestId('drive-default-session-error');
		await fireEvent.change(sessionSelect(), { target: { value: 'ses_2' } });
		await waitFor(() => expect(screen.queryByTestId('drive-default-session-error')).toBeNull());
	});

	it('disables the select while the save is in flight', async () => {
		const finish = deferredUpdate();
		renderPanel();
		await fireEvent.change(sessionSelect(), { target: { value: 'ses_1' } });
		await waitFor(() => expect(sessionSelect().disabled).toBe(true));
		finish();
		await waitFor(() => expect(sessionSelect().disabled).toBe(false));
	});
});

describe('DriveSettingsPanel rip speed', () => {
	const speed = () => input(/Rip Speed/);

	it('shows the drive rip speed', async () => {
		await renderSyncedPanel({ rip_speed: 4 });
		expect(speed().value).toBe('4');
	});

	it('is blank when the drive has no rip speed', () => {
		renderPanel();
		expect(speed().value).toBe('');
	});

	it('saves a changed speed on blur', async () => {
		const onupdate = vi.fn();
		renderPanel({ rip_speed: 4 }, { onupdate });
		await typeAndBlur(speed(), '8');
		await waitFor(() => expect(onupdate).toHaveBeenCalledTimes(1));
		expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { rip_speed: 8 });
	});

	it('sends null when the speed is cleared', async () => {
		renderPanel({ rip_speed: 4 });
		await typeAndBlur(speed(), '');
		await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { rip_speed: null }));
	});

	it('sends nothing when the speed is unchanged', async () => {
		await renderSyncedPanel({ rip_speed: 4 });
		await fireEvent.blur(speed());
		expect(updateDriveMock).not.toHaveBeenCalled();
	});

	it('sends nothing when the speed is out of range', async () => {
		renderPanel({ rip_speed: 4 });
		await typeAndBlur(speed(), '100');
		expect(updateDriveMock).not.toHaveBeenCalled();
	});

	it('reverts the input when the save fails', async () => {
		updateDriveMock.mockRejectedValueOnce(new Error('boom'));
		renderPanel({ rip_speed: 4 });
		await typeAndBlur(speed(), '8');
		await waitFor(() => expect(speed().value).toBe('4'));
	});

	it('blurs the input on Enter', async () => {
		renderPanel({ rip_speed: 4 });
		speed().focus();
		await typeInto(speed(), '8');
		await fireEvent.keyDown(speed(), { key: 'Enter' });
		expect(document.activeElement).not.toBe(speed());
		await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { rip_speed: 8 }));
	});

	it('ignores other keys', async () => {
		renderPanel({ rip_speed: 4 });
		await typeInto(speed(), '8');
		await fireEvent.keyDown(speed(), { key: 'a' });
		expect(speed().value).toBe('8');
		expect(screen.getByTestId('drive-default-session')).toBeTruthy();
	});

	it('reverts and closes the panel on Escape', async () => {
		renderPanel({ rip_speed: 4 });
		await typeInto(speed(), '8');
		await fireEvent.keyDown(speed(), { key: 'Escape' });
		await expectPanelClosed();
		expect(updateDriveMock).not.toHaveBeenCalled();
	});

	it('disables the input while saving', async () => {
		const finish = deferredUpdate();
		renderPanel({ rip_speed: 4 });
		await typeAndBlur(speed(), '8');
		await waitFor(() => expect(speed().disabled).toBe(true));
		finish();
		await waitFor(() => expect(speed().disabled).toBe(false));
	});
});

describe('DriveSettingsPanel prescan fields', () => {
	it('shows each label, unit and tooltip', () => {
		renderPanel();
		for (const f of FIELDS) {
			const label = input(f.label).closest('div')!.querySelector('label')!;
			const unit = label.querySelector('span');
			if (f.unit) expect(unit?.textContent).toBe(f.unit);
			else expect(unit).toBeNull();
			expect(screen.getByText(f.tooltip)).toBeTruthy();
		}
	});

	it('limits each input to its range', () => {
		renderPanel();
		for (const f of FIELDS) {
			expect(input(f.label).min).toBe(String(f.min));
			expect(input(f.label).max).toBe(String(f.max));
		}
	});

	it('uses the global defaults as placeholders', () => {
		renderPanel({}, { globalDefaults: { prescan_cache_mb: 64, prescan_timeout: 600 } });
		expect(FIELDS.map((f) => input(f.label).placeholder)).toEqual(['64', '600', '', '']);
	});

	it('has blank placeholders when no global defaults are set', () => {
		renderPanel();
		expect(FIELDS.map((f) => input(f.label).placeholder)).toEqual(['', '', '', '']);
	});

	it('fills each input from the drive', async () => {
		await renderSyncedPanel({ prescan_cache_mb: 64, prescan_timeout: 600, prescan_retries: 3, disc_enum_timeout: 120 });
		expect(FIELDS.map((f) => input(f.label).value)).toEqual(['64', '600', '3', '120']);
	});

	describe.each(FIELDS)('$key', (f) => {
		const inRange = f.min + 1;
		const field = () => input(f.label);

		it('saves a changed value on blur', async () => {
			const onupdate = vi.fn();
			renderPanel({}, { onupdate });
			await typeAndBlur(field(), String(inRange));
			await waitFor(() => expect(onupdate).toHaveBeenCalledTimes(1));
			expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { [f.key]: inRange });
		});

		it('sends null when the value is cleared', async () => {
			renderPanel({ [f.key]: inRange });
			await typeAndBlur(field(), '');
			await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { [f.key]: null }));
		});

		it('sends null and clears the input when the value equals the global default', async () => {
			renderPanel({ [f.key]: inRange }, { globalDefaults: { [f.key]: f.max } });
			await typeAndBlur(field(), String(f.max));
			await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { [f.key]: null }));
			expect(field().value).toBe('');
		});

		it('sends nothing when the value is unchanged', async () => {
			await renderSyncedPanel({ [f.key]: inRange });
			await fireEvent.blur(field());
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('sends nothing when the value is out of range', async () => {
			renderPanel();
			await typeAndBlur(field(), String(f.max + 1));
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('reverts the input when the save fails', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('boom'));
			renderPanel({ [f.key]: inRange });
			await typeAndBlur(field(), String(f.max));
			await waitFor(() => expect(field().value).toBe(String(inRange)));
		});

		it('blurs the input on Enter', async () => {
			renderPanel();
			field().focus();
			await typeInto(field(), String(inRange));
			await fireEvent.keyDown(field(), { key: 'Enter' });
			expect(document.activeElement).not.toBe(field());
			await waitFor(() => expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { [f.key]: inRange }));
		});

		it('ignores other keys', async () => {
			renderPanel();
			await typeInto(field(), String(inRange));
			await fireEvent.keyDown(field(), { key: 'a' });
			expect(field().value).toBe(String(inRange));
			expect(screen.getByTestId('drive-default-session')).toBeTruthy();
		});

		it('reverts and closes the panel on Escape', async () => {
			renderPanel();
			await typeInto(field(), String(inRange));
			await fireEvent.keyDown(field(), { key: 'Escape' });
			await expectPanelClosed();
			expect(updateDriveMock).not.toHaveBeenCalled();
		});

		it('disables the inputs while saving', async () => {
			const finish = deferredUpdate();
			renderPanel();
			await typeAndBlur(field(), String(inRange));
			await waitFor(() => expect(field().disabled).toBe(true));
			finish();
			await waitFor(() => expect(field().disabled).toBe(false));
		});
	});
});

describe('DriveSettingsPanel sync', () => {
	it('follows a drive update while closed', async () => {
		const { rerender } = renderPanel({ rip_speed: 4, prescan_cache_mb: 64 }, { open: false });
		await rerender({ drive: createDrive({ rip_speed: 8, prescan_cache_mb: 128 }) });
		await rerender({ open: true });
		expect(input(/Rip Speed/).value).toBe('8');
		expect(input(/Pre-scan Cache/).value).toBe('128');
	});

	it('keeps typed text when the drive updates while open', async () => {
		const { rerender } = renderPanel({ rip_speed: 4, prescan_cache_mb: 64 });
		await typeInto(input(/Rip Speed/), '9');
		await typeInto(input(/Pre-scan Cache/), '77');
		await rerender({ drive: createDrive({ rip_speed: 8, prescan_cache_mb: 128 }) });
		expect(input(/Rip Speed/).value).toBe('9');
		expect(input(/Pre-scan Cache/).value).toBe('77');
	});
});

describe('DriveSettingsPanel onupdate', () => {
	it('is called after each kind of save', async () => {
		const onupdate = vi.fn();
		renderPanel({}, { onupdate });
		await fireEvent.change(sessionSelect(), { target: { value: 'ses_1' } });
		await waitFor(() => expect(onupdate).toHaveBeenCalledTimes(1));
		await typeAndBlur(input(/Rip Speed/), '8');
		await waitFor(() => expect(onupdate).toHaveBeenCalledTimes(2));
		await typeAndBlur(input(/Enum Timeout/), '20');
		await waitFor(() => expect(onupdate).toHaveBeenCalledTimes(3));
	});

	it('is optional', async () => {
		renderPanel();
		await fireEvent.change(sessionSelect(), { target: { value: 'ses_1' } });
		await typeAndBlur(input(/Rip Speed/), '8');
		await typeAndBlur(input(/Enum Timeout/), '20');
		await waitFor(() => expect(updateDriveMock).toHaveBeenCalledTimes(3));
	});
});
