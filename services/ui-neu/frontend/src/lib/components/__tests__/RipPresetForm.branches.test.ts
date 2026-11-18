import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import RipPresetFormHarness from './RipPresetFormHarness.svelte';
import { createRipPreset, updateRipPreset } from '$lib/api/ripPresets';
import type { RipPresetView } from '$lib/types/api.gen';

// Pins for RipPresetForm's submit rules, beside RipPresetForm.test.ts. One
// branch cannot be reached from the rendered component, so nothing here
// forces it:
// - The `&& preset` half of submit's `editing && preset` test: `editing` is
//   derived from `!!preset`, so whenever it is true `preset` is set too and
//   the else path (create) is only taken when `editing` is false.

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

function renderForm(preset: RipPresetView | null, onsaved = vi.fn()) {
	return renderComponent(RipPresetFormHarness, { props: { preset, onsaved } });
}

function submitForm(): Promise<boolean> {
	return fireEvent.submit(screen.getByTestId('preset-name').closest('form') as HTMLFormElement);
}

async function typeName(value: string): Promise<void> {
	await fireEvent.input(screen.getByTestId('preset-name'), { target: { value } });
}

// A save promise the test settles by hand.
function deferred<T>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

describe('RipPresetForm submit rules', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('guard', () => {
		it('makes no call when a built-in preset is submitted', async () => {
			renderForm(makePreset({ is_builtin: true, name: 'Built-in' }));
			await submitForm();
			expect(createRipPresetMock).not.toHaveBeenCalled();
			expect(updateRipPresetMock).not.toHaveBeenCalled();
		});

		it('makes no call for a blank name', async () => {
			renderForm(null);
			await submitForm();
			expect(createRipPresetMock).not.toHaveBeenCalled();
		});

		it('makes no call for a whitespace-only name', async () => {
			renderForm(null);
			await typeName('   ');
			await submitForm();
			expect(createRipPresetMock).not.toHaveBeenCalled();
		});

		it('makes no second call while a save is in flight', async () => {
			const save = deferred<RipPresetView>();
			createRipPresetMock.mockReturnValue(save.promise);
			renderForm(null);
			await typeName('Once');
			await submitForm();
			await submitForm();
			expect(createRipPresetMock).toHaveBeenCalledTimes(1);
			save.resolve(resultPreset());
			await waitFor(() => expect(screen.getByRole('button', { name: /^save/i })).not.toBeDisabled());
		});
	});

	describe('request', () => {
		it('creates with the values chosen in the selects', async () => {
			createRipPresetMock.mockResolvedValue(resultPreset());
			renderForm(null);
			await typeName('Picked');
			await fireEvent.change(screen.getByTestId('preset-media-type'), { target: { value: 'music' } });
			await fireEvent.change(screen.getByTestId('preset-track-selection'), { target: { value: 'archive' } });
			await fireEvent.change(screen.getByTestId('preset-identification-mode'), { target: { value: 'skip' } });
			await fireEvent.change(screen.getByTestId('preset-output-mode'), { target: { value: 'folder' } });
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(createRipPresetMock).toHaveBeenCalledTimes(1));
			expect(createRipPresetMock).toHaveBeenCalledWith({
				name: 'Picked',
				media_type: 'music',
				track_selection: 'archive',
				identification_mode: 'skip',
				output_mode: 'folder',
				track_filters_json: null
			});
		});

		it('updates a custom preset by id with the same body minus media_type', async () => {
			updateRipPresetMock.mockResolvedValue(resultPreset());
			renderForm(makePreset({ id: 'preset_7', media_type: 'tv', track_selection: 'main_feature' }));
			await fireEvent.change(screen.getByTestId('preset-identification-mode'), {
				target: { value: 'deferred_placeholder' }
			});
			await fireEvent.change(screen.getByTestId('preset-output-mode'), { target: { value: 'iso' } });
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(updateRipPresetMock).toHaveBeenCalledTimes(1));
			expect(updateRipPresetMock).toHaveBeenCalledWith('preset_7', {
				name: 'My preset',
				track_selection: 'main_feature',
				identification_mode: 'deferred_placeholder',
				output_mode: 'iso',
				track_filters_json: null
			});
			expect(createRipPresetMock).not.toHaveBeenCalled();
		});

		it('sends null track_filters_json for a non-custom selection even when the preset carries filters', async () => {
			updateRipPresetMock.mockResolvedValue(resultPreset());
			renderForm(
				makePreset({
					track_selection: 'all_tracks',
					track_filters_json: { min_duration_seconds: 90 }
				})
			);
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(updateRipPresetMock).toHaveBeenCalledTimes(1));
			expect(updateRipPresetMock.mock.calls[0][1].track_filters_json).toBeNull();
		});

		it('drops null and undefined filter keys for the custom selection', async () => {
			updateRipPresetMock.mockResolvedValue(resultPreset());
			renderForm(
				makePreset({
					track_filters_json: {
						min_duration_seconds: 120,
						max_duration_seconds: 0,
						title_indices: null,
						title_indices_exclude: [4, 5],
						extra_unset: undefined
					} as unknown as RipPresetView['track_filters_json']
				})
			);
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(updateRipPresetMock).toHaveBeenCalledTimes(1));
			expect(updateRipPresetMock.mock.calls[0][1].track_filters_json).toEqual({
				min_duration_seconds: 120,
				max_duration_seconds: 0,
				title_indices_exclude: [4, 5]
			});
			expect(Object.keys(updateRipPresetMock.mock.calls[0][1].track_filters_json as object)).toEqual([
				'min_duration_seconds',
				'max_duration_seconds',
				'title_indices_exclude'
			]);
		});

		it('sends an empty object for the custom selection with no filters', async () => {
			createRipPresetMock.mockResolvedValue(resultPreset());
			renderForm(null);
			await typeName('Bare custom');
			await fireEvent.change(screen.getByTestId('preset-track-selection'), { target: { value: 'custom' } });
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(createRipPresetMock).toHaveBeenCalledTimes(1));
			expect(createRipPresetMock.mock.calls[0][0].track_filters_json).toEqual({});
		});
	});

	describe('save', () => {
		it('shows Saving... and disables Save, Cancel and the name while in flight', async () => {
			const save = deferred<RipPresetView>();
			createRipPresetMock.mockReturnValue(save.promise);
			renderForm(null);
			await typeName('Slow');
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled());
			expect(screen.getByText('Cancel')).toBeDisabled();
			expect(screen.getByTestId('preset-name')).toBeDisabled();
			save.resolve(resultPreset());
			await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument());
			expect(screen.queryByRole('button', { name: 'Saving...' })).not.toBeInTheDocument();
		});

		it('passes the returned preset to onsaved and clears the busy state', async () => {
			createRipPresetMock.mockResolvedValue(resultPreset());
			const onsaved = vi.fn();
			renderForm(null, onsaved);
			await typeName('Done');
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(onsaved).toHaveBeenCalledWith(resultPreset()));
			await waitFor(() => expect(screen.getByRole('button', { name: /^save/i })).not.toBeDisabled());
			expect(screen.getByRole('button', { name: /^save/i })).toHaveTextContent('Save');
			expect(screen.getByTestId('preset-name')).not.toBeDisabled();
			expect(screen.getByText('Cancel')).not.toBeDisabled();
		});

		it('shows an Error message, skips onsaved and clears the busy state', async () => {
			createRipPresetMock.mockRejectedValue(new Error('save boom'));
			const onsaved = vi.fn();
			renderForm(null, onsaved);
			await typeName('Bad');
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(screen.getByTestId('preset-error')).toHaveTextContent('save boom'));
			expect(onsaved).not.toHaveBeenCalled();
			expect(screen.getByRole('button', { name: /^save/i })).not.toBeDisabled();
			expect(screen.getByTestId('preset-name')).not.toBeDisabled();
		});

		it('shows "Save failed" for a non-Error rejection', async () => {
			createRipPresetMock.mockRejectedValue('nope');
			renderForm(null);
			await typeName('Odd');
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(screen.getByTestId('preset-error')).toHaveTextContent('Save failed'));
		});

		it('clears the earlier error line while a later submit runs', async () => {
			createRipPresetMock.mockRejectedValueOnce(new Error('first fail'));
			const retry = deferred<RipPresetView>();
			createRipPresetMock.mockReturnValueOnce(retry.promise);
			renderForm(null);
			await typeName('Again');
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(screen.getByTestId('preset-error')).toBeInTheDocument());
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(screen.queryByTestId('preset-error')).not.toBeInTheDocument());
			retry.resolve(resultPreset());
			await waitFor(() => expect(screen.getByRole('button', { name: /^save/i })).not.toBeDisabled());
		});

		it('calls the onsaved current when the save resolves, not the one at submit', async () => {
			const save = deferred<RipPresetView>();
			createRipPresetMock.mockReturnValue(save.promise);
			const first = vi.fn();
			const second = vi.fn();
			const { rerender } = renderForm(null, first);
			await typeName('Swap');
			await fireEvent.click(screen.getByRole('button', { name: /^save/i }));
			await waitFor(() => expect(createRipPresetMock).toHaveBeenCalledTimes(1));
			await rerender({ preset: null, onsaved: second });
			save.resolve(resultPreset());
			await waitFor(() => expect(second).toHaveBeenCalledWith(resultPreset()));
			expect(first).not.toHaveBeenCalled();
		});
	});
});
