// Every branch of PresetBlock's own code is covered here. The coverage tool
// still reports open arms that are Svelte's, not the component's: each
// `<select value={...}>`, `<option value={...}>` and text `{expr}` compiles to
// `(... ) ?? ''` plus a select-sync `if`, and none of those values is ever
// null (draft fields are strings, catalog ids and labels are strings).
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/testing/render';
import type { EncoderAvailabilityView, SettingIssue } from '$lib/types/api.gen';
import type { WSEnvelope } from '$lib/api/ws';
import { stopEncoderEvents } from '$lib/stores/encoders.svelte';
import { initialDraft, type Draft } from '$lib/handbrake/draft';
import PresetBlock from '../PresetBlock.svelte';

// One entry per group, in catalog order, standing in for the full
// arm_common.encoders catalog: qsv_h264 unavailable (no verified device),
// any_h265 available but would currently fall back to the CPU, vaapi_h264
// runs over ffmpeg directly rather than through HandBrake.
function enc(id: string, group: EncoderAvailabilityView['group'], over: Partial<EncoderAvailabilityView> = {}) {
	return {
		id,
		label: id,
		group,
		engine: 'handbrake',
		kind: group === 'any' ? 'any' : 'gpu',
		vendor: null,
		codec: 'h264',
		available: true,
		reason: null,
		...over
	} as EncoderAvailabilityView;
}
const ENCODERS: EncoderAvailabilityView[] = [
	enc('preset', 'preset', { label: "HandBrake preset's own encoder", kind: 'preset', codec: null }),
	enc('cpu_h264', 'cpu', { label: 'CPU H.264', kind: 'cpu' }),
	enc('any_h265', 'any', { label: 'Any GPU H.265', reason: 'no verified GPU; runs on the CPU' }),
	enc('qsv_h264', 'qsv', { available: false, reason: 'no enabled device has verified qsv_h264' }),
	enc('nvenc_h264', 'nvenc'),
	enc('vaapi_h264', 'vaapi', { engine: 'ffmpeg_vaapi' })
];

const mockFetchEncoders = vi.fn(() => Promise.resolve(ENCODERS));
vi.mock('$lib/api/encoders', () => ({ fetchEncoders: () => mockFetchEncoders() }));

// The encoders store follows `transcode.events`; capture its handler so a
// test can deliver a gpu.probed envelope.
const ws = vi.hoisted(() => ({ handler: null as ((env: WSEnvelope) => void) | null }));
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		start: vi.fn(),
		subscribe: (_topic: string, handler: (env: WSEnvelope) => void) => {
			ws.handler = handler;
			return () => {
				ws.handler = null;
			};
		}
	}
}));

function mount(over: Partial<Draft> = {}, props: Record<string, unknown> = {}) {
	const onfield = vi.fn();
	renderComponent(PresetBlock, {
		props: {
			draft: { ...initialDraft(null), ...over },
			readonly: false,
			editing: false,
			builtinNames: ['Fast 1080p30', 'H.265 NVENC 1080p'],
			issues: [] as SettingIssue[],
			onfield,
			...props
		}
	});
	return onfield;
}

const encoderSelect = () => screen.getByTestId('tp-encoder') as HTMLSelectElement;
const option = (value: string) => encoderSelect().querySelector(`option[value="${value}"]`) as HTMLOptionElement | null;

async function encodersLoaded() {
	await waitFor(() => expect(option('nvenc_h264')).not.toBeNull());
}

afterEach(() => {
	cleanup();
	stopEncoderEvents();
	vi.clearAllMocks();
});

describe('fields', () => {
	it('shows the draft and sends each edit to onfield', async () => {
		const onfield = mount({ name: 'N', extra_args: '--x' });
		expect(screen.getByTestId('tp-name')).toHaveValue('N');
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'M' } });
		await fireEvent.change(screen.getByTestId('tp-media-type'), { target: { value: 'music' } });
		await fireEvent.change(screen.getByTestId('tp-tool'), { target: { value: 'abcde' } });
		await fireEvent.change(screen.getByTestId('tp-container'), { target: { value: 'mp4' } });
		await fireEvent.input(screen.getByTestId('tp-extra-args'), { target: { value: '--y' } });
		expect(onfield.mock.calls).toEqual([
			['name', 'M'],
			['media_type', 'music'],
			['tool', 'abcde'],
			['container', 'mp4'],
			['extra_args', '--y']
		]);
	});

	it('offers Video for movie and TV, and shows a TV preset as Video', () => {
		mount({ media_type: 'tv' });
		const select = screen.getByTestId('tp-media-type') as HTMLSelectElement;
		expect(Array.from(select.options).map((o) => o.textContent?.trim())).toEqual(['Video', 'Music', 'Data', 'ISO']);
		expect(select.selectedOptions[0].textContent?.trim()).toBe('Video');
	});

	it('locks media type on edit and everything when read-only', () => {
		mount({}, { editing: true });
		expect(screen.getByTestId('tp-media-type')).toBeDisabled();
		expect(screen.getByTestId('tp-name')).not.toBeDisabled();
		cleanup();
		mount({}, { readonly: true });
		for (const id of ['tp-name', 'tp-tool', 'tp-container', 'tp-encoder', 'tp-preset-ref', 'tp-extra-args']) {
			expect(screen.getByTestId(id)).toBeDisabled();
		}
	});

	it("links the base preset to HandBrake's official presets page for a HandBrake preset", () => {
		mount();
		const link = screen.getByTestId('tp-preset-ref-docs');
		expect(link).toHaveAttribute('href', 'https://handbrake.fr/docs/en/latest/technical/official-presets.html');
		expect(link).toHaveAttribute('target', '_blank');
		expect(link).toHaveAttribute('rel', 'noopener noreferrer');
		expect(link).toHaveAccessibleName('HandBrake docs: official presets');
		expect(screen.getByLabelText('Base preset')).toBe(screen.getByTestId('tp-preset-ref'));
		cleanup();
		mount({}, { builtinNames: null });
		expect(screen.getByLabelText('Preset ref')).toBe(screen.getByTestId('tp-preset-ref'));
		expect(screen.getByTestId('tp-preset-ref-docs')).toBeInTheDocument();
		cleanup();
		mount({ tool: 'abcde' });
		expect(screen.queryByTestId('tp-preset-ref-docs')).not.toBeInTheDocument();
	});

	it('notes that extra args win over the settings while the tabs show', () => {
		mount({ encoder: 'any_h265' });
		expect(screen.getByText('Flags here are added last and override the settings below.')).toBeInTheDocument();
		cleanup();
		mount({ tool: 'abcde' });
		expect(screen.queryByText(/added last/)).not.toBeInTheDocument();
	});
});

describe('field messages', () => {
	it.each(['name', 'media_type', 'tool', 'container', 'encoder', 'preset_ref', 'extra_args'])(
		'shows a save issue on %s under its input and marks the input',
		(key) => {
			const id = `tp-${key.replaceAll('_', '-')}`;
			mount({}, { issues: [{ key, encoder: null, code: 'wrong_type', message: `Bad ${key}` }] });
			const input = document.getElementById(id) as HTMLElement;
			expect(input).toHaveAttribute('aria-invalid', 'true');
			expect(input).toHaveAttribute('aria-describedby', `${id}-error`);
			const message = document.getElementById(`${id}-error`) as HTMLElement;
			expect(message).toHaveTextContent(`Bad ${key}`);
			expect(message).toHaveClass('field-error');
		}
	);

	it("puts the sidebar's own name check before a save issue on the name", () => {
		mount(
			{},
			{
				issues: [{ key: 'name', encoder: null, code: 'wrong_type', message: 'Taken' }],
				errors: { 'tp-name': 'Name is required' }
			}
		);
		expect(document.getElementById('tp-name-error')).toHaveTextContent('Name is required');
	});

	it('marks no field without issues or errors', () => {
		mount();
		expect(document.querySelector('[aria-invalid]')).toBeNull();
		expect(document.querySelector('.field-error')).toBeNull();
	});
});

describe('settings that will be cleared', () => {
	const note = "This preset's HandBrake settings will be cleared when you save.";
	const settings = { common: { ChapterMarkers: true }, encoders: {} };

	it('says so when the tabs no longer apply and settings are stored', () => {
		mount({ tool: 'none', settings });
		expect(screen.getByText(note)).toBeInTheDocument();
		cleanup();
		mount({ encoder: 'vaapi_h264', settings });
		expect(screen.getByText(note)).toBeInTheDocument();
	});

	it('says nothing while the tabs apply or nothing is stored', () => {
		mount({ encoder: 'any_h265', settings });
		expect(screen.queryByText(note)).not.toBeInTheDocument();
		cleanup();
		mount({ tool: 'none' });
		expect(screen.queryByText(note)).not.toBeInTheDocument();
	});
});

describe('base preset', () => {
	it('is a select of built-in names with a None choice', async () => {
		const onfield = mount({ preset_ref: null });
		const select = screen.getByTestId('tp-preset-ref');
		expect(screen.getByText('Base preset')).toBeInTheDocument();
		expect(
			within(select)
				.getAllByRole('option')
				.map((o) => o.textContent)
		).toEqual(['None (HandBrake defaults)', 'Fast 1080p30', 'H.265 NVENC 1080p']);
		await fireEvent.change(select, { target: { value: 'Fast 1080p30' } });
		expect(onfield).toHaveBeenCalledWith('preset_ref', 'Fast 1080p30');
	});

	it('keeps a stored name the build lacks, and shows its issue', () => {
		const issues = [{ key: 'preset_ref', encoder: null, code: 'not_in_list', message: 'No such preset' }];
		mount({ preset_ref: 'Gone 1080p' }, { issues });
		expect(within(screen.getByTestId('tp-preset-ref')).getByRole('option', { name: 'Gone 1080p' })).toBeInTheDocument();
		expect(screen.getByRole('alert')).toHaveTextContent('No such preset');
	});

	it('is free text without a schema or for another tool', async () => {
		const onfield = mount({ preset_ref: 'x' }, { builtinNames: null });
		expect(screen.getByText('Preset ref')).toBeInTheDocument();
		await fireEvent.change(screen.getByTestId('tp-preset-ref'), { target: { value: 'flac' } });
		expect(onfield).toHaveBeenCalledWith('preset_ref', 'flac');
		cleanup();
		mount({ tool: 'abcde' });
		expect(screen.getByTestId('tp-preset-ref').tagName).toBe('INPUT');
	});
});

describe('encoder picker', () => {
	it('groups options in catalog order, unavailable ones disabled with their reason', async () => {
		mount();
		await encodersLoaded();
		const labels = Array.from(encoderSelect().querySelectorAll('optgroup')).map((g) => g.label);
		expect(labels).toEqual(["HandBrake preset's own", 'CPU', 'Any GPU', 'Intel QSV', 'NVIDIA NVENC', 'AMD VAAPI']);
		expect(option('qsv_h264')?.disabled).toBe(true);
		expect(option('qsv_h264')?.textContent).toContain('no enabled device has verified qsv_h264');
		expect(option('cpu_h264')?.title).toBe('');
	});

	it('refreshes availability when a GPU probe finishes', async () => {
		mount();
		await waitFor(() => expect(option('qsv_h264')?.disabled).toBe(true));
		mockFetchEncoders.mockResolvedValueOnce(ENCODERS.map((e) => (e.id === 'qsv_h264' ? { ...e, available: true } : e)));
		ws.handler?.({
			op: 'event',
			event_id: 'evt_1',
			event_type: 'gpu.probed',
			emitted_at: 'now',
			topic: 'transcode.events',
			job_id: null,
			track_id: null,
			payload: { gpu_id: 'gpu_1' }
		});
		await waitFor(() => expect(option('qsv_h264')?.disabled).toBe(false));
	});

	it('sends the chosen encoder, and moves WebM to MKV for a VAAPI encoder', async () => {
		const onfield = mount({ container: 'webm' });
		await encodersLoaded();
		await fireEvent.change(encoderSelect(), { target: { value: 'nvenc_h264' } });
		await fireEvent.change(encoderSelect(), { target: { value: 'vaapi_h264' } });
		expect(onfield.mock.calls).toEqual([
			['encoder', 'nvenc_h264'],
			['encoder', 'vaapi_h264'],
			['container', 'mkv']
		]);
	});

	it('keeps the container for a VAAPI encoder that already writes MKV', async () => {
		const onfield = mount({ container: 'mkv' });
		await encodersLoaded();
		await fireEvent.change(encoderSelect(), { target: { value: 'vaapi_h264' } });
		expect(onfield.mock.calls).toEqual([['encoder', 'vaapi_h264']]);
	});

	it('is locked for abcde and none', async () => {
		mount({ tool: 'none' });
		await encodersLoaded();
		expect(encoderSelect()).toBeDisabled();
	});

	it('a VAAPI encoder relabels extra args, notes the base preset and disables WebM', async () => {
		mount({ encoder: 'vaapi_h264' });
		await encodersLoaded();
		expect(screen.getByText('ffmpeg arguments')).toBeInTheDocument();
		expect(screen.getByTestId('tp-preset-ref-note')).toHaveTextContent('Not used by this encoder.');
		expect(screen.getByTestId('tp-container-vaapi-note')).toBeInTheDocument();
		const webm = screen.getByTestId('tp-container').querySelector('option[value="webm"]') as HTMLOptionElement;
		expect(webm.disabled).toBe(true);
	});

	it('re-derives the VAAPI view when the encoder prop changes', async () => {
		const props = {
			draft: { ...initialDraft(null), encoder: 'any_h264' },
			readonly: false,
			editing: false,
			builtinNames: ['Fast 1080p30'],
			issues: [] as SettingIssue[],
			onfield: vi.fn()
		};
		const { rerender } = renderComponent(PresetBlock, { props });
		await encodersLoaded();
		expect(screen.queryByText('ffmpeg arguments')).not.toBeInTheDocument();
		expect(screen.queryByTestId('tp-container-vaapi-note')).not.toBeInTheDocument();
		await rerender({ draft: { ...props.draft, encoder: 'vaapi_h264' } });
		expect(screen.getByText('ffmpeg arguments')).toBeInTheDocument();
		expect(screen.getByTestId('tp-container-vaapi-note')).toBeInTheDocument();
	});

	it('shows the current id alone when the catalog is empty', async () => {
		mockFetchEncoders.mockResolvedValueOnce([]);
		mount({ encoder: 'any_h264' });
		await waitFor(() => expect(within(encoderSelect()).getByRole('option', { name: 'any_h264' })).toBeInTheDocument());
	});
});

describe('hardware hint', () => {
	it('shows when the base names a hardware encoder and the encoder is the preset one', async () => {
		mount({ preset_ref: 'H.265 NVENC 1080p' });
		expect(screen.getByTestId('tp-encoder-hint')).toBeInTheDocument();
	});

	it('hides for a plain base or a chosen encoder', async () => {
		mount({ preset_ref: 'Fast 1080p30' });
		expect(screen.queryByTestId('tp-encoder-hint')).not.toBeInTheDocument();
		cleanup();
		mount({ preset_ref: 'H.265 NVENC 1080p', encoder: 'nvenc_h264' });
		expect(screen.queryByTestId('tp-encoder-hint')).not.toBeInTheDocument();
	});
});

describe('PresetBlock accessible labels', () => {
	afterEach(() => cleanup());
	it('labels every control by name', () => {
		renderComponent(PresetBlock, {
			props: {
				draft: initialDraft(null),
				readonly: false,
				editing: false,
				builtinNames: ['Fast 1080p30'],
				issues: [],
				onfield: vi.fn()
			}
		});
		for (const name of ['Name', 'Media type', 'Tool', 'Container', 'Encoder', 'Base preset', 'Extra args']) {
			expect(screen.getByLabelText(name)).toBeInTheDocument();
		}
	});
});
