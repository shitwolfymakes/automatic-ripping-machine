import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TranscodePresetForm from '../TranscodePresetForm.svelte';
import { createTranscodePreset, updateTranscodePreset } from '$lib/api/transcodePresets';
import type { TranscodePresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/transcodePresets', () => ({
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn()
}));

const createMock = vi.mocked(createTranscodePreset);
const updateMock = vi.mocked(updateTranscodePreset);

function makePreset(overrides: Partial<TranscodePresetView> = {}): TranscodePresetView {
	return {
		id: 'tpr_1',
		name: 'My preset',
		media_type: 'movie',
		is_builtin: false,
		tool: 'handbrake',
		preset_ref: null,
		preset_json: null,
		container: 'mkv',
		codec: null,
		hw_preference: null,
		extra_args: null,
		created_by_user_id: 'user_1',
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...overrides
	} as TranscodePresetView;
}

function resultPreset(): TranscodePresetView {
	return makePreset({ id: 'saved_1' });
}

describe('TranscodePresetForm', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('create mode', () => {
		it('renders all selects with enum options and an enabled media_type', () => {
			renderComponent(TranscodePresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() }
			});

			const mediaType = screen.getByTestId('tp-media-type') as HTMLSelectElement;
			const tool = screen.getByTestId('tp-tool') as HTMLSelectElement;
			const container = screen.getByTestId('tp-container') as HTMLSelectElement;
			const codec = screen.getByTestId('tp-codec') as HTMLSelectElement;
			const hw = screen.getByTestId('tp-hw-preference') as HTMLSelectElement;

			expect(mediaType).not.toBeDisabled();

			const optionValues = (el: HTMLSelectElement) => Array.from(el.options).map((o) => o.value);
			expect(optionValues(mediaType)).toEqual(['movie', 'tv', 'music', 'data', 'iso']);
			expect(optionValues(tool)).toEqual(['handbrake', 'abcde', 'none']);
			expect(optionValues(container)).toEqual([
				'mkv', 'mp4', 'webm', 'flac', 'mp3', 'ogg', 'iso', 'none'
			]);
			expect(optionValues(codec)).toEqual(['', 'h264', 'h265', 'av1']);
			expect(optionValues(hw)).toEqual(['', 'cpu_only', 'any']);
		});

		it('submits the full create body, empty optionals as null', async () => {
			createMock.mockResolvedValue(resultPreset());
			const onsaved = vi.fn();
			renderComponent(TranscodePresetForm, {
				props: { preset: null, onsaved, oncancel: vi.fn() }
			});

			await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });
			await fireEvent.change(screen.getByTestId('tp-media-type'), { target: { value: 'tv' } });
			await fireEvent.change(screen.getByTestId('tp-tool'), { target: { value: 'handbrake' } });
			await fireEvent.change(screen.getByTestId('tp-container'), { target: { value: 'mp4' } });
			await fireEvent.click(screen.getByTestId('tp-submit'));

			await waitFor(() => {
				expect(createMock).toHaveBeenCalledWith({
					name: 'HQ',
					media_type: 'tv',
					tool: 'handbrake',
					preset_ref: null,
					container: 'mp4',
					codec: null,
					hw_preference: null,
					extra_args: null
				});
				expect(onsaved).toHaveBeenCalledWith(resultPreset());
			});
		});

		it('submits codec / preset_ref / hw_preference / extra_args when set', async () => {
			createMock.mockResolvedValue(resultPreset());
			renderComponent(TranscodePresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() }
			});

			await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'Full' } });
			await fireEvent.input(screen.getByTestId('tp-preset-ref'), { target: { value: 'Fast 1080p30' } });
			await fireEvent.change(screen.getByTestId('tp-codec'), { target: { value: 'h265' } });
			await fireEvent.change(screen.getByTestId('tp-hw-preference'), { target: { value: 'any' } });
			await fireEvent.input(screen.getByTestId('tp-extra-args'), { target: { value: '--turbo' } });
			await fireEvent.click(screen.getByTestId('tp-submit'));

			await waitFor(() => {
				expect(createMock).toHaveBeenCalledWith({
					name: 'Full',
					media_type: 'movie',
					tool: 'handbrake',
					preset_ref: 'Fast 1080p30',
					container: 'mkv',
					codec: 'h265',
					hw_preference: 'any',
					extra_args: '--turbo'
				});
			});
		});
	});

	describe('edit mode — custom preset', () => {
		it('seeds fields, disables media_type, and submits without media_type', async () => {
			updateMock.mockResolvedValue(resultPreset());
			const preset = makePreset({
				id: 'tpr_99',
				name: 'Existing',
				media_type: 'music',
				tool: 'abcde',
				preset_ref: 'flac',
				container: 'flac',
				codec: 'h264',
				hw_preference: 'cpu_only',
				extra_args: '-q 5',
				is_builtin: false
			});
			renderComponent(TranscodePresetForm, {
				props: { preset, onsaved: vi.fn(), oncancel: vi.fn() }
			});

			const name = screen.getByTestId('tp-name') as HTMLInputElement;
			const mediaType = screen.getByTestId('tp-media-type') as HTMLSelectElement;
			expect(name.value).toBe('Existing');
			expect(mediaType.value).toBe('music');
			expect(mediaType).toBeDisabled();
			expect((screen.getByTestId('tp-codec') as HTMLSelectElement).value).toBe('h264');

			await fireEvent.input(name, { target: { value: 'Renamed' } });
			await fireEvent.click(screen.getByTestId('tp-submit'));

			await waitFor(() => {
				expect(updateMock).toHaveBeenCalledWith('tpr_99', {
					name: 'Renamed',
					tool: 'abcde',
					preset_ref: 'flac',
					container: 'flac',
					codec: 'h264',
					hw_preference: 'cpu_only',
					extra_args: '-q 5'
				});
			});
			const body = updateMock.mock.calls[0][1];
			expect('media_type' in body).toBe(false);
		});
	});

	describe('edit mode — built-in preset', () => {
		it('only the name is editable, note shown, submits name only', async () => {
			updateMock.mockResolvedValue(resultPreset());
			const onsaved = vi.fn();
			const preset = makePreset({ id: 'builtin_1', name: 'Stock', is_builtin: true });
			renderComponent(TranscodePresetForm, {
				props: { preset, onsaved, oncancel: vi.fn() }
			});

			expect(screen.getByTestId('tp-media-type')).toBeDisabled();
			expect(screen.getByTestId('tp-tool')).toBeDisabled();
			expect(screen.getByTestId('tp-container')).toBeDisabled();
			expect(screen.getByTestId('tp-codec')).toBeDisabled();
			expect(screen.getByTestId('tp-hw-preference')).toBeDisabled();
			expect(screen.getByTestId('tp-preset-ref')).toBeDisabled();
			expect(screen.getByTestId('tp-extra-args')).toBeDisabled();
			expect(
				screen.getByText('Built-in preset - only the name is editable.')
			).toBeInTheDocument();

			await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'Stock renamed' } });
			await fireEvent.click(screen.getByTestId('tp-submit'));

			await waitFor(() => {
				expect(updateMock).toHaveBeenCalledWith('builtin_1', { name: 'Stock renamed' });
				expect(onsaved).toHaveBeenCalledWith(resultPreset());
			});
		});
	});

	describe('validation', () => {
		it('disables submit when name is empty', () => {
			renderComponent(TranscodePresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() }
			});
			expect(screen.getByTestId('tp-submit')).toBeDisabled();
		});
	});

	describe('cancel', () => {
		it('fires oncancel', async () => {
			const oncancel = vi.fn();
			renderComponent(TranscodePresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel }
			});
			await fireEvent.click(screen.getByText('Cancel'));
			expect(oncancel).toHaveBeenCalledTimes(1);
		});
	});

	describe('error handling', () => {
		it('shows the thrown error message inline', async () => {
			createMock.mockRejectedValue(new Error('save boom'));
			renderComponent(TranscodePresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() }
			});
			await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'X' } });
			await fireEvent.click(screen.getByTestId('tp-submit'));
			await waitFor(() => expect(screen.getByText('save boom')).toBeInTheDocument());
		});
	});
});
