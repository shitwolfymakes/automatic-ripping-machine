import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';
import type { EncoderAvailabilityView, HandbrakeSchemaSlimView, TranscodePresetView } from '$lib/types/api.gen';
import plexImport from '$lib/handbrake/__tests__/fixtures/plex-import-response.json';
import fixture from '$lib/handbrake/__tests__/fixtures/slim-schema.json';
import { ApiError } from '$lib/api/client';
import { fetchBuiltinPreset, fetchHandbrakeSchema, refreshHandbrakeSchema } from '$lib/api/handbrakeSchema';
import { createTranscodePreset, parseHandbrakeImport, updateTranscodePreset } from '$lib/api/transcodePresets';
import { handbrakeSchema } from '$lib/stores/handbrakeSchema.svelte';
import { stopEncoderEvents } from '$lib/stores/encoders.svelte';
import PresetSidebar from '../PresetSidebar.svelte';

vi.mock('$lib/api/handbrakeSchema', () => ({
	fetchHandbrakeSchema: vi.fn(),
	fetchBuiltinPreset: vi.fn(),
	refreshHandbrakeSchema: vi.fn()
}));
vi.mock('$lib/api/transcodePresets', () => ({
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn(),
	parseHandbrakeImport: vi.fn()
}));
const encoders = vi.hoisted(() => ({ list: [] as unknown[] }));
vi.mock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(encoders.list) }));
vi.mock('$lib/api/ws', () => ({ wsClient: { start: vi.fn(), subscribe: vi.fn(() => () => {}) } }));

const schema = fixture as unknown as HandbrakeSchemaSlimView;

function enc(id: string, over: Partial<EncoderAvailabilityView> = {}): EncoderAvailabilityView {
	return {
		id,
		label: id,
		group: 'any',
		engine: 'handbrake',
		kind: 'any',
		vendor: null,
		codec: null,
		available: true,
		reason: null,
		...over
	};
}
const ENCODERS = [
	enc('preset', { group: 'preset', kind: 'preset' }),
	enc('any_h264'),
	enc('any_h265'),
	enc('nvenc_h264', { group: 'nvenc', kind: 'gpu', vendor: 'nvenc', label: 'NVIDIA H.264' }),
	enc('vaapi_h264', { group: 'vaapi', kind: 'gpu', vendor: 'vaapi', engine: 'ffmpeg_vaapi', label: 'AMD H.264' })
];

function preset(over: Partial<TranscodePresetView> = {}): TranscodePresetView {
	return {
		id: 't1',
		name: 'Movies',
		media_type: 'movie',
		is_builtin: false,
		tool: 'handbrake',
		preset_ref: null,
		handbrake_settings: null,
		issues: [],
		host_notes: [],
		container: 'mkv',
		encoder: 'any_h264',
		extra_args: null,
		created_by_user_id: null,
		created_at: null,
		updated_at: null,
		...over
	};
}

function mount(
	props: Partial<{
		preset: TranscodePresetView | null;
		mode: 'new' | 'edit' | 'view';
		usage: number;
		onclone: (p: TranscodePresetView) => void;
	}>
) {
	const onclose = vi.fn();
	const onsaved = vi.fn();
	renderComponent(PresetSidebar, { props: { preset: null, mode: 'new', usage: 0, onclose, onsaved, ...props } });
	return { onclose, onsaved };
}

async function ready() {
	await screen.findByRole('tablist');
}

async function openTab(name: string) {
	await fireEvent.click(screen.getByRole('tab', { name: new RegExp(`^${name}`) }));
}

function save() {
	return fireEvent.click(screen.getByRole('button', { name: 'Save' }));
}

beforeEach(() => {
	handbrakeSchema.reset();
	encoders.list = ENCODERS;
	vi.mocked(fetchHandbrakeSchema).mockResolvedValue(schema);
	vi.mocked(fetchBuiltinPreset).mockResolvedValue({ PictureHeight: 1080, VideoEncoder: 'x264' });
});

afterEach(() => {
	cleanup();
	stopEncoderEvents();
	vi.clearAllMocks();
});

describe('header', () => {
	it.each([
		['new', 'New transcode preset'],
		['edit', 'Edit transcode preset'],
		['view', 'View transcode preset']
	] as const)('titles %s mode "%s"', async (mode, title) => {
		mount({ mode, preset: mode === 'new' ? null : preset() });
		expect(await screen.findByRole('dialog', { name: title })).toBeInTheDocument();
	});

	it('offers Import HandBrake preset, disabled in view mode', () => {
		mount({ mode: 'view', preset: preset() });
		expect(screen.getByRole('button', { name: 'Import HandBrake preset' })).toBeDisabled();
	});

	it('Close and Cancel call onclose', async () => {
		const { onclose } = mount({});
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(onclose).toHaveBeenCalledTimes(1);
	});
});

describe('view mode', () => {
	it('is read-only with no Save', async () => {
		const { onclose } = mount({ mode: 'view', preset: preset({ is_builtin: true }) });
		await ready();
		expect(screen.getByTestId('tp-name')).toBeDisabled();
		expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
		expect(screen.getByText(/built-in preset and can't be edited/)).toBeInTheDocument();
		await openTab('Chapters');
		expect(screen.getByLabelText('Create chapter markers')).toBeDisabled();
		// The header's close button, then the footer's Close.
		const [, footerClose] = screen.getAllByRole('button', { name: 'Close' });
		await fireEvent.click(footerClose);
		expect(onclose).toHaveBeenCalledTimes(1);
	});
});

describe('base preset', () => {
	it('fetches a built-in once per name and shows its values as inherited', async () => {
		mount({ mode: 'edit', preset: preset() });
		await ready();
		const base = screen.getByTestId('tp-preset-ref');
		expect(within(base).getByRole('option', { name: 'None (HandBrake defaults)' })).toBeInTheDocument();
		await fireEvent.change(base, { target: { value: 'Fast 1080p30' } });
		await waitFor(() => expect(fetchBuiltinPreset).toHaveBeenCalledWith('Fast 1080p30'));
		await openTab('Dimensions');
		await waitFor(() => expect(screen.getByLabelText('Maximum height')).toHaveAttribute('placeholder', '1080'));
		await fireEvent.change(base, { target: { value: '' } });
		expect(screen.getByLabelText('Maximum height')).toHaveAttribute('placeholder', '0');
		await fireEvent.change(base, { target: { value: 'Fast 1080p30' } });
		expect(fetchBuiltinPreset).toHaveBeenCalledTimes(1);
	});

	it('loads the stored base on open and inherits defaults when the fetch fails', async () => {
		vi.mocked(fetchBuiltinPreset).mockRejectedValue(new Error('404'));
		mount({ mode: 'edit', preset: preset({ preset_ref: 'Fast 480p30' }) });
		await ready();
		await waitFor(() => expect(fetchBuiltinPreset).toHaveBeenCalledWith('Fast 480p30'));
		await openTab('Dimensions');
		expect(screen.getByLabelText('Maximum height')).toHaveAttribute('placeholder', '0');
	});

	it('does not fetch a profile name for abcde', async () => {
		mount({ mode: 'edit', preset: preset({ tool: 'abcde', encoder: 'preset', preset_ref: 'flac' }) });
		await waitFor(() => expect(fetchHandbrakeSchema).toHaveBeenCalled());
		expect(fetchBuiltinPreset).not.toHaveBeenCalled();
	});
});

describe('which settings show', () => {
	it('a pinned VAAPI encoder hides the tabs and says why', async () => {
		mount({ mode: 'edit', preset: preset({ encoder: 'vaapi_h264' }) });
		expect(
			await screen.findByText(
				'HandBrake settings do not apply to AMD VAAPI encoders. Only the container and extra args are used.'
			)
		).toBeInTheDocument();
		expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
	});

	it('a tool other than HandBrake shows neither tabs nor the note', async () => {
		mount({ mode: 'edit', preset: preset({ tool: 'none', encoder: 'preset' }) });
		await waitFor(() => expect(fetchHandbrakeSchema).toHaveBeenCalled());
		expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
		expect(screen.queryByText(/do not apply to AMD/)).not.toBeInTheDocument();
	});

	it('the Video tab lists common keys, then a card per reachable encoder, with the AMD note', async () => {
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await openTab('Video');
		expect(screen.getByRole('heading', { name: 'All encoders' })).toBeInTheDocument();
		expect(screen.getByRole('heading', { name: 'Per encoder' })).toBeInTheDocument();
		expect(screen.getByLabelText('Rate control mode')).toBeInTheDocument();
		await waitFor(() => expect(screen.getByRole('region', { name: 'NVIDIA H.264' })).toBeInTheDocument());
		expect(screen.getByRole('region', { name: 'x264' })).toBeInTheDocument();
		expect(
			screen.getByText(
				'AMD devices encode with ffmpeg, which cannot apply these settings. Because this preset has HandBrake settings, it skips AMD devices and uses another GPU or the CPU.'
			)
		).toBeInTheDocument();
	});

	it('the Video tab sections each carry a line saying what they hold', async () => {
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await openTab('Video');
		expect(screen.getByText('These apply whichever device runs the encode.')).toBeInTheDocument();
		expect(
			screen.getByText(
				'any_h264 can land on the encoders below. Each keeps its own speed preset, profile, level and quality, because the values differ between them.'
			)
		).toBeInTheDocument();
	});

	it('a tab shows a group heading only for a group with a visible field', async () => {
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await openTab('Dimensions');
		for (const group of ['Size', 'Cropping', 'Pixel aspect', 'Padding', 'Orientation']) {
			expect(screen.getByRole('heading', { name: group })).toBeInTheDocument();
		}
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'Rotate' } });
		expect(screen.getByRole('heading', { name: 'Orientation' })).toBeInTheDocument();
		expect(screen.queryByRole('heading', { name: 'Size' })).toBeNull();
	});

	it('an encoder card field links to its family docs page', async () => {
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await openTab('Video');
		const card = await screen.findByRole('region', { name: 'NVIDIA H.264' });
		const link = within(card).getAllByRole('link')[0];
		expect(link).toHaveAttribute('href', 'https://handbrake.fr/docs/en/latest/technical/video-nvenc.html');
	});

	it('names the preset as This preset when the encoder is not in the catalog', async () => {
		encoders.list = [];
		mount({ mode: 'edit', preset: preset({ encoder: 'nvenc_h264' }) });
		await ready();
		await openTab('Video');
		expect(screen.getByText(/^This preset can land on the encoders below/)).toBeInTheDocument();
	});

	it('x264 advanced options appear on the x264 card only', async () => {
		const encoders = { x264: { x264UseAdvancedOptions: true } };
		mount({ mode: 'edit', preset: preset({ handbrake_settings: { common: {}, encoders } }) });
		await ready();
		await openTab('Video');
		await screen.findByRole('region', { name: 'x264' });
		for (const label of ['Use x264 advanced options', 'x264 advanced options']) {
			const found = screen.getAllByLabelText(label);
			expect(found).toHaveLength(1);
			expect(within(screen.getByRole('region', { name: 'x264' })).getByLabelText(label)).toBe(found[0]);
			expect(within(screen.getByRole('region', { name: 'NVIDIA H.264' })).queryByLabelText(label)).toBeNull();
		}
	});

	it('an expanded card shows the encoder default as inherited', async () => {
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await openTab('Video');
		const card = await screen.findByRole('region', { name: 'x264' });
		expect((within(card).getByLabelText('Encoder preset') as HTMLSelectElement).value).toBe('medium');
	});

	it('Changed only hides fields and cards with nothing stored', async () => {
		mount({
			mode: 'edit',
			preset: preset({ handbrake_settings: { common: {}, encoders: { x264: { VideoTune: 'film' } } } })
		});
		await ready();
		await openTab('Video');
		await fireEvent.click(screen.getByLabelText('Changed only'));
		expect(screen.queryByLabelText('Rate control mode')).not.toBeInTheDocument();
		expect(screen.getByRole('region', { name: 'x264' })).toBeInTheDocument();
		expect(screen.queryByRole('region', { name: 'NVIDIA H.264' })).not.toBeInTheDocument();
	});

	it('Changed only drops the All encoders heading when no common video key is stored', async () => {
		mount({
			mode: 'edit',
			preset: preset({ handbrake_settings: { common: {}, encoders: { x264: { VideoTune: 'film' } } } })
		});
		await ready();
		await openTab('Video');
		await fireEvent.click(screen.getByLabelText('Changed only'));
		expect(screen.queryByRole('heading', { name: 'All encoders' })).not.toBeInTheDocument();
		expect(screen.getByRole('heading', { name: 'Per encoder' })).toBeInTheDocument();
	});

	async function filterBy(text: string) {
		await fireEvent.input(screen.getByPlaceholderText('Filter settings'), { target: { value: text } });
	}
	const fieldLabels = (el: HTMLElement) =>
		Array.from(el.querySelectorAll('label.field-label')).map((l) => l.textContent);

	it('filtering by "track" shows only matching inputs, inside each audio track too, and nothing on Video', async () => {
		const AudioList = [{ AudioEncoder: 'av_aac' }, { AudioEncoder: 'ac3' }];
		mount({ mode: 'edit', preset: preset({ handbrake_settings: { common: { AudioList }, encoders: {} } }) });
		await ready();
		await filterBy('track');
		expect(screen.getByRole('tab', { name: /^Audio/ })).toHaveAttribute('aria-selected', 'true');
		expect(screen.getByRole('tab', { name: /^Audio/ })).toHaveTextContent('9');
		expect(screen.getByLabelText('Pass through track names')).toBeInTheDocument();
		expect(screen.queryByLabelText('Fallback encoder')).not.toBeInTheDocument();
		for (const n of [1, 2]) {
			expect(fieldLabels(screen.getByRole('region', { name: `Audio track ${n}` }))).toEqual([
				'Use quality instead of bitrate',
				'Gain (dB)',
				'Dynamic range compression'
			]);
		}
		await openTab('Video');
		expect(screen.getByRole('tab', { name: /^Video/ })).toHaveTextContent('0');
		expect(screen.queryByRole('heading', { name: 'All encoders' })).not.toBeInTheDocument();
		expect(screen.queryByRole('heading', { name: 'Per encoder' })).not.toBeInTheDocument();
		expect(screen.queryByRole('region', { name: 'x264' })).not.toBeInTheDocument();
		expect(screen.queryByText(/do not apply to AMD|AMD devices encode/)).not.toBeInTheDocument();
	});

	it('filtering by "gain" shows each track with its gain only', async () => {
		const AudioList = [{ AudioEncoder: 'av_aac' }, { AudioEncoder: 'ac3' }];
		mount({ mode: 'edit', preset: preset({ handbrake_settings: { common: { AudioList }, encoders: {} } }) });
		await ready();
		await filterBy('gain');
		expect(screen.getByRole('tab', { name: /^Audio/ })).toHaveTextContent('2');
		for (const n of [1, 2]) {
			expect(fieldLabels(screen.getByRole('region', { name: `Audio track ${n}` }))).toEqual(['Gain (dB)']);
		}
	});

	it('filtering by "preset" shows only the encoder preset inside each card', async () => {
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await openTab('Video');
		await filterBy('preset');
		const x264 = await screen.findByRole('region', { name: 'x264' });
		expect(fieldLabels(x264)).toEqual(['Encoder preset']);
		expect(fieldLabels(screen.getByRole('region', { name: 'NVIDIA H.264' }))).toEqual(['Encoder preset']);
		expect(screen.queryByRole('heading', { name: 'All encoders' })).not.toBeInTheDocument();
		expect(screen.getByRole('heading', { name: 'Per encoder' })).toBeInTheDocument();
		expect(screen.getByRole('tab', { name: /^Video/ })).toHaveTextContent('2');
	});

	it('counts a collapsed card once Set values anyway opens it', async () => {
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await openTab('Video');
		await filterBy('preset');
		const qsv = await screen.findByRole('region', { name: 'qsv_h264' });
		expect(screen.getByRole('tab', { name: /^Video/ })).toHaveTextContent('2');
		await fireEvent.click(within(qsv).getByRole('button', { name: 'Set values anyway' }));
		expect(fieldLabels(screen.getByRole('region', { name: 'qsv_h264' }))).toEqual(['Encoder preset']);
		expect(screen.getByRole('tab', { name: /^Video/ })).toHaveTextContent('3');
	});

	it('hides a gated field that holds a value, and still saves the value', async () => {
		vi.mocked(updateTranscodePreset).mockResolvedValue(preset());
		const common = { VideoQualityType: 2, VideoAvgBitrate: 5000 };
		mount({ mode: 'edit', preset: preset({ handbrake_settings: { common, encoders: {} } }) });
		await ready();
		await openTab('Video');
		expect(screen.queryByLabelText('Average bitrate (kbit/s)')).not.toBeInTheDocument();
		expect(screen.queryByLabelText('Multi-pass encoding')).not.toBeInTheDocument();
		await save();
		await waitFor(() => expect(updateTranscodePreset).toHaveBeenCalled());
		expect(vi.mocked(updateTranscodePreset).mock.calls[0][1].handbrake_settings?.common?.VideoAvgBitrate).toBe(5000);
	});

	it('the Audio tab edits the output tracks', async () => {
		vi.mocked(updateTranscodePreset).mockResolvedValue(preset());
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await openTab('Audio');
		await fireEvent.click(screen.getByRole('button', { name: /add track/i }));
		await save();
		await waitFor(() => expect(updateTranscodePreset).toHaveBeenCalled());
		const body = vi.mocked(updateTranscodePreset).mock.calls[0][1];
		expect(Array.isArray(body.handbrake_settings?.common?.AudioList)).toBe(true);
	});

	it('the Audio tab starts from the base preset tracks', async () => {
		vi.mocked(fetchBuiltinPreset).mockResolvedValue({ AudioList: [{ AudioEncoder: 'av_aac' }] });
		mount({ mode: 'edit', preset: preset({ preset_ref: 'Fast 1080p30' }) });
		await ready();
		await openTab('Audio');
		expect(await screen.findByRole('region', { name: 'Audio track 1' })).toBeInTheDocument();
	});
});

describe('editing and saving', () => {
	it('creates a new preset with its settings and hands it to onsaved', async () => {
		const saved = preset({ id: 't9' });
		vi.mocked(createTranscodePreset).mockResolvedValue(saved);
		const { onsaved } = mount({});
		await ready();
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'New one' } });
		await openTab('Chapters');
		await fireEvent.click(screen.getByLabelText('Create chapter markers'));
		await save();
		await waitFor(() => expect(onsaved).toHaveBeenCalledWith(saved));
		expect(createTranscodePreset).toHaveBeenCalledWith(
			expect.objectContaining({ name: 'New one', media_type: 'movie', handbrake_settings: expect.anything() })
		);
		expect(vi.mocked(createTranscodePreset).mock.calls[0][0].handbrake_settings?.common).toHaveProperty(
			'ChapterMarkers'
		);
	});

	it('disables Save without a name', async () => {
		mount({});
		expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
	});

	it('offers Clone on a read-only preset only when a clone handler is given', async () => {
		const builtin = preset({ is_builtin: true });
		const onclone = vi.fn();
		mount({ mode: 'view', preset: builtin, onclone });
		await fireEvent.click(screen.getByRole('button', { name: 'Clone' }));
		expect(onclone).toHaveBeenCalledWith(builtin);
		cleanup();
		mount({ mode: 'view', preset: builtin });
		expect(screen.queryByRole('button', { name: 'Clone' })).not.toBeInTheDocument();
	});

	it('does not save when the form is submitted on a read-only preset', async () => {
		mount({ mode: 'view', preset: preset({ is_builtin: true }) });
		await ready();
		await fireEvent.submit(document.querySelector('form') as HTMLFormElement);
		expect(createTranscodePreset).not.toHaveBeenCalled();
		expect(updateTranscodePreset).not.toHaveBeenCalled();
	});

	it('does not save when the form is submitted without a name', async () => {
		mount({});
		await ready();
		await fireEvent.submit(document.querySelector('form') as HTMLFormElement);
		expect(createTranscodePreset).not.toHaveBeenCalled();
	});

	it('sends handbrake_settings null once every value is reset (Review Focus 2)', async () => {
		vi.mocked(updateTranscodePreset).mockResolvedValue(preset());
		mount({
			mode: 'edit',
			preset: preset({ handbrake_settings: { common: { ChapterMarkers: false }, encoders: {} } })
		});
		await ready();
		await openTab('Chapters');
		await fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
		await save();
		await waitFor(() => expect(updateTranscodePreset).toHaveBeenCalled());
		expect(vi.mocked(updateTranscodePreset).mock.calls[0]).toEqual([
			't1',
			expect.objectContaining({ handbrake_settings: null })
		]);
	});

	it('an encoder change drops blocks the new encoder cannot reach (Review Focus 4)', async () => {
		vi.mocked(updateTranscodePreset).mockResolvedValue(preset());
		const settings = { common: {}, encoders: { x264: { VideoTune: 'film' }, x265: { VideoTune: 'grain' } } };
		mount({ mode: 'edit', preset: preset({ handbrake_settings: settings }) });
		await ready();
		const encoder = screen.getByTestId('tp-encoder');
		await waitFor(() => expect(encoder.querySelector('option[value="any_h265"]')).not.toBeNull());
		await fireEvent.change(encoder, { target: { value: 'any_h265' } });
		await save();
		await waitFor(() => expect(updateTranscodePreset).toHaveBeenCalled());
		expect(vi.mocked(updateTranscodePreset).mock.calls[0][1].handbrake_settings).toEqual({
			common: {},
			encoders: { x265: { VideoTune: 'grain' } }
		});
	});

	it('a new base drops the blocks the preset encoder no longer reaches', async () => {
		vi.mocked(updateTranscodePreset).mockResolvedValue(preset());
		vi.mocked(fetchBuiltinPreset).mockResolvedValue({ VideoEncoder: 'x265_10bit' });
		const settings = { common: {}, encoders: { x264: { VideoTune: 'film' }, x265: { VideoTune: 'grain' } } };
		mount({ mode: 'edit', preset: preset({ encoder: 'preset', handbrake_settings: settings }) });
		await ready();
		await fireEvent.change(screen.getByTestId('tp-preset-ref'), { target: { value: 'H.265 MKV 1080p30' } });
		await waitFor(() => expect(fetchBuiltinPreset).toHaveBeenCalledWith('H.265 MKV 1080p30'));
		await save();
		await waitFor(() => expect(updateTranscodePreset).toHaveBeenCalled());
		expect(vi.mocked(updateTranscodePreset).mock.calls[0][1].handbrake_settings).toEqual({
			common: {},
			encoders: { x265: { VideoTune: 'grain' } }
		});
	});

	it('edits and resets a per-encoder value', async () => {
		vi.mocked(updateTranscodePreset).mockResolvedValue(preset());
		mount({
			mode: 'edit',
			preset: preset({ handbrake_settings: { common: {}, encoders: { x264: { VideoOptionExtra: 'a' } } } })
		});
		await ready();
		await openTab('Video');
		const card = screen.getByRole('region', { name: 'x264' });
		await fireEvent.click(within(card).getByRole('button', { name: 'Reset' }));
		await fireEvent.change(within(card).getByLabelText('Extra encoder options'), { target: { value: 'b' } });
		await save();
		await waitFor(() => expect(updateTranscodePreset).toHaveBeenCalled());
		expect(vi.mocked(updateTranscodePreset).mock.calls[0][1].handbrake_settings?.encoders).toEqual({
			x264: { VideoOptionExtra: 'b' }
		});
	});

	it('a 422 with issues marks the fields and keeps the sidebar open', async () => {
		const issues = [
			{ key: 'ChapterMarkers', encoder: null, code: 'wrong_type' as const, message: 'Must be a boolean' },
			{ key: 'handbrake_settings', encoder: null, code: 'engine_ignores_settings' as const, message: 'Ignored' }
		];
		vi.mocked(updateTranscodePreset).mockRejectedValue(new ApiError(422, 'API 422', { detail: { issues } }));
		const { onsaved } = mount({ mode: 'edit', preset: preset() });
		await ready();
		await save();
		expect(await screen.findByText('Fix the marked settings and save again.')).toBeInTheDocument();
		expect(screen.getByText('Ignored')).toBeInTheDocument();
		await openTab('Chapters');
		expect(screen.getByText('Must be a boolean')).toBeInTheDocument();
		expect(onsaved).not.toHaveBeenCalled();
		expect(screen.getByRole('dialog', { name: 'Edit transcode preset' })).toBeInTheDocument();
	});

	it('lists an issue on a field another setting hides in the banner, named by its label', async () => {
		const issues = [{ key: 'PictureTopCrop', encoder: null, code: 'out_of_range' as const, message: 'Too large' }];
		const handbrake_settings = { common: { PictureCropMode: 0, PictureTopCrop: 9999 }, encoders: {} };
		mount({ mode: 'edit', preset: preset({ handbrake_settings, issues }) });
		await ready();
		const banner = document.querySelector('.preset-sidebar-issues') as HTMLElement;
		expect(banner).toHaveTextContent('Top crop: Too large');
		await openTab('Dimensions');
		expect(screen.queryByLabelText('Top crop')).not.toBeInTheDocument();
	});

	it('keeps an issue on a rendered field out of the banner', async () => {
		const issues = [{ key: 'PictureTopCrop', encoder: null, code: 'out_of_range' as const, message: 'Too large' }];
		const handbrake_settings = { common: { PictureCropMode: 3, PictureTopCrop: 9999 }, encoders: {} };
		mount({ mode: 'edit', preset: preset({ handbrake_settings, issues }) });
		await ready();
		expect(document.querySelector('.preset-sidebar-issues')).toBeNull();
	});

	it('shows the read-time issues of the preset', async () => {
		const issues = [{ key: 'preset_ref', encoder: null, code: 'not_in_list' as const, message: 'No such preset' }];
		mount({ mode: 'edit', preset: preset({ preset_ref: 'Gone 1080p', issues }) });
		expect(await screen.findByText('No such preset')).toBeInTheDocument();
	});

	it('another failure shows a banner and keeps the earlier issues', async () => {
		vi.mocked(updateTranscodePreset).mockRejectedValue(new ApiError(409, 'Name taken', null));
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await save();
		expect(await screen.findByText('Name taken')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
	});

	it('a 503 on save offers Retry, which refreshes the schema', async () => {
		vi.mocked(refreshHandbrakeSchema).mockResolvedValue({ ok: true, error: null });
		vi.mocked(updateTranscodePreset).mockRejectedValue(new ApiError(503, 'No HandBrake schema loaded yet', null));
		mount({ mode: 'edit', preset: preset() });
		await ready();
		await save();
		expect(await screen.findByText('No HandBrake schema loaded yet')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
		await waitFor(() => expect(refreshHandbrakeSchema).toHaveBeenCalled());
	});

	it('shows Saving... while the save runs', async () => {
		vi.mocked(updateTranscodePreset).mockReturnValue(new Promise(() => {}));
		mount({ mode: 'edit', preset: preset() });
		await save();
		expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled();
	});
});

describe('no schema loaded', () => {
	it('shows the message and a Retry that refreshes, while the preset block still works', async () => {
		vi.mocked(fetchHandbrakeSchema).mockRejectedValue(new ApiError(503, 'No HandBrake schema loaded yet', null));
		vi.mocked(refreshHandbrakeSchema).mockResolvedValue({ ok: true, error: null });
		mount({ mode: 'edit', preset: preset() });
		expect(await screen.findByText('No HandBrake schema loaded yet')).toBeInTheDocument();
		expect(screen.getByTestId('tp-preset-ref').tagName).toBe('INPUT');
		vi.mocked(fetchHandbrakeSchema).mockResolvedValue(schema);
		await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
		await waitFor(() => expect(refreshHandbrakeSchema).toHaveBeenCalled());
		await ready();
	});

	it('does not reload a schema the store already has', async () => {
		await handbrakeSchema.load();
		mount({ mode: 'edit', preset: preset() });
		await ready();
		expect(fetchHandbrakeSchema).toHaveBeenCalledTimes(1);
	});
});

describe('footer', () => {
	it('shows usage and the CPU note only with the host note', async () => {
		mount({ mode: 'edit', usage: 2, preset: preset({ host_notes: ['encodes_on_cpu_here'] }) });
		expect(screen.getByText('Used by 2 sessions')).toBeInTheDocument();
		expect(screen.getByText('Encodes on CPU on this host: no verified non-AMD GPU for this codec')).toBeInTheDocument();
	});

	it('has no note without it', () => {
		mount({ mode: 'edit', usage: 1, preset: preset() });
		expect(screen.getByText('Used by 1 session')).toBeInTheDocument();
		expect(screen.queryByText(/Encodes on CPU on this host/)).not.toBeInTheDocument();
	});
});

describe('import', () => {
	async function openImport() {
		await ready();
		await fireEvent.click(screen.getByRole('button', { name: 'Import HandBrake preset' }));
		await fireEvent.input(screen.getByLabelText('HandBrake preset JSON'), { target: { value: '{}' } });
	}

	it('draws no footer strip while importing, and brings it back after Cancel', async () => {
		mount({});
		await openImport();
		expect(screen.queryByTestId('editor-sidebar-footer')).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(await screen.findByTestId('editor-sidebar-footer')).toBeInTheDocument();
	});

	it('Cancel on step 1 returns to the tabs unchanged', async () => {
		mount({});
		await openImport();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(await screen.findByRole('tablist')).toBeInTheDocument();
		expect(screen.getByLabelText('Name')).toHaveValue('');
	});

	it('Use these settings fills the draft without saving, and Save then creates it', async () => {
		vi.mocked(parseHandbrakeImport).mockResolvedValue(plexImport as never);
		vi.mocked(createTranscodePreset).mockResolvedValue(preset());
		const { onsaved } = mount({});
		await openImport();
		await fireEvent.click(screen.getByRole('button', { name: 'Read file' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Use these settings' }));
		expect(await screen.findByRole('tablist')).toBeInTheDocument();
		expect(screen.getByLabelText('Name')).toHaveValue('Custom_Plex_720p');
		expect(createTranscodePreset).not.toHaveBeenCalled();
		await save();
		await waitFor(() => expect(onsaved).toHaveBeenCalled());
		const body = vi.mocked(createTranscodePreset).mock.calls[0][0];
		expect(body).toMatchObject({ name: 'Custom_Plex_720p', container: 'mkv', encoder: 'any_h264' });
		expect(body.handbrake_settings?.encoders?.nvenc_h264).toMatchObject({ VideoPreset: 'slower' });
	});
});
