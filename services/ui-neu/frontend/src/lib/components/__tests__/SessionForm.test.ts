import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import SessionForm from '../SessionForm.svelte';
import { createSession, updateSession, previewTemplate } from '$lib/api/sessions';
import { fetchRipPresets } from '$lib/api/ripPresets';
import { fetchTranscodePresets } from '$lib/api/transcodePresets';
import type { RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/sessions', () => ({
	createSession: vi.fn(),
	updateSession: vi.fn(),
	previewTemplate: vi.fn()
}));
vi.mock('$lib/api/ripPresets', () => ({ fetchRipPresets: vi.fn() }));
vi.mock('$lib/api/transcodePresets', () => ({ fetchTranscodePresets: vi.fn() }));

const createMock = vi.mocked(createSession);
const updateMock = vi.mocked(updateSession);
const previewMock = vi.mocked(previewTemplate);
const ripMock = vi.mocked(fetchRipPresets);
const tcMock = vi.mocked(fetchTranscodePresets);

function rip(id: string, media_type = 'movie', name = id): RipPresetView {
	return { id, name, media_type, is_builtin: false } as RipPresetView;
}
function tc(id: string, media_type = 'movie', name = id): TranscodePresetView {
	return { id, name, media_type, is_builtin: false } as TranscodePresetView;
}
function makeSession(overrides: Partial<SessionView> = {}): SessionView {
	return {
		id: 'ses_1',
		name: 'My session',
		media_type: 'movie',
		is_builtin: false,
		rip_preset_id: 'rp_movie',
		transcode_preset_id: 'tp_movie',
		output_path_template: '/media/{title}',
		overrides_json: { min_length_seconds: 600 },
		created_by_user_id: 'u1',
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...overrides
	} as SessionView;
}
function resultSession(): SessionView {
	return makeSession({ id: 'saved_1' });
}

const defaultPresets = () => {
	ripMock.mockResolvedValue([rip('rp_movie', 'movie', 'Movie rip'), rip('rp_music', 'music', 'Music rip')]);
	tcMock.mockResolvedValue([tc('tp_movie', 'movie', 'Movie tc'), tc('tp_music', 'music', 'Music tc')]);
};

describe('SessionForm', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
		vi.useRealTimers();
	});

	describe('create mode', () => {
		it('loads preset dropdowns filtered to the media_type', async () => {
			defaultPresets();
			previewMock.mockResolvedValue({ expansion: '' });
			renderComponent(SessionForm, { props: { session: null, onsaved: vi.fn(), oncancel: vi.fn() } });

			const ripSel = screen.getByTestId('session-rip-preset') as HTMLSelectElement;
			const tcSel = screen.getByTestId('session-transcode-preset') as HTMLSelectElement;
			// Wait for the loaded presets to paint into the dropdowns.
			await waitFor(() => expect(Array.from(ripSel.options).map((o) => o.value)).toEqual(['rp_movie']));
			expect(Array.from(tcSel.options).map((o) => o.value)).toEqual(['', 'tp_movie']);
		});

		it('re-filters and resets preset selects when media_type changes', async () => {
			defaultPresets();
			previewMock.mockResolvedValue({ expansion: '' });
			renderComponent(SessionForm, { props: { session: null, onsaved: vi.fn(), oncancel: vi.fn() } });
			await waitFor(() => expect(ripMock).toHaveBeenCalled());

			await fireEvent.change(screen.getByTestId('session-media-type'), { target: { value: 'music' } });

			const ripSel = screen.getByTestId('session-rip-preset') as HTMLSelectElement;
			expect(Array.from(ripSel.options).map((o) => o.value)).toEqual(['rp_music']);
			expect(ripSel.value).toBe('rp_music');
		});

		it('submits the full create body (no overrides_json), transcode null when none', async () => {
			defaultPresets();
			previewMock.mockResolvedValue({ expansion: '' });
			createMock.mockResolvedValue(resultSession());
			const onsaved = vi.fn();
			renderComponent(SessionForm, { props: { session: null, onsaved, oncancel: vi.fn() } });
			await waitFor(() => expect(ripMock).toHaveBeenCalled());

			await fireEvent.input(screen.getByTestId('session-name'), { target: { value: 'Movies' } });
			await fireEvent.change(screen.getByTestId('session-rip-preset'), { target: { value: 'rp_movie' } });
			await fireEvent.input(screen.getByTestId('session-template'), { target: { value: '/media/{title}' } });
			await fireEvent.click(screen.getByTestId('session-submit'));

			await waitFor(() => {
				expect(createMock).toHaveBeenCalledWith({
					name: 'Movies',
					media_type: 'movie',
					rip_preset_id: 'rp_movie',
					transcode_preset_id: null,
					output_path_template: '/media/{title}'
				});
				expect(onsaved).toHaveBeenCalledWith(resultSession());
			});
			expect('overrides_json' in createMock.mock.calls[0][0]).toBe(false);
		});

		it('disables submit until a rip preset is available/selected', async () => {
			// No rip presets for the default media type → rip select empty → submit blocked even with a name.
			ripMock.mockResolvedValue([]);
			tcMock.mockResolvedValue([]);
			previewMock.mockResolvedValue({ expansion: '' });
			renderComponent(SessionForm, { props: { session: null, onsaved: vi.fn(), oncancel: vi.fn() } });
			await waitFor(() => expect(ripMock).toHaveBeenCalled());
			await fireEvent.input(screen.getByTestId('session-name'), { target: { value: 'Has name' } });
			expect(screen.getByTestId('session-submit')).toBeDisabled();
		});
	});

	describe('live preview', () => {
		it('debounces and renders the expansion from previewTemplate', async () => {
			vi.useFakeTimers();
			defaultPresets();
			previewMock.mockResolvedValue({ expansion: '/media/The Matrix' });
			renderComponent(SessionForm, { props: { session: null, onsaved: vi.fn(), oncancel: vi.fn() } });
			await vi.advanceTimersByTimeAsync(0);
			await fireEvent.input(screen.getByTestId('session-template'), { target: { value: '/media/{title}' } });
			await vi.advanceTimersByTimeAsync(300);

			expect(previewMock).toHaveBeenCalledWith({
				template: '/media/{title}',
				media_type: 'movie',
				has_transcode_preset: false
			});
			await waitFor(() => expect(screen.getByTestId('session-preview')).toHaveTextContent('/media/The Matrix'));
		});

		it('shows the preview error in the panel on a 422', async () => {
			vi.useFakeTimers();
			defaultPresets();
			previewMock.mockRejectedValue(new Error('bad template'));
			renderComponent(SessionForm, { props: { session: null, onsaved: vi.fn(), oncancel: vi.fn() } });
			await vi.advanceTimersByTimeAsync(0);
			await fireEvent.input(screen.getByTestId('session-template'), { target: { value: '/x/{nope}' } });
			await vi.advanceTimersByTimeAsync(300);
			await waitFor(() => expect(screen.getByTestId('session-preview-error')).toHaveTextContent('bad template'));
		});
	});

	describe('edit mode — custom', () => {
		it('seeds fields, disables media_type, submits without media_type or overrides_json', async () => {
			defaultPresets();
			previewMock.mockResolvedValue({ expansion: '' });
			updateMock.mockResolvedValue(resultSession());
			const session = makeSession({ id: 'ses_9', name: 'Existing', transcode_preset_id: 'tp_movie' });
			renderComponent(SessionForm, { props: { session, onsaved: vi.fn(), oncancel: vi.fn() } });
			await waitFor(() => expect(ripMock).toHaveBeenCalled());

			const mediaType = screen.getByTestId('session-media-type') as HTMLSelectElement;
			expect((screen.getByTestId('session-name') as HTMLInputElement).value).toBe('Existing');
			expect(mediaType).toBeDisabled();

			await fireEvent.input(screen.getByTestId('session-name'), { target: { value: 'Renamed' } });
			await fireEvent.click(screen.getByTestId('session-submit'));

			await waitFor(() => {
				expect(updateMock).toHaveBeenCalledWith('ses_9', {
					name: 'Renamed',
					rip_preset_id: 'rp_movie',
					transcode_preset_id: 'tp_movie',
					output_path_template: '/media/{title}'
				});
			});
			const body = updateMock.mock.calls[0][1];
			expect('media_type' in body).toBe(false);
			expect('overrides_json' in body).toBe(false);
		});
	});

	describe('edit mode — built-in', () => {
		it('only name editable, note shown, submits name only', async () => {
			defaultPresets();
			previewMock.mockResolvedValue({ expansion: '' });
			updateMock.mockResolvedValue(resultSession());
			const session = makeSession({ id: 'b1', name: 'Stock', is_builtin: true });
			renderComponent(SessionForm, { props: { session, onsaved: vi.fn(), oncancel: vi.fn() } });
			await waitFor(() => expect(ripMock).toHaveBeenCalled());

			expect(screen.getByTestId('session-rip-preset')).toBeDisabled();
			expect(screen.getByTestId('session-transcode-preset')).toBeDisabled();
			expect(screen.getByTestId('session-template')).toBeDisabled();
			expect(screen.getByText(/only the name is editable/i)).toBeInTheDocument();

			await fireEvent.input(screen.getByTestId('session-name'), { target: { value: 'Stock renamed' } });
			await fireEvent.click(screen.getByTestId('session-submit'));
			await waitFor(() => expect(updateMock).toHaveBeenCalledWith('b1', { name: 'Stock renamed' }));
		});
	});

	describe('validation + cancel + error', () => {
		it('disables submit when name empty', async () => {
			defaultPresets();
			previewMock.mockResolvedValue({ expansion: '' });
			renderComponent(SessionForm, { props: { session: null, onsaved: vi.fn(), oncancel: vi.fn() } });
			await waitFor(() => expect(ripMock).toHaveBeenCalled());
			expect(screen.getByTestId('session-submit')).toBeDisabled();
		});

		it('fires oncancel', async () => {
			defaultPresets();
			previewMock.mockResolvedValue({ expansion: '' });
			const oncancel = vi.fn();
			renderComponent(SessionForm, { props: { session: null, onsaved: vi.fn(), oncancel } });
			await waitFor(() => expect(ripMock).toHaveBeenCalled());
			await fireEvent.click(screen.getByText('Cancel'));
			expect(oncancel).toHaveBeenCalledTimes(1);
		});

		it('shows a save error inline', async () => {
			defaultPresets();
			previewMock.mockResolvedValue({ expansion: '' });
			createMock.mockRejectedValue(new Error('save boom'));
			renderComponent(SessionForm, { props: { session: null, onsaved: vi.fn(), oncancel: vi.fn() } });
			await waitFor(() => expect(ripMock).toHaveBeenCalled());
			await fireEvent.input(screen.getByTestId('session-name'), { target: { value: 'X' } });
			await fireEvent.change(screen.getByTestId('session-rip-preset'), { target: { value: 'rp_movie' } });
			await fireEvent.input(screen.getByTestId('session-template'), { target: { value: '/m/{title}' } });
			await fireEvent.click(screen.getByTestId('session-submit'));
			await waitFor(() => expect(screen.getByTestId('session-error')).toHaveTextContent('save boom'));
		});
	});
});
