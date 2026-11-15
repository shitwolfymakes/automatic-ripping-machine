import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/test-utils';
import { fireEvent } from '@testing-library/svelte';
import type { HandbrakeSchemaSlimView, SettingIssue } from '$lib/types/api.gen';
import fixture from '$lib/handbrake/__tests__/fixtures/slim-schema.json';
import { rowKeys } from '$lib/handbrake/audioTracks';
import AudioTrackList from '../AudioTrackList.svelte';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const tracks = [
	{ AudioEncoder: 'av_aac', AudioMixdown: 'stereo' },
	{ AudioEncoder: 'copy:ac3', AudioMixdown: 'none', AudioBitrate: 128 }
];

function mount(over: Record<string, unknown> = {}) {
	const onchange = vi.fn();
	const result = renderComponent(AudioTrackList, {
		props: {
			value: tracks,
			visibleKeys: tracks.map(() => rowKeys(schema)),
			schema,
			issues: [],
			readonly: false,
			onchange,
			...over
		}
	});
	return { onchange, ...result };
}

const row = (n: number) => screen.getByRole('region', { name: `Audio track ${n}` });
const optionsOf = (el: HTMLElement) => Array.from((el as HTMLSelectElement).options).map((o) => o.value);

describe('AudioTrackList', () => {
	afterEach(() => cleanup());

	it('renders one row per track with unique ids and the fields in order', () => {
		mount();
		const labels = Array.from(row(1).querySelectorAll('label.field-label')).map((l) => l.textContent);
		expect(labels.slice(0, 8)).toEqual([
			'Encoder',
			'Mixdown',
			'Sample rate',
			'Bitrate (kbit/s)',
			'Use quality instead of bitrate',
			'Quality',
			'Gain (dB)',
			'Dynamic range compression'
		]);
		expect(row(1).querySelector('#audio-0-tunable-AudioEncoder')).not.toBeNull();
		expect(row(2).querySelector('#audio-1-tunable-AudioEncoder')).not.toBeNull();
	});

	it('narrows the mixdown list to the row encoder', () => {
		mount();
		expect(optionsOf(within(row(1)).getByLabelText('Mixdown'))).toContain('5point1');
		expect(optionsOf(within(row(2)).getByLabelText('Mixdown'))).toEqual(['none']);
	});

	it('changing an encoder leaves a now-invalid mixdown untouched', async () => {
		const { onchange } = mount();
		await fireEvent.change(within(row(1)).getByLabelText('Encoder'), { target: { value: 'copy:ac3' } });
		const next = onchange.mock.calls[0][0];
		expect(next[0]).toEqual({ AudioEncoder: 'copy:ac3', AudioMixdown: 'stereo' });
	});

	it('edits a field, and Reset clears it', async () => {
		const { onchange } = mount();
		await fireEvent.change(within(row(1)).getByLabelText('Sample rate'), { target: { value: '48' } });
		expect(onchange.mock.calls[0][0][0]).toMatchObject({ AudioSamplerate: '48' });
		const bitrate = within(row(2)).getByLabelText('Bitrate (kbit/s)').closest('.tunable-field') as HTMLElement;
		await fireEvent.click(within(bitrate).getByRole('button', { name: 'Reset' }));
		expect(onchange.mock.calls[1][0][1]).toEqual({ AudioEncoder: 'copy:ac3', AudioMixdown: 'none' });
	});

	it('adds, removes and reorders tracks', async () => {
		const { onchange } = mount();
		await fireEvent.click(screen.getByRole('button', { name: 'Add track' }));
		expect(onchange.mock.calls[0][0]).toHaveLength(3);
		await fireEvent.click(screen.getByRole('button', { name: 'Remove track 1' }));
		expect(onchange.mock.calls[1][0]).toEqual([tracks[1]]);
		await fireEvent.click(screen.getByRole('button', { name: 'Move track 2 up' }));
		expect(onchange.mock.calls[2][0]).toEqual([tracks[1], tracks[0]]);
		await fireEvent.click(screen.getByRole('button', { name: 'Move track 1 down' }));
		expect(onchange.mock.calls[3][0]).toEqual([tracks[1], tracks[0]]);
	});

	it('disables the edge moves', () => {
		mount();
		expect((screen.getByRole('button', { name: 'Move track 1 up' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: 'Move track 2 down' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('shows a row issue under that row and a whole-list issue above the list', () => {
		const issues = [
			{ key: 'AudioList[1].AudioMixdown', message: 'Bad mixdown', code: 'not_in_list' },
			{ key: 'AudioList', message: 'List is wrong', code: 'wrong_type' }
		] as SettingIssue[];
		mount({ issues });
		expect(within(row(2)).getByText('Bad mixdown')).toBeTruthy();
		expect(within(row(1)).queryByText('Bad mixdown')).toBeNull();
		expect(screen.getByText('List is wrong')).toBeTruthy();
	});

	it('hides the row controls and disables fields when readonly', () => {
		mount({ readonly: true });
		expect(screen.queryByRole('button', { name: 'Add track' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Remove track 1' })).toBeNull();
		expect((within(row(1)).getByLabelText('Encoder') as HTMLSelectElement).disabled).toBe(true);
	});

	it('draws the row actions as small buttons with their short labels', () => {
		mount({ value: [{}, {}] });
		const up = screen.getByRole('button', { name: 'Move track 2 up' });
		expect(up).toHaveTextContent('Move up');
		expect(up).toHaveClass('btn', 'btn-sm');
		expect(screen.getByRole('button', { name: 'Remove track 1' })).toHaveClass('btn', 'btn-sm');
	});

	it('renders just the Add track button for an empty list', () => {
		mount({ value: [] });
		expect(screen.getByRole('button', { name: 'Add track' })).toBeTruthy();
		expect(screen.queryByRole('region')).toBeNull();
	});

	it('renders only the fields each track is given', () => {
		const gain = rowKeys(schema).filter((k) => k.name === 'AudioTrackGainSlider');
		mount({ visibleKeys: [gain, gain] });
		for (const n of [1, 2]) {
			const labels = Array.from(row(n).querySelectorAll('label.field-label')).map((l) => l.textContent);
			expect(labels).toEqual(['Gain (dB)']);
		}
	});

	it('leaves out a track with no fields to show', () => {
		const gain = rowKeys(schema).filter((k) => k.name === 'AudioTrackGainSlider');
		mount({ visibleKeys: [[], gain] });
		expect(screen.queryByRole('region', { name: 'Audio track 1' })).toBeNull();
		expect(row(2)).toBeTruthy();
	});

	it('leaves out a track the visible keys do not reach', () => {
		mount({ visibleKeys: [] });
		expect(screen.queryByRole('region')).toBeNull();
	});
});
