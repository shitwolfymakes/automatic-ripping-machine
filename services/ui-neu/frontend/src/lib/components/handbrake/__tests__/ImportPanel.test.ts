import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import type {
	EncoderAvailabilityView,
	HandbrakeSchemaSlimView,
	ImportParseResponse,
	ImportedPresetView
} from '$lib/types/api.gen';
import slim from '$lib/handbrake/__tests__/fixtures/slim-schema.json';
import tenBit from '$lib/handbrake/__tests__/fixtures/x265-10bit-import-response.json';
import plex from '$lib/handbrake/__tests__/fixtures/plex-import-response.json';
import { ApiError } from '$lib/api/client';
import { parseHandbrakeImport } from '$lib/api/transcode-presets';
import ImportPanel from '../ImportPanel.svelte';

vi.mock('$lib/api/transcode-presets', () => ({ parseHandbrakeImport: vi.fn() }));

const schema = slim as unknown as HandbrakeSchemaSlimView;
const PLEX = plex as unknown as ImportParseResponse;

function enc(id: string, label: string): EncoderAvailabilityView {
	return {
		id,
		label,
		group: 'any',
		engine: 'handbrake',
		kind: 'any',
		vendor: null,
		codec: null,
		available: true,
		reason: null
	};
}
const AVAILABILITY = [
	enc('any_h264', 'Any H.264'),
	enc('x264', 'CPU x264'),
	enc('qsv_h264', 'Intel QSV H.264'),
	enc('nvenc_h264', 'NVIDIA H.264'),
	enc('x265', 'CPU x265'),
	enc('nvenc_h265', 'NVIDIA H.265'),
	enc('qsv_h265', 'Intel QSV H.265')
];

function mount(loaded: HandbrakeSchemaSlimView | null = schema) {
	const oncancel = vi.fn();
	const onuse = vi.fn();
	renderComponent(ImportPanel, { props: { schema: loaded, availability: AVAILABILITY, oncancel, onuse } });
	return { oncancel, onuse };
}

async function paste(text: string) {
	await fireEvent.input(screen.getByLabelText('HandBrake preset JSON'), { target: { value: text } });
}

async function readFile() {
	await fireEvent.click(screen.getByRole('button', { name: 'Import' }));
}

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('step 1', () => {
	it('shows the steps, the checked version, the instruction and the review promise', () => {
		mount();
		expect(screen.getByText('1. Import > 2. Review')).toBeInTheDocument();
		expect(
			screen.getByText(`The file is checked against HandBrake ${schema.handbrake_tag}, then discarded.`)
		).toBeInTheDocument();
		expect(
			screen.getByText('Choose a preset file exported from the HandBrake app (Presets, Export), or paste its JSON.')
		).toBeInTheDocument();
		expect(screen.getByText('Choose file').tagName).toBe('LABEL');
		expect(screen.getByText('Nothing changes in the preset until you finish the review.')).toBeInTheDocument();
	});

	it('leaves out the version line while the schema is not loaded', () => {
		mount(null);
		expect(screen.queryByText(/is checked against HandBrake/)).toBeNull();
	});

	it('disables Import while the text is empty', async () => {
		mount();
		const button = screen.getByRole('button', { name: 'Import' });
		expect(button).toBeDisabled();
		await paste('{}');
		expect(button).toBeEnabled();
	});

	it('shows a parse error inline and stays on step 1', async () => {
		vi.mocked(parseHandbrakeImport).mockRejectedValue(new ApiError(422, 'This is not a HandBrake export', null));
		mount();
		await paste('nope');
		await readFile();
		expect(await screen.findByRole('alert')).toHaveTextContent('This is not a HandBrake export');
		expect(screen.getByLabelText('HandBrake preset JSON')).toHaveValue('nope');
		expect(screen.queryByText('Review the import')).not.toBeInTheDocument();
	});

	it('shows a generic message for an error that is not an Error', async () => {
		vi.mocked(parseHandbrakeImport).mockRejectedValue('boom');
		mount();
		await paste('x');
		await readFile();
		expect(await screen.findByRole('alert')).toHaveTextContent('Could not read the file');
	});

	it('disables Import while the request is in flight', async () => {
		vi.mocked(parseHandbrakeImport).mockReturnValue(new Promise(() => {}));
		mount();
		await paste('x');
		await readFile();
		expect(await screen.findByRole('button', { name: 'Importing...' })).toBeDisabled();
	});

	it('loads a chosen file into the text box', async () => {
		mount();
		const file = new File(['{"a":1}'], 'export.json', { type: 'application/json' });
		await fireEvent.change(screen.getByLabelText('Choose file'), { target: { files: [file] } });
		await waitFor(() => expect(screen.getByLabelText('HandBrake preset JSON')).toHaveValue('{"a":1}'));
	});

	it('ignores a file dialog that chose nothing', async () => {
		mount();
		await fireEvent.change(screen.getByLabelText('Choose file'), { target: { files: [] } });
		expect(screen.getByLabelText('HandBrake preset JSON')).toHaveValue('');
	});

	it('Cancel calls oncancel', async () => {
		const { oncancel } = mount();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(oncancel).toHaveBeenCalledTimes(1);
	});
});

describe('step 2 with the Plex export', () => {
	async function review() {
		vi.mocked(parseHandbrakeImport).mockResolvedValue(PLEX);
		const handles = mount();
		await paste('{"PresetList":[]}');
		await readFile();
		await screen.findByText('Review the import');
		return handles;
	}

	it('sends the pasted text as the body', async () => {
		await review();
		expect(parseHandbrakeImport).toHaveBeenCalledWith('{"PresetList":[]}');
	});

	it('shows the labelled values, counts and notes', async () => {
		await review();
		expect(screen.getByText('Encoder in the file').nextElementSibling).toHaveTextContent('NVIDIA H.264');
		expect(screen.getByText('Codec and bit depth').nextElementSibling).toHaveTextContent('H.264, 8-bit');
		expect(screen.getByText('Encoder in ARM').nextElementSibling).toHaveTextContent('Any H.264');
		expect(screen.getByText('Container').nextElementSibling).toHaveTextContent('mkv');
		expect(screen.getByText('Stored for NVIDIA H.264')).toBeInTheDocument();
		expect(screen.getByText('Bit depth 8 also set for Intel QSV H.264, CPU x264')).toBeInTheDocument();
		expect(screen.getByText('Video').nextElementSibling).not.toHaveTextContent('0');
		expect(screen.getByText('Total')).toBeInTheDocument();
		expect(screen.getByText('Only bit depth is copied. Other encoders keep their defaults.')).toBeInTheDocument();
		expect(screen.getByText(/^Not used by NVIDIA H\.264, not imported: VideoMultiPass/)).toBeInTheDocument();
		expect(screen.getByText('1 key dropped (not in HandBrake 1.11.1): VideoColorMatrixCode')).toBeInTheDocument();
	});

	it('shows no pick list for one preset, and eight-bit-only families when present', async () => {
		const withEight = { ...PLEX, presets: [{ ...PLEX.presets[0], eight_bit_only: ['x264'], copied_depth_to: [] }] };
		vi.mocked(parseHandbrakeImport).mockResolvedValue(withEight);
		mount();
		await paste('x');
		await readFile();
		expect(await screen.findByText('CPU x264: 8-bit on this encoder')).toBeInTheDocument();
		expect(screen.queryByRole('radio')).not.toBeInTheDocument();
	});

	it('Back returns to step 1 with the text kept', async () => {
		await review();
		await fireEvent.click(screen.getByRole('button', { name: 'Back' }));
		expect(screen.getByLabelText('HandBrake preset JSON')).toHaveValue('{"PresetList":[]}');
	});

	it('Use these settings hands the preset over', async () => {
		const { onuse } = await review();
		await fireEvent.click(screen.getByRole('button', { name: 'Use these settings' }));
		expect(onuse).toHaveBeenCalledWith(PLEX.presets[0]);
	});
});

describe('step 2 with several presets', () => {
	const base = PLEX.presets[0];
	const response: ImportParseResponse = {
		...PLEX,
		presets: [
			{ ...base, path: ['Plex'], name: 'Broken', proposal: null, importable: false, reason: 'No video encoder' },
			{ ...base, path: ['Plex', 'Movies'], name: 'Good' } as ImportedPresetView,
			{ ...base, path: [], name: 'Other', source_encoder: 'x264' } as ImportedPresetView
		]
	};

	async function review() {
		vi.mocked(parseHandbrakeImport).mockResolvedValue(response);
		const handles = mount();
		await paste('x');
		await readFile();
		return handles;
	}

	it('lists them with their path, disables the unimportable one with its reason, and preselects the first importable', async () => {
		await review();
		const radios = await screen.findAllByRole('radio');
		expect(radios).toHaveLength(3);
		expect(radios[0]).toBeDisabled();
		expect(screen.getByText('No video encoder')).toBeInTheDocument();
		expect(screen.getByText('Plex / Movies / Good')).toBeInTheDocument();
		expect(radios[1]).toBeChecked();
	});

	it('reviews the preset picked', async () => {
		const { onuse } = await review();
		await fireEvent.click((await screen.findAllByRole('radio'))[2]);
		expect(screen.getByText('Encoder in the file').nextElementSibling).toHaveTextContent('CPU x264');
		await fireEvent.click(screen.getByRole('button', { name: 'Use these settings' }));
		expect(onuse).toHaveBeenCalledWith(response.presets[2]);
	});
});

describe('a single unimportable preset', () => {
	it('shows its reason and disables Use these settings', async () => {
		const only = { ...PLEX.presets[0], proposal: null, importable: false, reason: 'No video encoder' };
		vi.mocked(parseHandbrakeImport).mockResolvedValue({ ...PLEX, presets: [only] });
		mount();
		await paste('x');
		await readFile();
		expect(await screen.findByText('No video encoder')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Use these settings' })).toBeDisabled();
	});

	it('copes with an empty list', async () => {
		vi.mocked(parseHandbrakeImport).mockResolvedValue({ ...PLEX, presets: [] });
		mount();
		await paste('x');
		await readFile();
		expect(await screen.findByRole('button', { name: 'Use these settings' })).toBeDisabled();
	});
});

describe('when its props change', () => {
	it('shows the version line once the schema arrives', async () => {
		const oncancel = vi.fn();
		const onuse = vi.fn();
		const { rerender } = renderComponent(ImportPanel, {
			props: { schema: null, availability: AVAILABILITY, oncancel, onuse }
		});
		expect(screen.queryByText(/is checked against HandBrake/)).toBeNull();
		await rerender({ schema });
		expect(
			screen.getByText(`The file is checked against HandBrake ${schema.handbrake_tag}, then discarded.`)
		).toBeInTheDocument();
	});
});

describe('before the schema has loaded', () => {
	it('still offers the picked preset without a review', async () => {
		vi.mocked(parseHandbrakeImport).mockResolvedValue(PLEX);
		mount(null);
		await paste('x');
		await readFile();
		expect(await screen.findByText('Review the import')).toBeInTheDocument();
		expect(screen.queryByText('Encoder in the file')).not.toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Use these settings' })).toBeEnabled();
	});
});

describe('step 2 with a 10-bit export', () => {
	it('shows the family, its stored values and the real depth', async () => {
		vi.mocked(parseHandbrakeImport).mockResolvedValue(tenBit as unknown as ImportParseResponse);
		mount();
		await paste('x');
		await readFile();
		expect(await screen.findByText('Stored for CPU x265')).toBeInTheDocument();
		expect(screen.getByText('Codec and bit depth').nextElementSibling).toHaveTextContent('H.265, 10-bit');
		expect(screen.getByText('Bit depth 10 also set for NVIDIA H.265, Intel QSV H.265')).toBeInTheDocument();
	});
});

describe('version mismatch', () => {
	it('shows every warning from the response as a note', async () => {
		const warning = 'Exported from HandBrake 72.0.1, this ARM reads 72.0.0';
		const mismatch = {
			...PLEX,
			handbrake_version: { export: '72.0.1', schema: '72.0.0' },
			presets: [{ ...PLEX.presets[0], warnings: [warning] }]
		};
		vi.mocked(parseHandbrakeImport).mockResolvedValue(mismatch);
		mount();
		await paste('x');
		await readFile();
		expect(await screen.findByText(warning)).toBeInTheDocument();
	});
});
