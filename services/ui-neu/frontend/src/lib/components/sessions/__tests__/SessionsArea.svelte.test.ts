import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';
import type { MediaType } from '$lib/types/api.gen';

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(),
	createSession: vi.fn(),
	updateSession: vi.fn(),
	deleteSession: vi.fn(),
	cloneSession: vi.fn(),
	previewTemplate: vi.fn().mockResolvedValue({ resolved: 'p', error: null })
}));
vi.mock('$lib/api/sessionRoutes', () => ({
	fetchSessionRoutes: vi.fn().mockResolvedValue([]),
	upsertSessionRoute: vi.fn(),
	deleteSessionRoute: vi.fn()
}));
vi.mock('$lib/api/ripPresets', () => ({
	fetchRipPresets: vi.fn(),
	createRipPreset: vi.fn(),
	updateRipPreset: vi.fn(),
	deleteRipPreset: vi.fn()
}));
vi.mock('$lib/api/transcodePresets', () => ({
	fetchTranscodePresets: vi.fn(),
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn(),
	deleteTranscodePreset: vi.fn()
}));
vi.mock('$lib/api/handbrakeSchema', () => ({
	fetchHandbrakeSchema: vi.fn().mockRejectedValue(new Error('No HandBrake schema loaded yet')),
	fetchBuiltinPreset: vi.fn(),
	refreshHandbrakeSchema: vi.fn()
}));
// The preset form's encoders store follows transcode.events; keep jsdom off a real socket.
vi.mock('$lib/api/ws', () => ({
	wsClient: { start: vi.fn(), subscribe: vi.fn(() => () => {}) }
}));

import { fetchSessions } from '$lib/api/sessions';
import { fetchSessionRoutes } from '$lib/api/sessionRoutes';
import { fetchRipPresets, createRipPreset } from '$lib/api/ripPresets';
import { fetchTranscodePresets, createTranscodePreset } from '$lib/api/transcodePresets';
import { deleteSession, cloneSession } from '$lib/api/sessions';
import SessionsArea from '../SessionsArea.svelte';
import { setTranscoderEnabled } from '$lib/stores/config';

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
	updated_at: null
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
	updated_at: null
});

const makeTranscode = (id = 't1', name = 'tc t1') => ({
	id,
	name,
	media_type: 'movie' as MediaType,
	is_builtin: false,
	tool: 'handbrake' as const,
	preset_ref: null,
	handbrake_settings: null,
	container: 'mkv' as const,
	encoder: 'any_h265',
	extra_args: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null
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

it('cloning a transcode preset carries its encoder', async () => {
	vi.mocked(createTranscodePreset).mockResolvedValue(makeTranscode('t2', 'tc t1 (copy)') as any);
	renderComponent(SessionsArea);
	await screen.findByText(/ses /i);
	await fireEvent.click(screen.getByRole('tab', { name: /transcode presets/i }));
	await fireEvent.click(screen.getByRole('button', { name: /^clone$/i }));
	await waitFor(() =>
		expect(createTranscodePreset).toHaveBeenCalledWith(
			expect.objectContaining({ name: 'tc t1 (copy)', encoder: 'any_h265' })
		)
	);
});

it('tab switches back from a preset tab to sessions', async () => {
	renderComponent(SessionsArea);
	await screen.findByText(/ses /i);
	await fireEvent.click(screen.getByRole('tab', { name: /rip presets/i }));
	await fireEvent.click(screen.getByRole('tab', { name: /^sessions\b/i }));
	expect(screen.getByText('ses Alpha')).toBeInTheDocument();
});

it('new session opens the builder', async () => {
	renderComponent(SessionsArea);
	await screen.findByText('ses Alpha');
	await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
	expect(screen.getByRole('heading', { name: 'New session' })).toBeInTheDocument();
});

it('builder cancel hides the builder', async () => {
	renderComponent(SessionsArea);
	await screen.findByText('ses Alpha');
	await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
	await fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
	expect(screen.queryByRole('heading', { name: 'New session' })).not.toBeInTheDocument();
});

// FIX 1: delete requires confirm dialog
describe('session delete — confirm flow', () => {
	it('clicking Delete opens a confirm dialog; confirming calls deleteSession then reloads', async () => {
		vi.mocked(deleteSession).mockResolvedValue(undefined);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');

		// The first Delete button is the first session row's
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
	expect(dialog).toHaveAttribute('data-stacked', 'true');

	// Fill in the preset name (required field)
	const nameInput = screen.getByTestId('preset-name') as HTMLInputElement;
	await fireEvent.input(nameInput, { target: { value: 'My New Rip' } });

	// Submit the form
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

	// createRipPreset should have been called
	await waitFor(() => expect(createRipPreset).toHaveBeenCalled());

	// Dialog should close
	await waitFor(() =>
		expect(screen.queryByRole('dialog', { name: /new rip preset|create rip/i })).not.toBeInTheDocument()
	);

	// fetchRipPresets was re-called (data.load triggered)
	await waitFor(() => expect(fetchRipPresets).toHaveBeenCalledTimes(2));

	// Builder slide-over should still be open
	expect(screen.getByRole('heading', { name: 'New session' })).toBeInTheDocument();
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

describe('ripper-only deployment (not transcode-capable)', () => {
	const passthroughPreset = () => ({ ...makeTranscode('t_none', 'tc passthrough'), tool: 'none' as const });

	beforeEach(() => {
		vi.mocked(fetchSessions).mockResolvedValue([
			{ ...makeSession('s_raw', 'ses Raw'), transcode_preset_id: null },
			{ ...makeSession('s_pass', 'ses Pass'), transcode_preset_id: 't_none' },
			{ ...makeSession('s_enc', 'ses Encode'), transcode_preset_id: 't1' }
		]);
		vi.mocked(fetchTranscodePresets).mockResolvedValue([makeTranscode(), passthroughPreset()]);
	});

	afterEach(() => setTranscoderEnabled(true));

	it('hub lists only passthrough sessions, with type counts to match', async () => {
		setTranscoderEnabled(false);
		renderComponent(SessionsArea);
		await screen.findByText('ses Raw');
		expect(screen.getByText('ses Pass')).toBeInTheDocument();
		expect(screen.queryByText('ses Encode')).not.toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'All 2' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Movie 2' })).toBeInTheDocument();
	});

	it('builder transcode picker offers only passthrough presets', async () => {
		setTranscoderEnabled(false);
		renderComponent(SessionsArea);
		await screen.findByText('ses Raw');
		await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
		const tcSel = screen.getByLabelText(/transcode preset/i) as HTMLSelectElement;
		const labels = Array.from(tcSel.options).map((o) => o.textContent?.trim());
		expect(labels).toContain('tc passthrough');
		expect(labels).not.toContain('tc t1');
	});

	it('transcode preset library shows only passthrough presets', async () => {
		setTranscoderEnabled(false);
		renderComponent(SessionsArea);
		await screen.findByText('ses Raw');
		await fireEvent.click(screen.getByRole('tab', { name: /transcode presets/i }));
		expect(screen.getByText('tc passthrough')).toBeInTheDocument();
		expect(screen.queryByText('tc t1')).not.toBeInTheDocument();
	});

	it('capable deployment keeps encode sessions and presets', async () => {
		setTranscoderEnabled(true);
		renderComponent(SessionsArea);
		await screen.findByText('ses Encode');
		await fireEvent.click(screen.getByRole('tab', { name: /transcode presets/i }));
		expect(screen.getByText('tc t1')).toBeInTheDocument();
	});
});

describe('every editor opens a sidebar', () => {
	it('"+ Create new transcode preset..." in the session slide-over opens the sidebar', async () => {
		renderComponent(SessionsArea);
		await screen.findByText(/ses /i);
		await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
		await fireEvent.change(screen.getByLabelText(/transcode preset/i), { target: { value: '__create_tc__' } });
		const sidebar = await screen.findByRole('dialog', { name: 'New transcode preset' });
		expect(sidebar).toHaveTextContent('Import HandBrake preset');
		expect(within(sidebar).getByRole('button', { name: 'Save' })).toBeInTheDocument();
	});

	it('Edit on a transcode preset opens the sidebar, not the dialog', async () => {
		renderComponent(SessionsArea);
		await screen.findByText(/ses /i);
		await fireEvent.click(screen.getByRole('tab', { name: /transcode presets/i }));
		await fireEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
		const sidebar = await screen.findByRole('dialog', { name: 'Edit transcode preset' });
		expect(sidebar).toHaveTextContent('Save');
	});

	it('a new rip preset opens the rip preset sidebar, not the old modal', async () => {
		renderComponent(SessionsArea);
		await screen.findByText(/ses /i);
		await fireEvent.click(screen.getByRole('tab', { name: /rip presets/i }));
		await fireEvent.click(screen.getByRole('button', { name: /new rip preset/i }));
		const dialog = await screen.findByRole('dialog', { name: 'New rip preset' });
		expect(dialog).not.toHaveTextContent('Import HandBrake preset');
		expect(dialog).toHaveAttribute('data-stacked', 'false');
		expect(document.querySelector('.sessions-area-inline-modal')).toBeNull();
	});
});

describe('the sidebar stacked over the session slide-over', () => {
	it('layers above the builder, and an outside click closes only the sidebar', async () => {
		renderComponent(SessionsArea);
		await screen.findByText(/ses /i);
		await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
		await fireEvent.change(screen.getByLabelText(/transcode preset/i), { target: { value: '__create_tc__' } });
		const sidebar = await screen.findByRole('dialog', { name: 'New transcode preset' });
		expect(sidebar).toHaveAttribute('data-stacked', 'true');
		const scrim = document.querySelector('.slide-over-scrim[data-stacked="true"]') as HTMLElement;
		await fireEvent.click(scrim);
		await waitFor(() => expect(screen.queryByRole('dialog', { name: 'New transcode preset' })).not.toBeInTheDocument());
		expect(screen.getByRole('heading', { name: 'New session' })).toBeInTheDocument();
	});
});

describe('the page header and view switch', () => {
	it('holds the presets note in the header for every view', async () => {
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		const note = /Presets are reusable building blocks: each preset can be used by multiple sessions/;
		expect(screen.getByText(note)).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('tab', { name: /rip presets/i }));
		expect(screen.getAllByText(note)).toHaveLength(1);
	});

	it('is a segmented control of four tabs, the list views showing their counts', async () => {
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		const tabs = screen.getAllByRole('tab');
		expect(tabs.map((t) => t.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
			'Sessions 1',
			'Rip presets 1',
			'Transcode presets 1',
			'Routing'
		]);
		expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
		expect(tabs[3]).toHaveAttribute('aria-selected', 'false');
	});

	it('Routing shows the matrix, with no search, source filter or type chips', async () => {
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		expect(screen.getByRole('searchbox')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('tab', { name: 'Routing' }));
		expect(screen.getByRole('tab', { name: 'Routing' })).toHaveAttribute('aria-selected', 'true');
		expect(await screen.findByLabelText('Movie, Any disc')).toBeInTheDocument();
		expect(fetchSessionRoutes).toHaveBeenCalled();
		expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
		expect(screen.queryByLabelText('Filter by source')).not.toBeInTheDocument();
		expect(screen.queryByRole('table', { name: 'Sessions' })).not.toBeInTheDocument();
	});
});

describe('creating a preset from the session sidebar keeps the session form', () => {
	async function typeSessionName() {
		await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
		await fireEvent.input(screen.getByLabelText(/session name/i), { target: { value: 'Keep me' } });
		await fireEvent.input(screen.getByLabelText(/output path/i), { target: { value: 'keep/{title}.{ext}' } });
	}

	it('a new rip preset is selected in the form, and the other unsaved edits stay', async () => {
		const newRip = makeRip('r2', 'My New Rip');
		vi.mocked(createRipPreset).mockResolvedValue(newRip as any);
		vi.mocked(fetchRipPresets).mockResolvedValueOnce([makeRip()]).mockResolvedValue([makeRip(), newRip]);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await typeSessionName();
		await fireEvent.change(screen.getByLabelText(/rip preset/i), { target: { value: '__create_rip__' } });
		const sidebar = await screen.findByRole('dialog', { name: 'New rip preset' });
		await fireEvent.input(within(sidebar).getByTestId('preset-name'), { target: { value: 'My New Rip' } });
		await fireEvent.click(within(sidebar).getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(screen.queryByRole('dialog', { name: 'New rip preset' })).not.toBeInTheDocument());
		await waitFor(() => expect(screen.getByLabelText(/rip preset/i)).toHaveValue('r2'));
		expect(screen.getByLabelText(/session name/i)).toHaveValue('Keep me');
		expect(screen.getByLabelText(/output path/i)).toHaveValue('keep/{title}.{ext}');
		expect(screen.getByRole('dialog', { name: 'New session' })).toBeInTheDocument();
	});

	it('a new transcode preset is selected in the form, and the other unsaved edits stay', async () => {
		const newTc = makeTranscode('t2', 'tc new');
		vi.mocked(createTranscodePreset).mockResolvedValue(newTc as any);
		vi.mocked(fetchTranscodePresets)
			.mockResolvedValueOnce([makeTranscode()])
			.mockResolvedValue([makeTranscode(), newTc]);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await typeSessionName();
		await fireEvent.change(screen.getByLabelText(/transcode preset/i), { target: { value: '__create_tc__' } });
		const tcDialog = await screen.findByRole('dialog', { name: 'New transcode preset' });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'tc new' } });
		await fireEvent.click(within(tcDialog).getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(screen.queryByRole('dialog', { name: 'New transcode preset' })).not.toBeInTheDocument());
		await waitFor(() => expect(screen.getByLabelText(/transcode preset/i)).toHaveValue('t2'));
		expect(screen.getByLabelText(/session name/i)).toHaveValue('Keep me');
		expect(screen.getByLabelText(/output path/i)).toHaveValue('keep/{title}.{ext}');
	});

	it('Escape closes only the stacked preset sidebar, not the session sidebar under it', async () => {
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await typeSessionName();
		await fireEvent.change(screen.getByLabelText(/rip preset/i), { target: { value: '__create_rip__' } });
		await screen.findByRole('dialog', { name: 'New rip preset' });
		await fireEvent.keyDown(document, { key: 'Escape' });
		await waitFor(() => expect(screen.queryByRole('dialog', { name: 'New rip preset' })).not.toBeInTheDocument());
		expect(screen.getByLabelText(/session name/i)).toHaveValue('Keep me');
	});
});
