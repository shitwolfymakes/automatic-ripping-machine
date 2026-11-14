import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import RipPresetForm from '../RipPresetForm.svelte';
import RipPresetFormHarness from './RipPresetFormHarness.svelte';
import { createRipPreset, updateRipPreset } from '$lib/api/rip-presets';
import type { RipPresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/rip-presets', () => ({
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
			renderComponent(RipPresetFormHarness, {
				props: { preset: null, onsaved: vi.fn() }
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

			const optionValues = (el: HTMLSelectElement) => Array.from(el.options).map((o) => o.value);
			expect(optionValues(mediaType)).toEqual(['movie', 'tv', 'music', 'data', 'iso']);
			expect(optionValues(trackSelection)).toEqual(['main_feature', 'all_tracks', 'archive', 'custom']);
			expect(optionValues(idMode)).toEqual(['required', 'skip', 'deferred_placeholder']);
			expect(optionValues(outputMode)).toEqual(['tracks', 'iso', 'data_copy', 'folder']);
		});

		it('submits the full create body with track_filters_json null for non-custom', async () => {
			createRipPresetMock.mockResolvedValue(resultPreset());
			const onsaved = vi.fn();
			renderComponent(RipPresetFormHarness, {
				props: { preset: null, onsaved }
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
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));

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
			renderComponent(RipPresetFormHarness, {
				props: { preset: null, onsaved }
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
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));

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
			renderComponent(RipPresetFormHarness, {
				props: { preset, onsaved }
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
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));

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

	describe('view mode — built-in preset', () => {
		it('is fully locked: all fields disabled, warning shown, no Save button', () => {
			const onsaved = vi.fn();
			const preset = makePreset({
				id: 'builtin_1',
				name: 'Built-in',
				is_builtin: true,
				track_selection: 'custom'
			});
			renderComponent(RipPresetFormHarness, {
				props: { preset, onsaved }
			});

			// Every field — including the name — is locked.
			expect(screen.getByTestId('preset-name')).toBeDisabled();
			expect(screen.getByTestId('preset-media-type')).toBeDisabled();
			expect(screen.getByTestId('preset-track-selection')).toBeDisabled();
			expect(screen.getByTestId('preset-identification-mode')).toBeDisabled();
			expect(screen.getByTestId('preset-output-mode')).toBeDisabled();

			// Warning banner rather than an "only the name is editable" note.
			expect(screen.getByText(/built-in preset and can't be edited/i)).toBeInTheDocument();

			// TrackFiltersEditor hidden for built-in even though track_selection is custom
			expect(screen.queryByTestId('tf-min-duration')).not.toBeInTheDocument();

			// No Save button at all.
			expect(screen.queryByRole('button', { name: /^save/i })).not.toBeInTheDocument();
			expect(updateRipPresetMock).not.toHaveBeenCalled();
		});
	});

	describe('validation', () => {
		it('keeps Save clickable; an empty name blocks the save, marks the field and focuses it', async () => {
			renderComponent(RipPresetFormHarness, {
				props: { preset: null, onsaved: vi.fn() }
			});
			const save = screen.getByRole('button', { name: /^save/i });
			expect(save).not.toBeDisabled();
			const name = screen.getByTestId('preset-name');
			expect(name).not.toHaveAttribute('aria-invalid');

			await fireEvent.click(save);

			await waitFor(() => expect(document.activeElement).toBe(name));
			expect(createRipPresetMock).not.toHaveBeenCalled();
			expect(name).toHaveAttribute('aria-invalid', 'true');
			expect(name).toHaveAttribute('aria-describedby', 'preset-name-error');
			const message = document.getElementById('preset-name-error');
			expect(message).toHaveTextContent('Name is required');
			expect(message).toHaveClass('field-error');
		});

		it('clears the mark once the name is filled in', async () => {
			renderComponent(RipPresetFormHarness, {
				props: { preset: null, onsaved: vi.fn() }
			});
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			const name = screen.getByTestId('preset-name');
			await waitFor(() => expect(name).toHaveAttribute('aria-invalid', 'true'));

			await fireEvent.input(name, { target: { value: 'Movies' } });

			expect(name).not.toHaveAttribute('aria-invalid');
			expect(screen.queryByText('Name is required')).toBeNull();
		});
	});

	describe('error handling', () => {
		it('shows the thrown error message inline', async () => {
			createRipPresetMock.mockRejectedValue(new Error('save boom'));
			renderComponent(RipPresetFormHarness, {
				props: { preset: null, onsaved: vi.fn() }
			});
			await fireEvent.input(screen.getByTestId('preset-name'), {
				target: { value: 'X' }
			});
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(screen.getByText('save boom')).toBeInTheDocument());
		});
	});
});

describe('RipPresetForm inside a sidebar (formId)', () => {
	afterEach(cleanup);

	it('takes the id, and leaves the title and the buttons to the sidebar', () => {
		const { container } = renderComponent(RipPresetForm, {
			props: { onsaved: vi.fn(), formId: 'f1' }
		});
		expect(container.querySelector('form#f1')).not.toBeNull();
		expect(screen.queryByRole('heading')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
		expect(screen.queryByRole('button', { name: /^save/i })).toBeNull();
	});

	it('submits from outside through the form attribute', async () => {
		createRipPresetMock.mockResolvedValue(resultPreset());
		const onsaved = vi.fn();
		renderComponent(RipPresetForm, { props: { onsaved, formId: 'f1' } });
		await fireEvent.input(screen.getByTestId('preset-name'), { target: { value: 'N' } });
		const external = document.createElement('button');
		external.type = 'submit';
		external.setAttribute('form', 'f1');
		document.body.appendChild(external);
		await fireEvent.click(external);
		await waitFor(() => expect(onsaved).toHaveBeenCalledWith(resultPreset()));
		external.remove();
	});
});
