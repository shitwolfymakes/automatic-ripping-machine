import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TranscodePresetForm from '../TranscodePresetForm.svelte';
import { createTranscodePreset, updateTranscodePreset } from '$lib/api/transcodePresets';
import type { EncoderAvailabilityView, TranscodePresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/transcodePresets', () => ({
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn()
}));

// One entry per group, in catalog order, standing in for the full
// arm_common.encoders catalog: qsv_h264 unavailable (no verified device),
// any_h265 available but would currently fall back to the CPU, vaapi_h264
// runs over ffmpeg directly rather than a HandBrake preset.
const ENCODERS: EncoderAvailabilityView[] = [
	{
		id: 'preset',
		label: "HandBrake preset's own encoder",
		group: 'preset',
		engine: 'handbrake',
		kind: 'preset',
		vendor: null,
		codec: null,
		available: true,
		reason: null
	},
	{
		id: 'cpu_h264',
		label: 'CPU H.264',
		group: 'cpu',
		engine: 'handbrake',
		kind: 'cpu',
		vendor: null,
		codec: 'h264',
		available: true,
		reason: null
	},
	{
		id: 'any_h265',
		label: 'Any GPU H.265',
		group: 'any',
		engine: 'handbrake',
		kind: 'any',
		vendor: null,
		codec: 'h265',
		available: true,
		reason: 'no verified GPU; runs on the CPU'
	},
	{
		id: 'qsv_h264',
		label: 'Intel QSV H.264',
		group: 'qsv',
		engine: 'handbrake',
		kind: 'gpu',
		vendor: 'qsv',
		codec: 'h264',
		available: false,
		reason: 'no enabled device has verified qsv_h264'
	},
	{
		id: 'nvenc_h264',
		label: 'NVIDIA NVENC H.264',
		group: 'nvenc',
		engine: 'handbrake',
		kind: 'gpu',
		vendor: 'nvenc',
		codec: 'h264',
		available: true,
		reason: null
	},
	{
		id: 'vaapi_h264',
		label: 'AMD VAAPI H.264',
		group: 'vaapi',
		engine: 'ffmpeg_vaapi',
		kind: 'gpu',
		vendor: 'vaapi',
		codec: 'h264',
		available: true,
		reason: null
	}
];

const mockFetchEncoders = vi.fn(() => Promise.resolve(ENCODERS));
vi.mock('$lib/api/encoders', () => ({ fetchEncoders: () => mockFetchEncoders() }));

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
		it('renders all selects with enum options and an enabled media_type', async () => {
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

			await waitFor(() =>
				expect(optionValues(encoder)).toEqual([
					'preset',
					'cpu_h264',
					'any_h265',
					'qsv_h264',
					'nvenc_h264',
					'vaapi_h264'
				])
			);
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

			const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
			await waitFor(() => expect(encoder.querySelector('option[value="any_h265"]')).not.toBeNull());

			await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'Full' } });
			await fireEvent.input(screen.getByTestId('tp-preset-ref'), { target: { value: 'Fast 1080p30' } });
			await fireEvent.change(encoder, { target: { value: 'any_h265' } });
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
				tool: 'handbrake',
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

			const encoderSelect = screen.getByTestId('tp-encoder') as HTMLSelectElement;
			await waitFor(() => expect(encoderSelect.value).toBe('cpu_h264'));

			await fireEvent.input(name, { target: { value: 'Renamed' } });
			await fireEvent.click(screen.getByTestId('tp-submit'));

			await waitFor(() => {
				expect(updateMock).toHaveBeenCalledWith('tpr_99', {
					name: 'Renamed',
					tool: 'handbrake',
					preset_ref: 'flac',
					container: 'flac',
					encoder: 'cpu_h264',
					extra_args: '-q 5'
				});
			});
			const body = updateMock.mock.calls[0][1];
			expect('media_type' in body).toBe(false);
		});

		it('corrects a stale non-preset encoder to preset for an abcde/none preset before saving', async () => {
			updateMock.mockResolvedValue(resultPreset());
			const preset = makePreset({
				id: 'tpr_100',
				tool: 'abcde',
				container: 'flac',
				encoder: 'cpu_h264',
				is_builtin: false
			});
			renderComponent(TranscodePresetForm, {
				props: { preset, onsaved: vi.fn(), oncancel: vi.fn() }
			});

			const encoderSelect = screen.getByTestId('tp-encoder') as HTMLSelectElement;
			await waitFor(() => expect(encoderSelect.querySelector('option[value="preset"]')).not.toBeNull());
			expect(encoderSelect).toBeDisabled();
			expect(encoderSelect.value).toBe('preset');

			await fireEvent.click(screen.getByTestId('tp-submit'));

			await waitFor(() =>
				expect(updateMock).toHaveBeenCalledWith(
					'tpr_100',
					expect.objectContaining({ encoder: 'preset' })
				)
			);
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

describe('encoder picker', () => {
	afterEach(() => cleanup());

	it('groups options into optgroups in catalog order', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		await waitFor(() => expect(encoder.querySelectorAll('optgroup')).toHaveLength(6));
		const groupLabels = Array.from(encoder.querySelectorAll('optgroup')).map((g) => g.label);
		expect(groupLabels).toEqual([
			"HandBrake preset's own",
			'CPU',
			'Any GPU',
			'Intel QSV',
			'NVIDIA NVENC',
			'AMD VAAPI'
		]);
	});

	it('disables an unavailable encoder option and shows its reason', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		await waitFor(() => expect(encoder.querySelector('option[value="qsv_h264"]')).not.toBeNull());
		const option = encoder.querySelector('option[value="qsv_h264"]') as HTMLOptionElement;
		expect(option.disabled).toBe(true);
		expect(option.textContent).toContain('no enabled device has verified qsv_h264');
	});

	it('locks the encoder to preset and disables it when the tool is abcde', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		await fireEvent.change(screen.getByTestId('tp-tool'), { target: { value: 'abcde' } });
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		expect(encoder).toBeDisabled();
		expect(encoder.value).toBe('preset');
	});

	it('locks the encoder to preset and disables it when the tool is none', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		await fireEvent.change(screen.getByTestId('tp-tool'), { target: { value: 'none' } });
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		expect(encoder).toBeDisabled();
		expect(encoder.value).toBe('preset');
	});

	it('resets a chosen encoder back to preset when the tool changes to abcde', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		await waitFor(() => expect(encoder.querySelector('option[value="any_h265"]')).not.toBeNull());
		await fireEvent.change(encoder, { target: { value: 'any_h265' } });
		expect(encoder.value).toBe('any_h265');

		await fireEvent.change(screen.getByTestId('tp-tool'), { target: { value: 'abcde' } });
		expect(encoder.value).toBe('preset');
		expect(encoder).toBeDisabled();
	});

	it('shows the "not used by this encoder" note and relabels extra args for a vaapi encoder', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		await waitFor(() => expect(encoder.querySelector('option[value="vaapi_h264"]')).not.toBeNull());
		expect(screen.queryByTestId('tp-preset-ref-note')).not.toBeInTheDocument();
		expect(screen.queryByText('ffmpeg arguments')).not.toBeInTheDocument();

		await fireEvent.change(encoder, { target: { value: 'vaapi_h264' } });

		expect(screen.getByTestId('tp-preset-ref-note').textContent).toContain('Not used by this encoder');
		expect(screen.getByText('ffmpeg arguments')).toBeInTheDocument();
	});
});

describe('encoder availability refresh', () => {
	afterEach(() => cleanup());

	it('refetches the catalog every time the form opens, even when it is cached', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		await waitFor(() => expect(mockFetchEncoders).toHaveBeenCalled());
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		await waitFor(() => expect(encoder.querySelector('option[value="any_h265"]')).not.toBeNull());
		cleanup();
		mockFetchEncoders.mockClear();

		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		await waitFor(() => expect(mockFetchEncoders).toHaveBeenCalledTimes(1));
	});
});

describe('any-GPU note', () => {
	afterEach(() => cleanup());

	const NOTE =
		'HandBrake preset settings (scaling, filters, audio) apply on CPU, NVENC and QSV, but not when the job runs on an AMD (VAAPI) device.';

	it('shows the note only while an any_* encoder is selected', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		await waitFor(() => expect(encoder.querySelector('option[value="any_h265"]')).not.toBeNull());
		expect(screen.queryByTestId('tp-encoder-any-note')).not.toBeInTheDocument();

		await fireEvent.change(encoder, { target: { value: 'any_h265' } });
		expect(screen.getByTestId('tp-encoder-any-note').textContent?.replace(/\s+/g, ' ').trim()).toBe(NOTE);

		await fireEvent.change(encoder, { target: { value: 'nvenc_h264' } });
		expect(screen.queryByTestId('tp-encoder-any-note')).not.toBeInTheDocument();
	});
});

describe('hardware-name hint', () => {
	afterEach(() => cleanup());

	it('shows the hint when the preset name mentions a hardware encoder and the encoder is preset', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-preset-ref'), { target: { value: 'H.265 NVENC 1080p' } });
		expect(screen.getByTestId('tp-encoder-hint').textContent).toBe(
			'This HandBrake preset uses a hardware encoder; choose the matching encoder above or ARM will not attach a GPU.'
		);
	});

	it('matches QSV/VCN/VCE case-insensitively', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-preset-ref'), { target: { value: 'fast 1080p qsv' } });
		expect(screen.getByTestId('tp-encoder-hint')).toBeInTheDocument();
	});

	it('does not show the hint for a plain preset name', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-preset-ref'), { target: { value: 'Fast 1080p30' } });
		expect(screen.queryByTestId('tp-encoder-hint')).not.toBeInTheDocument();
	});

	it('does not show the hint once a matching encoder is chosen', async () => {
		renderComponent(TranscodePresetForm, { props: { preset: null, oncancel: vi.fn(), onsaved: vi.fn() } });
		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		await waitFor(() => expect(encoder.querySelector('option[value="nvenc_h264"]')).not.toBeNull());
		await fireEvent.input(screen.getByTestId('tp-preset-ref'), { target: { value: 'H.264 NVENC 1080p' } });
		expect(screen.getByTestId('tp-encoder-hint')).toBeInTheDocument();

		await fireEvent.change(encoder, { target: { value: 'nvenc_h264' } });
		expect(screen.queryByTestId('tp-encoder-hint')).not.toBeInTheDocument();
	});
});
