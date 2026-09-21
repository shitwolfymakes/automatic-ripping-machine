import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { MediaType } from '$lib/types/api.gen';

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(),
	createSession: vi.fn(),
	updateSession: vi.fn(),
	deleteSession: vi.fn(),
	cloneSession: vi.fn(),
	previewTemplate: vi.fn().mockResolvedValue({ resolved: 'p', error: null }),
}));
vi.mock('$lib/api/ripPresets', () => ({
	fetchRipPresets: vi.fn(),
	createRipPreset: vi.fn(),
	updateRipPreset: vi.fn(),
	deleteRipPreset: vi.fn(),
}));
vi.mock('$lib/api/transcodePresets', () => ({
	fetchTranscodePresets: vi.fn(),
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn(),
	deleteTranscodePreset: vi.fn(),
}));

import { fetchSessions } from '$lib/api/sessions';
import { fetchRipPresets, createRipPreset } from '$lib/api/ripPresets';
import { fetchTranscodePresets } from '$lib/api/transcodePresets';
import { deleteSession, cloneSession } from '$lib/api/sessions';
import SessionsArea from '../SessionsArea.svelte';

const makeSession = (id = 's1', name = 'ses Alpha') => ({
	id,
	name,
	media_type: 'movie' as MediaType,
	is_builtin: false,
	rip_preset_id: 'r1',
	transcode_preset_id: null,
	output_path_template: 'movies/{title}.{ext}',
	overrides_json: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null,
});

const makeRip = (id = 'r1', name = 'rip r1') => ({
	id,
	name,
	media_type: 'movie' as MediaType,
	is_builtin: false,
	track_selection: 'main_feature' as const,
	identification_mode: 'required' as const,
	output_mode: 'tracks' as const,
	track_filters_json: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null,
});

const makeTranscode = (id = 't1', name = 'tc t1') => ({
	id,
	name,
	media_type: 'movie' as MediaType,
	is_builtin: false,
	tool: 'handbrake' as const,
	preset_ref: null,
	preset_json: null,
	container: 'mkv' as const,
	codec: 'h265' as const,
	hw_preference: 'any' as const,
	extra_args: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null,
});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

beforeEach(() => {
	vi.mocked(fetchSessions).mockResolvedValue([makeSession()]);
	vi.mocked(fetchRipPresets).mockResolvedValue([makeRip()]);
	vi.mocked(fetchTranscodePresets).mockResolvedValue([makeTranscode()]);
});

it('loads and shows a session card', async () => {
	renderComponent(SessionsArea);
	await screen.findByText(/ses /i);
});

it('Rip presets tab shows the rip presets section', async () => {
	renderComponent(SessionsArea);
	await screen.findByText(/ses /i);
	await fireEvent.click(screen.getByRole('tab', { name: /rip presets/i }));
	expect(screen.getByRole('heading', { name: /rip presets/i })).toBeInTheDocument();
});

it('Transcode presets tab shows the transcode presets section', async () => {
	renderComponent(SessionsArea);
	await screen.findByText(/ses /i);
	await fireEvent.click(screen.getByRole('tab', { name: /transcode presets/i }));
	expect(screen.getByRole('heading', { name: /transcode presets/i })).toBeInTheDocument();
});

it('tab switches back from a preset tab to sessions', async () => {
	renderComponent(SessionsArea);
	await screen.findByText(/ses /i);
	await fireEvent.click(screen.getByRole('tab', { name: /rip presets/i }));
	await fireEvent.click(screen.getByRole('tab', { name: /^sessions$/i }));
	expect(screen.getByText('ses Alpha')).toBeInTheDocument();
});

it('new session opens the builder', async () => {
	renderComponent(SessionsArea);
	await screen.findByText('ses Alpha');
	await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
	expect(screen.getByRole('heading', { name: /create a session/i })).toBeInTheDocument();
});

it('builder cancel hides the builder', async () => {
	renderComponent(SessionsArea);
	await screen.findByText('ses Alpha');
	await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
	await fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
	expect(screen.queryByRole('heading', { name: /create a session/i })).not.toBeInTheDocument();
});

// FIX 1: delete requires confirm dialog
describe('session delete — confirm flow', () => {
	it('clicking Delete opens a confirm dialog; confirming calls deleteSession then reloads', async () => {
		vi.mocked(deleteSession).mockResolvedValue(undefined);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');

		// Find the session card Delete button by its position inside the card
		// (SessionCard renders one delete button; there's no dialog yet)
		const deleteBtns = screen.getAllByRole('button', { name: /^delete$/i });
		await fireEvent.click(deleteBtns[0]);

		// Confirm dialog should appear with session-specific message
		await screen.findByText(/delete the session "ses Alpha"/i);
		const dialog = screen.getByRole('dialog');
		expect(dialog).toBeInTheDocument();

		// Click the confirm button inside the dialog (data-dialog is on the inner div)
		const confirmBtn = dialog.querySelector('[data-dialog] button:last-child') as HTMLButtonElement;
		await fireEvent.click(confirmBtn);

		await waitFor(() => expect(deleteSession).toHaveBeenCalledWith('s1'));
		await waitFor(() => expect(fetchSessions).toHaveBeenCalledTimes(2));
	});

	it('cancelling the confirm dialog does NOT call deleteSession', async () => {
		vi.mocked(deleteSession).mockResolvedValue(undefined);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');

		const deleteBtns = screen.getAllByRole('button', { name: /^delete$/i });
		await fireEvent.click(deleteBtns[0]);

		// Wait for confirm dialog
		await screen.findByText(/delete the session "ses Alpha"/i);
		const dialog = screen.getByRole('dialog');

		// Click Cancel inside the dialog
		const cancelBtn = dialog.querySelector('[data-dialog] button:first-child') as HTMLButtonElement;
		await fireEvent.click(cancelBtn);

		// Dialog should close, deleteSession should NOT have been called
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
		expect(deleteSession).not.toHaveBeenCalled();
	});
});

it('clone calls cloneSession then reloads', async () => {
	vi.mocked(cloneSession).mockResolvedValue(makeSession('s2', 'ses Alpha (copy)') as any);
	renderComponent(SessionsArea);
	await screen.findByText('ses Alpha');
	const cloneBtn = screen.getByRole('button', { name: /clone/i });
	await fireEvent.click(cloneBtn);
	await waitFor(() => expect(cloneSession).toHaveBeenCalledWith('s1', { name: 'ses Alpha (copy)' }));
	await waitFor(() => expect(fetchSessions).toHaveBeenCalledTimes(2));
});

it('inline rip create form opens over the builder', async () => {
	renderComponent(SessionsArea);
	await screen.findByText('ses Alpha');
	await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
	// Choose + Create new rip preset from the select in the builder
	const ripSel = screen.getByLabelText(/rip preset/i) as HTMLSelectElement;
	await fireEvent.change(ripSel, { target: { value: '__create_rip__' } });
	// RipPresetForm should now appear as stacked dialog
	await waitFor(() => expect(screen.getByRole('dialog', { name: /new rip preset|create rip/i })).toBeInTheDocument());
});

// FIX 3: rewritten inline-create save test — exercises the real save path
it('inline rip create: saving a new preset closes the form, reloads, and returns to builder', async () => {
	const newRip = makeRip('r2', 'My New Rip');
	vi.mocked(createRipPreset).mockResolvedValue(newRip as any);
	vi.mocked(fetchRipPresets).mockResolvedValueOnce([makeRip()]).mockResolvedValue([makeRip(), newRip]);

	renderComponent(SessionsArea);
	await screen.findByText('ses Alpha');
	await fireEvent.click(screen.getByRole('button', { name: /new session/i }));

	// Open the inline create form
	const ripSel = screen.getByLabelText(/rip preset/i) as HTMLSelectElement;
	await fireEvent.change(ripSel, { target: { value: '__create_rip__' } });

	// Wait for the stacked dialog
	const dialog = await screen.findByRole('dialog', { name: /new rip preset|create rip/i });
	expect(dialog).toBeInTheDocument();

	// Fill in the preset name (required field)
	const nameInput = screen.getByTestId('preset-name') as HTMLInputElement;
	await fireEvent.input(nameInput, { target: { value: 'My New Rip' } });

	// Submit the form
	const submitBtn = screen.getByTestId('preset-submit');
	await fireEvent.click(submitBtn);

	// createRipPreset should have been called
	await waitFor(() => expect(createRipPreset).toHaveBeenCalled());

	// Dialog should close
	await waitFor(() =>
		expect(screen.queryByRole('dialog', { name: /new rip preset|create rip/i })).not.toBeInTheDocument()
	);

	// fetchRipPresets was re-called (data.load triggered)
	await waitFor(() => expect(fetchRipPresets).toHaveBeenCalledTimes(2));

	// Builder slide-over should still be open
	expect(screen.getByRole('heading', { name: /create a session/i })).toBeInTheDocument();
});

// FIX 2: library Edit button opens the RipPresetForm with the existing preset
it('Rip presets tab Edit button opens RipPresetForm with the existing preset', async () => {
	// Only a rip preset (no transcode preset) to keep a single Edit button
	vi.mocked(fetchTranscodePresets).mockResolvedValue([]);
	renderComponent(SessionsArea);
	await screen.findByText(/ses /i);

	// Switch to the Rip presets tab
	await fireEvent.click(screen.getByRole('tab', { name: /rip presets/i }));
	await screen.findByRole('heading', { name: /rip presets/i });

	// The rip preset row shows Edit (custom preset) — only one Edit button now
	const editBtn = screen.getByRole('button', { name: /^edit$/i });
	await fireEvent.click(editBtn);

	// The stacked dialog should open with the edit form
	const dialog = await screen.findByRole('dialog', { name: /edit rip preset/i });
	expect(dialog).toBeInTheDocument();

	// The form should be pre-populated with the preset's name
	const nameInput = screen.getByTestId('preset-name') as HTMLInputElement;
	expect(nameInput.value).toBe('rip r1');
});
