import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import RipPresetForm from '../RipPresetForm.svelte';
import { createRipPreset, updateRipPreset } from '$lib/api/ripPresets';
import type { RipPresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/ripPresets', () => ({
	createRipPreset: vi.fn(),
	updateRipPreset: vi.fn()
}));

const createRipPresetMock = vi.mocked(createRipPreset);
const updateRipPresetMock = vi.mocked(updateRipPreset);

function makePreset(overrides: Partial<RipPresetView> = {}): RipPresetView {
	return {
		id: 'preset_1',
		name: 'My preset',
		media_type: 'movie',
		is_builtin: false,
		track_selection: 'custom',
		identification_mode: 'required',
		output_mode: 'tracks',
		track_filters_json: null,
		created_by_user_id: 'user_1',
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...overrides
	} as RipPresetView;
}

function resultPreset(): RipPresetView {
	return makePreset({ id: 'saved_1' });
}

describe('RipPresetForm', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('create mode', () => {
		it('renders all five selects with enum options and an enabled media_type', () => {
			renderComponent(RipPresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() }
			});

			const mediaType = screen.getByTestId('preset-media-type') as HTMLSelectElement;
			const trackSelection = screen.getByTestId('preset-track-selection') as HTMLSelectElement;
			const idMode = screen.getByTestId('preset-identification-mode') as HTMLSelectElement;
			const outputMode = screen.getByTestId('preset-output-mode') as HTMLSelectElement;

			expect(mediaType).toBeInTheDocument();
			expect(trackSelection).toBeInTheDocument();
			expect(idMode).toBeInTheDocument();
			expect(outputMode).toBeInTheDocument();
			expect(screen.getByTestId('preset-name')).toBeInTheDocument();

			// media_type editable on create
			expect(mediaType).not.toBeDisabled();

			const optionValues = (el: HTMLSelectElement) =>
				Array.from(el.options).map((o) => o.value);
			expect(optionValues(mediaType)).toEqual(['movie', 'tv', 'music', 'data', 'iso']);
			expect(optionValues(trackSelection)).toEqual([
				'main_feature',
				'all_tracks',
				'archive',
				'custom'
			]);
			expect(optionValues(idMode)).toEqual(['required', 'skip', 'deferred_placeholder']);
			expect(optionValues(outputMode)).toEqual(['tracks', 'iso', 'data_copy']);
		});

		it('submits the full create body with track_filters_json null for non-custom', async () => {
			createRipPresetMock.mockResolvedValue(resultPreset());
			const onsaved = vi.fn();
			renderComponent(RipPresetForm, {
				props: { preset: null, onsaved, oncancel: vi.fn() }
			});

			await fireEvent.input(screen.getByTestId('preset-name'), {
				target: { value: 'Big movies' }
			});
			await fireEvent.change(screen.getByTestId('preset-media-type'), {
				target: { value: 'tv' }
			});
			await fireEvent.change(screen.getByTestId('preset-track-selection'), {
				target: { value: 'all_tracks' }
			});
			await fireEvent.click(screen.getByTestId('preset-submit'));

			await waitFor(() => {
				expect(createRipPresetMock).toHaveBeenCalledWith({
					name: 'Big movies',
					media_type: 'tv',
					track_selection: 'all_tracks',
					identification_mode: 'required',
					output_mode: 'tracks',
					track_filters_json: null
				});
				expect(onsaved).toHaveBeenCalledWith(resultPreset());
			});
		});

		it('shows the TrackFiltersEditor and passes track_filters_json when custom', async () => {
			createRipPresetMock.mockResolvedValue(resultPreset());
			const onsaved = vi.fn();
			renderComponent(RipPresetForm, {
				props: { preset: null, onsaved, oncancel: vi.fn() }
			});

			await fireEvent.input(screen.getByTestId('preset-name'), {
				target: { value: 'Custom set' }
			});
			await fireEvent.change(screen.getByTestId('preset-track-selection'), {
				target: { value: 'custom' }
			});

			expect(screen.getByTestId('tf-min-duration')).toBeInTheDocument();

			await fireEvent.input(screen.getByTestId('tf-min-duration'), {
				target: { value: '120' }
			});
			await fireEvent.click(screen.getByTestId('preset-submit'));

			await waitFor(() => {
				expect(createRipPresetMock).toHaveBeenCalledWith({
					name: 'Custom set',
					media_type: 'movie',
					track_selection: 'custom',
					identification_mode: 'required',
					output_mode: 'tracks',
					track_filters_json: { min_duration_seconds: 120 }
				});
			});
		});
	});

	describe('edit mode — custom preset', () => {
		it('seeds fields, disables media_type, and submits without media_type', async () => {
			updateRipPresetMock.mockResolvedValue(resultPreset());
			const onsaved = vi.fn();
			const preset = makePreset({
				id: 'preset_99',
				name: 'Existing',
				media_type: 'music',
				track_selection: 'all_tracks',
				identification_mode: 'skip',
				output_mode: 'iso',
				is_builtin: false
			});
			renderComponent(RipPresetForm, {
				props: { preset, onsaved, oncancel: vi.fn() }
			});

			const name = screen.getByTestId('preset-name') as HTMLInputElement;
			const mediaType = screen.getByTestId('preset-media-type') as HTMLSelectElement;
			const trackSelection = screen.getByTestId('preset-track-selection') as HTMLSelectElement;

			expect(name.value).toBe('Existing');
			expect(mediaType.value).toBe('music');
			expect(mediaType).toBeDisabled();
			expect(trackSelection.value).toBe('all_tracks');
			expect(trackSelection).not.toBeDisabled();

			await fireEvent.input(name, { target: { value: 'Renamed' } });
			await fireEvent.click(screen.getByTestId('preset-submit'));

			await waitFor(() => {
				expect(updateRipPresetMock).toHaveBeenCalledWith('preset_99', {
					name: 'Renamed',
					track_selection: 'all_tracks',
					identification_mode: 'skip',
					output_mode: 'iso',
					track_filters_json: null
				});
			});
			const body = updateRipPresetMock.mock.calls[0][1];
			expect('media_type' in body).toBe(false);
		});
	});

	describe('edit mode — built-in preset', () => {
		it('only the name is editable, note is shown, submits name only', async () => {
			updateRipPresetMock.mockResolvedValue(resultPreset());
			const onsaved = vi.fn();
			const preset = makePreset({
				id: 'builtin_1',
				name: 'Built-in',
				is_builtin: true,
				track_selection: 'custom'
			});
			renderComponent(RipPresetForm, {
				props: { preset, onsaved, oncancel: vi.fn() }
			});

			expect(screen.getByTestId('preset-media-type')).toBeDisabled();
			expect(screen.getByTestId('preset-track-selection')).toBeDisabled();
			expect(screen.getByTestId('preset-identification-mode')).toBeDisabled();
			expect(screen.getByTestId('preset-output-mode')).toBeDisabled();
			expect(
				screen.getByText('Built-in preset - only the name is editable.')
			).toBeInTheDocument();

			// TrackFiltersEditor hidden for built-in even though track_selection is custom
			expect(screen.queryByTestId('tf-min-duration')).not.toBeInTheDocument();

			await fireEvent.input(screen.getByTestId('preset-name'), {
				target: { value: 'Built-in renamed' }
			});
			await fireEvent.click(screen.getByTestId('preset-submit'));

			await waitFor(() => {
				expect(updateRipPresetMock).toHaveBeenCalledWith('builtin_1', {
					name: 'Built-in renamed'
				});
				expect(onsaved).toHaveBeenCalledWith(resultPreset());
			});
		});
	});

	describe('validation', () => {
		it('disables submit when name is empty', () => {
			renderComponent(RipPresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() }
			});
			expect(screen.getByTestId('preset-submit')).toBeDisabled();
		});
	});

	describe('cancel', () => {
		it('fires oncancel', async () => {
			const oncancel = vi.fn();
			renderComponent(RipPresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel }
			});
			await fireEvent.click(screen.getByText('Cancel'));
			expect(oncancel).toHaveBeenCalledTimes(1);
		});
	});

	describe('error handling', () => {
		it('shows the thrown error message inline', async () => {
			createRipPresetMock.mockRejectedValue(new Error('save boom'));
			renderComponent(RipPresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() }
			});
			await fireEvent.input(screen.getByTestId('preset-name'), {
				target: { value: 'X' }
			});
			await fireEvent.click(screen.getByTestId('preset-submit'));
			await waitFor(() => expect(screen.getByText('save boom')).toBeInTheDocument());
		});
	});
});
