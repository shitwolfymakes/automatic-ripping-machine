import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';
import type { MediaType } from '$lib/types/api.gen';

// Branch pins for SessionsArea, beside SessionsArea.svelte.test.ts. The delete
// handlers read their target with an as-cast rather than a null guard:
// ConfirmDialog fires onconfirm only while it is open, which is only while the
// target is set. The empty-message arms of the ConfirmDialog messages are
// covered in sessionsAreaModel.test.ts.

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(),
	createSession: vi.fn(),
	updateSession: vi.fn(),
	deleteSession: vi.fn(),
	cloneSession: vi.fn(),
	previewTemplate: vi.fn().mockResolvedValue({ resolved: 'p', error: null })
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
// The transcode preset sidebar loads the HandBrake schema.
vi.mock('$lib/api/handbrakeSchema', () => ({
	fetchHandbrakeSchema: vi.fn().mockRejectedValue(new Error('No HandBrake schema loaded yet')),
	fetchBuiltinPreset: vi.fn(),
	refreshHandbrakeSchema: vi.fn()
}));
// The preset form's encoders store follows transcode.events; keep jsdom off a real socket.
vi.mock('$lib/api/ws', () => ({
	wsClient: { start: vi.fn(), subscribe: vi.fn(() => () => {}) }
}));

import { fetchSessions, updateSession, deleteSession, cloneSession } from '$lib/api/sessions';
import { fetchRipPresets, createRipPreset, updateRipPreset, deleteRipPreset } from '$lib/api/ripPresets';
import {
	fetchTranscodePresets,
	createTranscodePreset,
	updateTranscodePreset,
	deleteTranscodePreset
} from '$lib/api/transcodePresets';
import { toasts, dismissToast } from '$lib/stores/toast.svelte';
import { handbrakeSchema } from '$lib/stores/handbrakeSchema.svelte';
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
	for (const t of [...toasts.value]) dismissToast(t.id);
});

beforeEach(() => {
	handbrakeSchema.reset();
	vi.mocked(fetchSessions).mockResolvedValue([makeSession()]);
	vi.mocked(fetchRipPresets).mockResolvedValue([makeRip()]);
	vi.mocked(fetchTranscodePresets).mockResolvedValue([makeTranscode()]);
});

function toastTitled(title: string) {
	return toasts.value.find((t) => t.title === title);
}

async function expectToast(title: string, body: string) {
	await waitFor(() => expect(toastTitled(title)).toBeDefined());
	expect(toastTitled(title)?.body).toBe(body);
}

async function openTab(name: RegExp) {
	await fireEvent.click(screen.getByRole('tab', { name }));
}

// A preset tab with no sessions, so no preset counts as in use and Delete is
// enabled.
async function renderPresetTab(tab: RegExp, firstPreset: string) {
	vi.mocked(fetchSessions).mockResolvedValue([]);
	renderComponent(SessionsArea);
	await screen.findByRole('tab', { name: tab });
	await openTab(tab);
	await screen.findByText(firstPreset);
}

async function confirmDelete() {
	const dialog = await screen.findByRole('dialog', { name: 'Delete preset' });
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
}

describe('sessions', () => {
	it('Edit opens the builder titled "Edit session"', async () => {
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		expect(screen.getByRole('heading', { name: 'Edit session' })).toBeInTheDocument();
	});

	it('View on a built-in session opens the builder titled "View session"', async () => {
		vi.mocked(fetchSessions).mockResolvedValue([{ ...makeSession(), is_builtin: true }]);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /^view$/i }));
		expect(screen.getByRole('heading', { name: 'View session' })).toBeInTheDocument();
	});

	async function confirmSessionDelete() {
		const dialog = await screen.findByRole('dialog', { name: 'Delete session' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
	}
	const rowOf = (name: string) => screen.getByText(name).closest('tr') as HTMLElement;

	it('highlights the row of the session whose builder is open', async () => {
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		expect(rowOf('ses Alpha')).not.toHaveAttribute('aria-current');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		expect(rowOf('ses Alpha')).toHaveAttribute('aria-current', 'true');
	});

	it('highlights no row while a new session is being built', async () => {
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
		expect(rowOf('ses Alpha')).not.toHaveAttribute('aria-current');
	});

	it('deleting the session open in the builder closes the builder', async () => {
		vi.mocked(deleteSession).mockResolvedValue(undefined);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		await fireEvent.click(within(rowOf('ses Alpha')).getByRole('button', { name: 'Delete' }));
		await confirmSessionDelete();
		await waitFor(() => expect(screen.queryByRole('heading', { name: 'Edit session' })).not.toBeInTheDocument());
	});

	it('a delete that fails keeps the open builder', async () => {
		vi.mocked(deleteSession).mockRejectedValue(new Error('boom'));
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		await fireEvent.click(within(rowOf('ses Alpha')).getByRole('button', { name: 'Delete' }));
		await confirmSessionDelete();
		await expectToast('Delete failed', 'boom');
		expect(screen.getByRole('heading', { name: 'Edit session' })).toBeInTheDocument();
	});

	it('deleting a session other than the open one keeps the builder', async () => {
		vi.mocked(fetchSessions).mockResolvedValue([makeSession('s1', 'ses Alpha'), makeSession('s2', 'ses Beta')]);
		vi.mocked(deleteSession).mockResolvedValue(undefined);
		renderComponent(SessionsArea);
		await screen.findByText('ses Beta');
		await fireEvent.click(within(rowOf('ses Alpha')).getByRole('button', { name: 'Edit' }));
		await fireEvent.click(within(rowOf('ses Beta')).getByRole('button', { name: 'Delete' }));
		await confirmSessionDelete();
		await waitFor(() => expect(deleteSession).toHaveBeenCalledWith('s2'));
		expect(screen.getByRole('heading', { name: 'Edit session' })).toBeInTheDocument();
	});

	it('saving from the builder closes it and reloads', async () => {
		vi.mocked(updateSession).mockResolvedValue(makeSession() as any);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(screen.queryByRole('heading', { name: 'Edit session' })).not.toBeInTheDocument());
		await waitFor(() => expect(fetchSessions).toHaveBeenCalledTimes(2));
	});

	it('a clone that rejects with an Error toasts "Clone failed" with its message', async () => {
		vi.mocked(cloneSession).mockRejectedValue(new Error('no room'));
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /clone/i }));
		await expectToast('Clone failed', 'no room');
	});

	it('a clone that rejects with a non-Error toasts "Clone failed" with "Unknown error"', async () => {
		vi.mocked(cloneSession).mockRejectedValue('nope');
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /clone/i }));
		await expectToast('Clone failed', 'Unknown error');
	});

	async function deleteTheSession() {
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
		const dialog = await screen.findByRole('dialog', { name: 'Delete session' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
	}

	it('a delete that rejects with an Error toasts "Delete failed" with its message', async () => {
		vi.mocked(deleteSession).mockRejectedValue(new Error('in use'));
		await deleteTheSession();
		await expectToast('Delete failed', 'in use');
	});

	it('a delete that rejects with a non-Error toasts "Delete failed" with "Unknown error"', async () => {
		vi.mocked(deleteSession).mockRejectedValue('nope');
		await deleteTheSession();
		await expectToast('Delete failed', 'Unknown error');
	});
});

describe('presets, opening', () => {
	it('View on a rip preset opens the read-only rip sidebar with its built-in note and a Clone button', async () => {
		vi.mocked(fetchRipPresets).mockResolvedValue([{ ...makeRip(), is_builtin: true }]);
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^view$/i }));
		const dialog = await screen.findByRole('dialog', { name: 'View rip preset' });
		expect(within(dialog).getByTestId('preset-name')).toHaveValue('rip r1');
		expect(within(dialog).getByTestId('preset-name')).toBeDisabled();
		expect(within(dialog).getByTestId('preset-builtin-note')).toBeInTheDocument();
		expect(within(dialog).getByRole('button', { name: 'Clone' })).toBeInTheDocument();
		expect(within(dialog).queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
		expect(document.querySelector('.sessions-area-inline-modal')).toBeNull();
	});

	it('Clone in the read-only rip sidebar copies the preset and closes the sidebar', async () => {
		vi.mocked(fetchRipPresets).mockResolvedValue([{ ...makeRip(), is_builtin: true }]);
		vi.mocked(createRipPreset).mockResolvedValue(makeRip('r2', 'rip r1 (copy)') as any);
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^view$/i }));
		const dialog = await screen.findByRole('dialog', { name: 'View rip preset' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Clone' }));
		await waitFor(() => expect(createRipPreset).toHaveBeenCalled());
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
	});

	it('a failed Clone in the read-only rip sidebar keeps the sidebar open', async () => {
		vi.mocked(fetchRipPresets).mockResolvedValue([{ ...makeRip(), is_builtin: true }]);
		vi.mocked(createRipPreset).mockRejectedValue(new Error('no room'));
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^view$/i }));
		const dialog = await screen.findByRole('dialog', { name: 'View rip preset' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Clone' }));
		await expectToast('Clone failed', 'no room');
		expect(screen.getByRole('dialog', { name: 'View rip preset' })).toBeInTheDocument();
	});

	it('View on a built-in transcode preset opens the sidebar read-only', async () => {
		vi.mocked(fetchTranscodePresets).mockResolvedValue([{ ...makeTranscode(), is_builtin: true }]);
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^view$/i }));
		const dialog = await screen.findByRole('dialog', { name: 'View transcode preset' });
		expect(within(dialog).getByTestId('tp-name')).toHaveValue('tc t1');
		expect(within(dialog).getByTestId('tp-name')).toBeDisabled();
		expect(within(dialog).queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
	});

	it('Clone in the read-only transcode sidebar copies the preset and closes the sidebar', async () => {
		vi.mocked(fetchTranscodePresets).mockResolvedValue([{ ...makeTranscode(), is_builtin: true }]);
		vi.mocked(createTranscodePreset).mockResolvedValue(makeTranscode('t2', 'tc t1 (copy)') as any);
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^view$/i }));
		const dialog = await screen.findByRole('dialog', { name: 'View transcode preset' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Clone' }));
		await waitFor(() => expect(createTranscodePreset).toHaveBeenCalled());
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
	});

	it('a failed Clone in the read-only transcode sidebar keeps the sidebar open', async () => {
		vi.mocked(fetchTranscodePresets).mockResolvedValue([{ ...makeTranscode(), is_builtin: true }]);
		vi.mocked(createTranscodePreset).mockRejectedValue(new Error('no room'));
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^view$/i }));
		const dialog = await screen.findByRole('dialog', { name: 'View transcode preset' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Clone' }));
		await expectToast('Clone failed', 'no room');
		expect(screen.getByRole('dialog', { name: 'View transcode preset' })).toBeInTheDocument();
	});

	it('the sidebar shows how many sessions use the preset', async () => {
		vi.mocked(fetchSessions).mockResolvedValue([{ ...makeSession(), transcode_preset_id: 't1' }]);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await openTab(/transcode presets/i);
		await fireEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
		const dialog = await screen.findByRole('dialog', { name: 'Edit transcode preset' });
		expect(within(dialog).getByText('Used by 1 session')).toBeInTheDocument();
	});

	it('"New transcode preset" from the library opens an empty transcode form', async () => {
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /new transcode preset/i }));
		const dialog = await screen.findByRole('dialog', { name: 'New transcode preset' });
		expect(within(dialog).getByTestId('tp-name')).toHaveValue('');
	});

	it('creating a transcode preset from the builder opens an empty transcode form', async () => {
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
		await fireEvent.change(screen.getByLabelText(/transcode preset/i), { target: { value: '__create_tc__' } });
		const dialog = await screen.findByRole('dialog', { name: 'New transcode preset' });
		expect(within(dialog).getByTestId('tp-name')).toHaveValue('');
	});
});

describe('presets, cloning', () => {
	it('cloning a rip preset creates the copy with every field carried over, then reloads', async () => {
		const rip = {
			...makeRip(),
			track_selection: 'all_tracks' as const,
			identification_mode: 'skip' as const,
			output_mode: 'iso' as const,
			track_filters_json: { min_length: 600 }
		};
		vi.mocked(fetchRipPresets).mockResolvedValue([rip]);
		vi.mocked(createRipPreset).mockResolvedValue(makeRip('r2', 'rip r1 (copy)') as any);
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^clone$/i }));
		await waitFor(() =>
			expect(createRipPreset).toHaveBeenCalledWith({
				name: 'rip r1 (copy)',
				media_type: 'movie',
				track_selection: 'all_tracks',
				identification_mode: 'skip',
				output_mode: 'iso',
				track_filters_json: { min_length: 600 }
			})
		);
		await waitFor(() => expect(fetchRipPresets).toHaveBeenCalledTimes(2));
	});

	it('cloning a transcode preset carries its preset_ref and extra_args', async () => {
		vi.mocked(fetchTranscodePresets).mockResolvedValue([
			{ ...makeTranscode(), preset_ref: 'Fast 1080p', extra_args: '--x' }
		]);
		vi.mocked(createTranscodePreset).mockResolvedValue(makeTranscode('t2', 'tc t1 (copy)') as any);
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^clone$/i }));
		await waitFor(() =>
			expect(createTranscodePreset).toHaveBeenCalledWith({
				name: 'tc t1 (copy)',
				media_type: 'movie',
				tool: 'handbrake',
				preset_ref: 'Fast 1080p',
				container: 'mkv',
				encoder: 'any_h265',
				extra_args: '--x'
			})
		);
	});

	it('a rip preset clone that rejects with an Error toasts "Clone failed" with its message', async () => {
		vi.mocked(createRipPreset).mockRejectedValue(new Error('rip dupe'));
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^clone$/i }));
		await expectToast('Clone failed', 'rip dupe');
	});

	it('a rip preset clone that rejects with a non-Error toasts "Unknown error"', async () => {
		vi.mocked(createRipPreset).mockRejectedValue('nope');
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^clone$/i }));
		await expectToast('Clone failed', 'Unknown error');
	});

	it('a transcode preset clone that rejects with an Error toasts "Clone failed" with its message', async () => {
		vi.mocked(createTranscodePreset).mockRejectedValue(new Error('tc dupe'));
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^clone$/i }));
		await expectToast('Clone failed', 'tc dupe');
	});

	it('a transcode preset clone that rejects with a non-Error toasts "Unknown error"', async () => {
		vi.mocked(createTranscodePreset).mockRejectedValue('nope');
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^clone$/i }));
		await expectToast('Clone failed', 'Unknown error');
	});
});

describe('the table row of the open preset editor', () => {
	const rowOf = (name: string) => screen.getByText(name).closest('tr') as HTMLElement;

	it('is highlighted while a transcode preset sidebar is open, and cleared when it closes', async () => {
		await renderPresetTab(/transcode presets/i, 'tc t1');
		expect(rowOf('tc t1')).not.toHaveAttribute('aria-current');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		await screen.findByRole('dialog', { name: 'Edit transcode preset' });
		expect(rowOf('tc t1')).toHaveAttribute('aria-current', 'true');
		await fireEvent.click(screen.getByRole('button', { name: /^close$/i }));
		await waitFor(() => expect(rowOf('tc t1')).not.toHaveAttribute('aria-current'));
	});

	it('is highlighted while the rip preset dialog is open', async () => {
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		await screen.findByRole('dialog', { name: 'Edit rip preset' });
		expect(rowOf('rip r1')).toHaveAttribute('aria-current', 'true');
	});

	it('deleting the open transcode preset closes its sidebar and clears the highlight', async () => {
		vi.mocked(deleteTranscodePreset).mockResolvedValue(undefined);
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		await screen.findByRole('dialog', { name: 'Edit transcode preset' });
		await fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
		await confirmDelete();
		await waitFor(() => expect(deleteTranscodePreset).toHaveBeenCalledWith('t1'));
		await waitFor(() =>
			expect(screen.queryByRole('dialog', { name: 'Edit transcode preset' })).not.toBeInTheDocument()
		);
		expect(rowOf('tc t1')).not.toHaveAttribute('aria-current');
	});

	it('deleting the open rip preset closes its dialog and clears the highlight', async () => {
		vi.mocked(deleteRipPreset).mockResolvedValue(undefined);
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		await screen.findByRole('dialog', { name: 'Edit rip preset' });
		await fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
		await confirmDelete();
		await waitFor(() => expect(deleteRipPreset).toHaveBeenCalledWith('r1'));
		await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Edit rip preset' })).not.toBeInTheDocument());
		expect(rowOf('rip r1')).not.toHaveAttribute('aria-current');
	});

	it('a delete that fails keeps the open editor and its highlight', async () => {
		vi.mocked(deleteTranscodePreset).mockRejectedValue(new Error('in use'));
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		await screen.findByRole('dialog', { name: 'Edit transcode preset' });
		await fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
		await confirmDelete();
		await expectToast('Delete failed', 'in use');
		expect(screen.getByRole('dialog', { name: 'Edit transcode preset' })).toBeInTheDocument();
		expect(rowOf('tc t1')).toHaveAttribute('aria-current', 'true');
	});

	it('deleting another preset leaves the open editor and its highlight alone', async () => {
		vi.mocked(deleteTranscodePreset).mockResolvedValue(undefined);
		vi.mocked(fetchTranscodePresets).mockResolvedValue([makeTranscode('t1', 'tc t1'), makeTranscode('t2', 'tc t2')]);
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(within(rowOf('tc t1')).getByRole('button', { name: /^edit$/i }));
		await screen.findByRole('dialog', { name: 'Edit transcode preset' });
		await fireEvent.click(within(rowOf('tc t2')).getByRole('button', { name: /^delete$/i }));
		await confirmDelete();
		await waitFor(() => expect(deleteTranscodePreset).toHaveBeenCalledWith('t2'));
		expect(screen.getByRole('dialog', { name: 'Edit transcode preset' })).toBeInTheDocument();
		expect(rowOf('tc t1')).toHaveAttribute('aria-current', 'true');
	});
});

describe('presets, deleting', () => {
	it('confirming a rip preset delete calls deleteRipPreset only, then reloads', async () => {
		vi.mocked(deleteRipPreset).mockResolvedValue(undefined);
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
		expect(await screen.findByText('Delete the preset "rip r1"? This cannot be undone.')).toBeInTheDocument();
		await confirmDelete();
		await waitFor(() => expect(deleteRipPreset).toHaveBeenCalledWith('r1'));
		await waitFor(() => expect(fetchRipPresets).toHaveBeenCalledTimes(2));
		expect(deleteTranscodePreset).not.toHaveBeenCalled();
	});

	it('confirming a transcode preset delete calls deleteTranscodePreset only, then reloads', async () => {
		vi.mocked(deleteTranscodePreset).mockResolvedValue(undefined);
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
		expect(await screen.findByText('Delete the preset "tc t1"? This cannot be undone.')).toBeInTheDocument();
		await confirmDelete();
		await waitFor(() => expect(deleteTranscodePreset).toHaveBeenCalledWith('t1'));
		await waitFor(() => expect(fetchTranscodePresets).toHaveBeenCalledTimes(2));
		expect(deleteRipPreset).not.toHaveBeenCalled();
	});

	it('cancelling the confirm calls neither delete', async () => {
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
		const dialog = await screen.findByRole('dialog', { name: 'Delete preset' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
		expect(deleteRipPreset).not.toHaveBeenCalled();
		expect(deleteTranscodePreset).not.toHaveBeenCalled();
	});

	it('a delete that rejects with an Error toasts "Delete failed" with its message', async () => {
		vi.mocked(deleteRipPreset).mockRejectedValue(new Error('in use'));
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
		await confirmDelete();
		await expectToast('Delete failed', 'in use');
	});

	it('a delete that rejects with a non-Error toasts "Delete failed" with "Unknown error"', async () => {
		vi.mocked(deleteTranscodePreset).mockRejectedValue('nope');
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
		await confirmDelete();
		await expectToast('Delete failed', 'Unknown error');
	});
});

describe('the inline dialog and the transcode preset sidebar', () => {
	it('is labelled "New rip preset" for a new rip preset', async () => {
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /new rip preset/i }));
		expect(await screen.findByRole('dialog', { name: 'New rip preset' })).toBeInTheDocument();
	});

	it('is labelled "Edit rip preset" for an existing rip preset', async () => {
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		expect(await screen.findByRole('dialog', { name: 'Edit rip preset' })).toBeInTheDocument();
	});

	it('is labelled "New transcode preset" for a new transcode preset', async () => {
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /new transcode preset/i }));
		expect(await screen.findByRole('dialog', { name: 'New transcode preset' })).toBeInTheDocument();
	});

	it('is labelled "Edit transcode preset" for an existing transcode preset', async () => {
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		expect(await screen.findByRole('dialog', { name: 'Edit transcode preset' })).toBeInTheDocument();
	});

	it('Cancel closes the transcode preset sidebar', async () => {
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /new transcode preset/i }));
		const dialog = await screen.findByRole('dialog', { name: 'New transcode preset' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
	});

	async function openBuilderTranscodeSelect() {
		await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
		return screen.getByLabelText(/transcode preset/i) as HTMLSelectElement;
	}

	it('saving an edited rip preset closes it, reloads and preselects nothing in the builder', async () => {
		vi.mocked(updateRipPreset).mockResolvedValue(makeRip() as any);
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		const editor = await screen.findByRole('dialog', { name: 'Edit rip preset' });
		await fireEvent.click(within(editor).getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(updateRipPreset).toHaveBeenCalled());
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
		await waitFor(() => expect(fetchRipPresets).toHaveBeenCalledTimes(2));
		await openTab(/^sessions\b/i);
		await fireEvent.click(screen.getByRole('button', { name: /new session/i }));
		expect(screen.getByLabelText(/rip preset/i)).toHaveValue('');
	});

	it('saving a new transcode preset from the builder preselects it there', async () => {
		vi.mocked(createTranscodePreset).mockResolvedValue(makeTranscode('t2', 'tc new') as any);
		renderComponent(SessionsArea);
		await screen.findByText('ses Alpha');
		const select = await openBuilderTranscodeSelect();
		vi.mocked(fetchTranscodePresets).mockResolvedValue([makeTranscode(), makeTranscode('t2', 'tc new')]);
		await fireEvent.change(select, { target: { value: '__create_tc__' } });
		const tcDialog = await screen.findByRole('dialog', { name: 'New transcode preset' });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'tc new' } });
		await fireEvent.click(within(tcDialog).getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(createTranscodePreset).toHaveBeenCalled());
		await waitFor(() => expect(screen.queryByRole('dialog', { name: 'New transcode preset' })).not.toBeInTheDocument());
		await waitFor(() => expect(select.value).toBe('t2'));
	});

	it('saving an edited transcode preset closes it and preselects nothing in the builder', async () => {
		vi.mocked(updateTranscodePreset).mockResolvedValue(makeTranscode() as any);
		await renderPresetTab(/transcode presets/i, 'tc t1');
		await fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
		await screen.findByRole('dialog', { name: 'Edit transcode preset' });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(updateTranscodePreset).toHaveBeenCalled());
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
		await waitFor(() => expect(fetchTranscodePresets).toHaveBeenCalledTimes(2));
		await openTab(/^sessions\b/i);
		const select = await openBuilderTranscodeSelect();
		expect(select.value).toBe('');
	});

	it('the scrim closes it', async () => {
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /new rip preset/i }));
		await screen.findByRole('dialog', { name: 'New rip preset' });
		await fireEvent.click(document.querySelector('.slide-over-scrim') as HTMLElement);
		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
	});

	it('Cancel closes it', async () => {
		await renderPresetTab(/rip presets/i, 'rip r1');
		await fireEvent.click(screen.getByRole('button', { name: /new rip preset/i }));
		const dialog = await screen.findByRole('dialog', { name: 'New rip preset' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
	});
});

describe('the error banner', () => {
	it('shows the message of a load that rejects with an Error', async () => {
		vi.mocked(fetchSessions).mockRejectedValue(new Error('backend down'));
		renderComponent(SessionsArea);
		expect(await screen.findByText('backend down')).toBeInTheDocument();
	});

	it('shows "Failed to load sessions" for a load that rejects with a non-Error', async () => {
		vi.mocked(fetchSessions).mockRejectedValue('nope');
		renderComponent(SessionsArea);
		expect(await screen.findByText('Failed to load sessions')).toBeInTheDocument();
	});
});
