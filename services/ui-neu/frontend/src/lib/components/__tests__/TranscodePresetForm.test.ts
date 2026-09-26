import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TranscodePresetForm from '../TranscodePresetForm.svelte';
import { createTranscodePreset, updateTranscodePreset } from '$lib/api/transcodePresets';
import type { TranscodePresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/transcodePresets', () => ({
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn()
}));

const mockFetchGpus = vi.fn(() =>
	Promise.resolve([
		{
			id: 'gpu_1',
			vendor: 'qsv',
			device_path: '/dev/dri/renderD128',
			encoder_kinds: ['h264', 'h265'],
			status: 'available',
			enabled: true,
			claimed_by_task_id: null,
			last_seen_at: null
		},
		{
			id: 'gpu_2',
			vendor: 'vaapi',
			device_path: '/dev/dri/renderD129',
			encoder_kinds: ['h264'],
			status: 'available',
			enabled: false,
			claimed_by_task_id: null,
			last_seen_at: null
		}
	])
);
vi.mock('$lib/api/gpus', () => ({ fetchGpus: () => mockFetchGpus() }));

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
		encoder: 'preset',
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
			const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;

			expect(mediaType).not.toBeDisabled();

			const optionValues = (el: HTMLSelectElement) => Array.from(el.options).map((o) => o.value);
			expect(optionValues(mediaType)).toEqual(['movie', 'tv', 'music', 'data', 'iso']);
			expect(optionValues(tool)).toEqual(['handbrake', 'abcde', 'none']);
			expect(optionValues(container)).toEqual([
				'mkv', 'mp4', 'webm', 'flac', 'mp3', 'ogg', 'iso', 'none'
			]);
			expect(optionValues(encoder)).toEqual([
				'preset',
				'cpu_h264', 'cpu_h265', 'cpu_av1',
				'any_h264', 'any_h265', 'any_av1',
				'qsv_h264', 'qsv_h265', 'qsv_av1',
				'nvenc_h264', 'nvenc_h265', 'nvenc_av1',
				'vaapi_h264', 'vaapi_h265', 'vaapi_av1'
			]);
			expect(encoder.value).toBe('preset');
		});

		it('submits the full create body, empty optionals as null and the default encoder', async () => {
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
					encoder: 'preset',
					extra_args: null
				});
				expect(onsaved).toHaveBeenCalledWith(resultPreset());
			});
		});

		it('submits encoder / preset_ref / extra_args when set', async () => {
			createMock.mockResolvedValue(resultPreset());
			renderComponent(TranscodePresetForm, {
				props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() }
			});

			await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'Full' } });
			await fireEvent.input(screen.getByTestId('tp-preset-ref'), { target: { value: 'Fast 1080p30' } });
			await fireEvent.change(screen.getByTestId('tp-encoder'), { target: { value: 'any_h265' } });
			await fireEvent.input(screen.getByTestId('tp-extra-args'), { target: { value: '--turbo' } });
			await fireEvent.click(screen.getByTestId('tp-submit'));

			await waitFor(() => {
				expect(createMock).toHaveBeenCalledWith({
					name: 'Full',
					media_type: 'movie',
					tool: 'handbrake',
					preset_ref: 'Fast 1080p30',
					container: 'mkv',
					encoder: 'any_h265',
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
				encoder: 'cpu_h264',
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
			expect((screen.getByTestId('tp-encoder') as HTMLSelectElement).value).toBe('cpu_h264');

			await fireEvent.input(name, { target: { value: 'Renamed' } });
			await fireEvent.click(screen.getByTestId('tp-submit'));

			await waitFor(() => {
				expect(updateMock).toHaveBeenCalledWith('tpr_99', {
					name: 'Renamed',
					tool: 'abcde',
					preset_ref: 'flac',
					container: 'flac',
					encoder: 'cpu_h264',
					extra_args: '-q 5'
				});
			});
			const body = updateMock.mock.calls[0][1];
			expect('media_type' in body).toBe(false);
		});
	});

	describe('view mode — built-in preset', () => {
		it('is fully locked: all fields disabled, warning shown, no Save button', () => {
			const onsaved = vi.fn();
			const preset = makePreset({ id: 'builtin_1', name: 'Stock', is_builtin: true });
			renderComponent(TranscodePresetForm, {
				props: { preset, onsaved, oncancel: vi.fn() }
			});

			// Every field — including the name — is locked.
			expect(screen.getByTestId('tp-name')).toBeDisabled();
			expect(screen.getByTestId('tp-media-type')).toBeDisabled();
			expect(screen.getByTestId('tp-tool')).toBeDisabled();
			expect(screen.getByTestId('tp-container')).toBeDisabled();
			expect(screen.getByTestId('tp-encoder')).toBeDisabled();
			expect(screen.getByTestId('tp-preset-ref')).toBeDisabled();
			expect(screen.getByTestId('tp-extra-args')).toBeDisabled();

			// Warning banner instead of the old "only the name is editable" note.
			expect(
				screen.getByText(/built-in preset and can't be edited/i)
			).toBeInTheDocument();

			// No Save button at all; heading reads View.
			expect(screen.queryByTestId('tp-submit')).not.toBeInTheDocument();
			expect(screen.getByRole('heading', { name: /view transcode preset/i })).toBeInTheDocument();
			expect(updateMock).not.toHaveBeenCalled();
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

describe('GPU awareness (G-30/G-31)', () => {
	afterEach(() => cleanup());

	it('labels the preset choice as the HandBrake preset encoder, not default', () => {
		renderComponent(TranscodePresetForm, { props: { preset: makePreset(), oncancel: vi.fn(), onsaved: vi.fn() } });
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		const labels = Array.from(encoder.options).map((o) => o.textContent);
		expect(labels).toContain("HandBrake preset's own encoder");
		expect(labels).not.toContain('(default)');
	});

	it('shows the live inventory hint under the encoder', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: makePreset(), oncancel: vi.fn(), onsaved: vi.fn() } });
		await waitFor(() => expect(screen.getByTestId('tp-gpu-hint')).toBeInTheDocument());
		const hint = screen.getByTestId('tp-gpu-hint').textContent ?? '';
		expect(hint).toContain('QSV renderD128 (h264, h265)');
		expect(hint).toContain('VAAPI renderD129 (h264) disabled');
	});

	it('says CPU fallback when the host has no GPUs', async () => {
		mockFetchGpus.mockResolvedValueOnce([]);
		renderComponent(TranscodePresetForm, { props: { preset: makePreset(), oncancel: vi.fn(), onsaved: vi.fn() } });
		await waitFor(() =>
			expect(screen.getByTestId('tp-gpu-hint').textContent).toContain('no GPUs configured')
		);
	});
});
