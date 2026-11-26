import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import { fireEvent } from '@testing-library/svelte';
import type { HandbrakeSchemaSlimView, SettingIssue, SlimKey } from '$lib/types/api.gen';
import fixture from '$lib/handbrake/__tests__/fixtures/slim-schema.json';
import TunableField from '../TunableField.svelte';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const key = (name: string): SlimKey => [...schema.keys, ...schema.audio_item_keys].find((k) => k.name === name)!;

function mount(name: string, over: Record<string, unknown> = {}) {
	const onchange = vi.fn();
	const onreset = vi.fn();
	const result = renderComponent(TunableField, {
		props: {
			key: key(name),
			value: undefined,
			inherited: undefined,
			stored: false,
			options: null,
			onchange,
			onreset,
			...over
		}
	});
	return { onchange, onreset, ...result };
}

describe('TunableField', () => {
	afterEach(() => cleanup());

	it('renders a checkbox from the inherited value and emits a boolean', async () => {
		const { onchange } = mount('ChapterMarkers', { inherited: true });
		const box = screen.getByLabelText(key('ChapterMarkers').label) as HTMLInputElement;
		expect(box.checked).toBe(true);
		await fireEvent.click(box);
		expect(onchange).toHaveBeenCalledWith(false);
	});

	it('shows the stored value rather than the inherited one', () => {
		mount('ChapterMarkers', { value: false, inherited: true, stored: true });
		expect((screen.getByLabelText(key('ChapterMarkers').label) as HTMLInputElement).checked).toBe(false);
	});

	it('renders a select and emits the option with its original type', async () => {
		const { onchange } = mount('AudioBitrate', { options: [-1, 128, 'auto'], inherited: 128 });
		const select = screen.getByLabelText(key('AudioBitrate').label) as HTMLSelectElement;
		expect(select.value).toBe('128');
		await fireEvent.change(select, { target: { value: '-1' } });
		expect(onchange).toHaveBeenLastCalledWith(-1);
		await fireEvent.change(select, { target: { value: 'auto' } });
		expect(onchange).toHaveBeenLastCalledWith('auto');
	});

	it('falls back to the raw text when the option list lacks it, and tolerates no options', async () => {
		const { onchange } = mount('AudioBitrate', { options: null });
		const select = screen.getByLabelText(key('AudioBitrate').label) as HTMLSelectElement;
		expect(select.options).toHaveLength(1);
		select.add(new Option('x', 'x'));
		await fireEvent.change(select, { target: { value: 'x' } });
		expect(onchange).toHaveBeenCalledWith('x');
	});

	it('renders a number input with the schema limits and emits numbers', async () => {
		const k = { ...key('PictureWidth'), limits: [16, 8000] as [number, number] };
		const onchange = vi.fn();
		renderComponent(TunableField, {
			props: { key: k, value: 1280, inherited: null, stored: true, options: null, onchange, onreset: vi.fn() }
		});
		const input = screen.getByLabelText(k.label) as HTMLInputElement;
		expect(input.min).toBe('16');
		expect(input.max).toBe('8000');
		expect(input.value).toBe('1280');
		await fireEvent.change(input, { target: { value: '640' } });
		expect(onchange).toHaveBeenCalledWith(640);
	});

	it('emits nothing for an empty number input and has no limits without them', async () => {
		const { onchange } = mount('PictureWidth');
		const input = screen.getByLabelText(key('PictureWidth').label) as HTMLInputElement;
		expect(input.value).toBe('');
		await fireEvent.change(input, { target: { value: '' } });
		expect(onchange).not.toHaveBeenCalled();
	});

	it('renders a text input and emits the text', async () => {
		const { onchange } = mount('PresetName', { inherited: 'abc' });
		const input = screen.getByLabelText(key('PresetName').label) as HTMLInputElement;
		expect(input.value).toBe('');
		expect(input.placeholder).toBe('abc');
		await fireEvent.change(input, { target: { value: 'xyz' } });
		expect(onchange).toHaveBeenCalledWith('xyz');
	});

	it('shows a stored text value in the text input', () => {
		mount('PresetName', { stored: true, value: 'mine', inherited: 'abc' });
		const input = screen.getByLabelText(key('PresetName').label) as HTMLInputElement;
		expect([input.value, input.placeholder]).toEqual(['mine', '']);
	});

	it('renders a list of strings as chips and emits string[]', async () => {
		const { onchange } = mount('AudioLanguageList', { inherited: ['eng'] });
		expect(screen.getByText('English (eng)')).toBeInTheDocument();
		await fireEvent.input(screen.getByLabelText('Add value'), { target: { value: 'fre' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		expect(onchange).toHaveBeenCalledWith(['eng', 'fra']);
	});

	it('treats a non-list value as no chips', () => {
		mount('AudioLanguageList', { inherited: null });
		expect(screen.queryByRole('button', { name: /^Remove/ })).toBeNull();
	});

	it('offers a select for a list key with options', async () => {
		const { onchange } = mount('AudioCopyMask', {
			value: ['copy:aac'],
			stored: true,
			options: ['copy:aac', 'copy:ac3']
		});
		await fireEvent.change(screen.getByLabelText('Add value'), { target: { value: 'copy:ac3' } });
		expect(onchange).toHaveBeenCalledWith(['copy:aac', 'copy:ac3']);
	});

	it('shows an empty placeholder in a select with no value', () => {
		mount('AudioBitrate', { options: [128, 192] });
		expect((screen.getByLabelText(key('AudioBitrate').label) as HTMLSelectElement).value).toBe('');
	});

	it('renders no control of its own for the audio track list', () => {
		const { container } = mount('AudioList');
		expect(container.querySelector('.tunable-field')).toBeNull();
		expect(screen.queryByText(key('AudioList').label)).toBeNull();
	});

	it('shows Reset only when stored, and calls onreset', async () => {
		const first = mount('ChapterMarkers');
		expect(screen.queryByRole('button', { name: 'Reset' })).toBeNull();
		first.unmount();
		const { onreset } = mount('ChapterMarkers', { stored: true, value: true });
		await fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
		expect(onreset).toHaveBeenCalledTimes(1);
	});

	it('shows the issue', () => {
		const issue = { key: 'ChapterMarkers', code: 'wrong_type', message: 'Not a boolean' } as SettingIssue;
		mount('ChapterMarkers', { issue });
		expect(screen.getByRole('alert')).toHaveTextContent('Not a boolean');
	});

	it('disables the control and Reset', () => {
		mount('ChapterMarkers', { disabled: true, stored: true, value: true });
		expect(screen.getByLabelText(key('ChapterMarkers').label)).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Reset' })).toBeDisabled();
	});
});

describe('TunableField idPrefix and range', () => {
	afterEach(() => cleanup());

	it('prefixes the control id', () => {
		mount('VideoPreset', { idPrefix: 'x264-' });
		expect(document.getElementById('x264-tunable-VideoPreset')).not.toBeNull();
	});

	it('applies a range and step to a number field', () => {
		mount('VideoQualitySlider', { range: { min: 1, max: 51, step: 0.5 } });
		const input = document.getElementById('tunable-VideoQualitySlider') as HTMLInputElement;
		expect([input.min, input.max, input.step]).toEqual(['1', '51', '0.5']);
	});
});

describe('TunableField fidelity', () => {
	afterEach(() => cleanup());
	const labelled = (): SlimKey => ({
		...key('VideoQualityType'),
		option_labels: { '1': 'Average bitrate', '2': 'Constant quality' }
	});

	it('renders option labels, keeps raw values and emits numbers', async () => {
		const { onchange } = mount('VideoQualityType', { key: labelled(), options: [1, 2], inherited: 1 });
		const select = screen.getByLabelText(labelled().label) as HTMLSelectElement;
		expect(screen.getByRole('option', { name: 'Constant quality' })).toHaveValue('2');
		expect(select.value).toBe('1');
		await fireEvent.change(select, { target: { value: '2' } });
		expect(onchange).toHaveBeenCalledWith(2);
	});

	it('falls back to the value when an option has no label', () => {
		mount('VideoQualityType', { key: labelled(), options: [1, 7], inherited: 7 });
		expect(screen.getByRole('option', { name: '7' })).toHaveValue('7');
	});

	it('selects the inherited value of an unstored select', () => {
		mount('VideoQualityType', { options: ['fast', 'medium'], inherited: 'medium' });
		expect((screen.getByLabelText(key('VideoQualityType').label) as HTMLSelectElement).value).toBe('medium');
	});

	it('shows the inherited number as a placeholder with an empty value', () => {
		mount('PictureWidth', { inherited: 1920 });
		const input = screen.getByLabelText(key('PictureWidth').label) as HTMLInputElement;
		expect([input.value, input.placeholder]).toEqual(['', '1920']);
	});

	it('lays a checkbox out like an input: the label, then a control line holding the box', () => {
		mount('ChapterMarkers', { stored: true, value: true });
		const label = screen.getByText(key('ChapterMarkers').label);
		const box = screen.getByRole('checkbox', { name: key('ChapterMarkers').label });
		const line = box.closest('.field-control-line')!;
		expect(label).toHaveAttribute('for', box.id);
		expect(line).not.toBeNull();
		expect(label.compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(line).not.toContainElement(label);
		expect(screen.getByText('Changed')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: /HandBrake docs for/ })).toBeInTheDocument();
	});

	it('marks a checkbox invalid and points it at its issue', () => {
		mount('ChapterMarkers', { issue: { message: 'nope' } });
		const box = screen.getByRole('checkbox', { name: key('ChapterMarkers').label });
		expect(box).toHaveAttribute('aria-invalid', 'true');
		expect(box).toHaveAttribute('aria-describedby', screen.getByRole('alert').id);
	});

	it('leaves the flip checkbox outside a control line', () => {
		mount('PictureRotate');
		expect(screen.getByRole('checkbox', { name: 'Flip horizontally' }).closest('.field-control-line')).toBeNull();
	});

	it('has no raw key line; an info link carries the key and opens the docs for its group', () => {
		mount('PictureTopCrop');
		expect(screen.queryByText('PictureTopCrop')).toBeNull();
		const link = screen.getByRole('link', { name: 'HandBrake docs for Top crop (PictureTopCrop)' });
		expect(link).toHaveAttribute('title', 'HandBrake key: PictureTopCrop');
		expect(link).toHaveAttribute('href', 'https://handbrake.fr/docs/en/latest/advanced/resizing-video.html');
		expect(link).toHaveAttribute('target', '_blank');
		expect(link).toHaveAttribute('rel', 'noopener noreferrer');
	});

	it('links to the docUrl it is given in place of the group page', () => {
		mount('VideoPreset', { docUrl: 'https://example.test/docs.html' });
		expect(screen.getByRole('link', { name: /HandBrake docs for/ })).toHaveAttribute(
			'href',
			'https://example.test/docs.html'
		);
	});

	it('marks a stored field as Changed on the field and beside the label; an unstored one is not', () => {
		const stored = mount('PictureWidth', { stored: true, value: 1 });
		expect(stored.container.querySelector('.tunable-field')).toHaveAttribute('data-changed');
		expect(screen.getByText('Changed')).toBeInTheDocument();
		stored.unmount();
		const inherited = mount('PictureWidth', { inherited: 2 });
		expect(inherited.container.querySelector('.tunable-field')).not.toHaveAttribute('data-changed');
		expect(screen.queryByText('Changed')).toBeNull();
	});

	it('offers Reset on a stored field; an inherited one has none', () => {
		const stored = mount('PictureWidth', { stored: true, value: 1 });
		expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument();
		stored.unmount();
		mount('PictureWidth', { inherited: 2 });
		expect(screen.queryByRole('button', { name: 'Reset' })).toBeNull();
	});

	// The danger border is field.css's .field-control[aria-invalid='true'] rule; no field-level class
	// or component rule restyles the control's border, so the stored state cannot override it.
	it('marks a stored field with an issue invalid, with nothing restyling its control', () => {
		const issue = { key: 'PictureWidth', code: 'out_of_range', message: 'Too wide' } as SettingIssue;
		const { container } = mount('PictureWidth', { stored: true, value: 99999, issue });
		const input = screen.getByLabelText(key('PictureWidth').label);
		expect(input).toHaveAttribute('aria-invalid', 'true');
		expect(input).toHaveAttribute('aria-describedby', 'tunable-PictureWidth-error');
		// Svelte's scoping hash (svelte-xxxx) is not a styling class of its own.
		const classes = (el: Element) => [...el.classList].filter((c) => !c.startsWith('svelte-'));
		expect(classes(input)).toEqual(['field-control']);
		expect(classes(container.querySelector('.tunable-field')!)).toEqual(['tunable-field']);
	});

	it('updates the shown value when stored and value props change', async () => {
		const { rerender } = mount('PictureWidth', { inherited: 2 });
		const input = () => screen.getByLabelText(key('PictureWidth').label) as HTMLInputElement;
		expect([input().value, input().placeholder]).toEqual(['', '2']);
		await rerender({ stored: true, value: 5 });
		expect([input().value, input().placeholder]).toEqual(['5', '']);
		await rerender({ value: 9 });
		expect(input().value).toBe('9');
	});

	it('keeps a stored select value the list lacks as an extra option labelled with it', () => {
		mount('AudioBitrate', { options: [128, 192], value: 'weird', stored: true });
		const select = screen.getByLabelText(key('AudioBitrate').label) as HTMLSelectElement;
		expect([...select.options].map((o) => o.textContent)).toEqual(['128', '192', 'weird']);
		expect(select.value).toBe('weird');
	});

	describe('PictureRotate', () => {
		const angle = () => screen.getByLabelText(key('PictureRotate').label) as HTMLSelectElement;
		const flip = () => screen.getByLabelText('Flip horizontally') as HTMLInputElement;

		it('shows the angle and flip of the effective value', () => {
			mount('PictureRotate', { value: 'angle=90:hflip=1', stored: true });
			expect(angle().value).toBe('90');
			expect(flip().checked).toBe(true);
		});

		it('emits the formatted value when the angle or flip changes', async () => {
			const { onchange } = mount('PictureRotate', { inherited: 'angle=0:hflip=0' });
			await fireEvent.change(angle(), { target: { value: '180' } });
			expect(onchange).toHaveBeenLastCalledWith('angle=180:hflip=0');
			await fireEvent.click(flip());
			expect(onchange).toHaveBeenLastCalledWith('angle=0:hflip=1');
		});

		it('reads a malformed value as no rotation', () => {
			mount('PictureRotate', { value: 'nonsense', stored: true });
			expect(angle().value).toBe('0');
			expect(flip().checked).toBe(false);
		});
	});

	describe('PicturePadColor', () => {
		const padKey = { ...key('PicturePadColor'), source: { kind: 'static', ref: 'PicturePadColor' } };
		const names = ['black', 'white', 'red'];
		const mountPad = (over: Record<string, unknown> = {}) =>
			mount('PicturePadColor', { key: padKey, options: names, inherited: 'black', ...over });
		const select = () => screen.getByLabelText('Padding color') as HTMLSelectElement;
		const custom = () => screen.queryByLabelText('Custom padding color') as HTMLInputElement | null;

		it('selects a listed name and shows no custom input', () => {
			mountPad({ value: 'white', stored: true });
			expect(select().value).toBe('white');
			expect(custom()).toBeNull();
		});

		it('emits a picked name', async () => {
			const { onchange } = mountPad();
			await fireEvent.change(select(), { target: { value: 'red' } });
			expect(onchange).toHaveBeenCalledWith('red');
		});

		it('shows an unlisted stored value as Custom with the value in the text input', () => {
			mountPad({ value: '#1a2b3c', stored: true });
			expect(select().selectedOptions[0].textContent).toBe('Custom\u2026');
			expect(custom()!.value).toBe('#1a2b3c');
		});

		it('reveals the text input on Custom, stores the hex verbatim, ignores empty and returns on a name', async () => {
			const { onchange } = mountPad();
			await fireEvent.change(select(), { target: { value: '__custom__' } });
			expect(onchange).not.toHaveBeenCalled();
			await fireEvent.change(custom()!, { target: { value: '#FFaa00' } });
			expect(onchange).toHaveBeenLastCalledWith('#FFaa00');
			await fireEvent.change(custom()!, { target: { value: '' } });
			expect(onchange).toHaveBeenCalledTimes(1);
			await fireEvent.change(select(), { target: { value: 'white' } });
			expect(onchange).toHaveBeenLastCalledWith('white');
			expect(custom()).toBeNull();
		});

		it('closes the custom input when the field is reset', async () => {
			const { onreset } = mountPad({ value: 'red', stored: true });
			await fireEvent.change(select(), { target: { value: '__custom__' } });
			expect(custom()).not.toBeNull();
			await fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
			expect(onreset).toHaveBeenCalled();
			expect(custom()).toBeNull();
		});

		it('marks the custom text input invalid alongside the select when the field has an issue', () => {
			const issue = { key: 'PicturePadColor', code: 'not_in_list', message: 'Bad colour' } as SettingIssue;
			mountPad({ value: '#zz', stored: true, issue });
			for (const control of [select(), custom()!]) {
				expect(control).toHaveAttribute('aria-invalid', 'true');
				expect(control).toHaveAttribute('aria-describedby', 'tunable-PicturePadColor-error');
			}
			expect(document.getElementById('tunable-PicturePadColor-error')).toHaveTextContent('Bad colour');
		});

		it('tolerates no options', () => {
			mountPad({ options: null });
			expect(select().options).toHaveLength(1);
		});
	});

	it('shows a stored B code as its language and stores the T code on a pick', async () => {
		const { onchange } = mount('SubtitleLanguageList', { value: ['fre'], stored: true });
		expect(screen.getByText('French (fra)')).toBeInTheDocument();
		await fireEvent.input(screen.getByLabelText('Add value'), { target: { value: 'German' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		expect(onchange).toHaveBeenLastCalledWith(['fre', 'deu']);
	});

	it('picks a language by label and shows a stored unknown code raw until removed', async () => {
		const { onchange } = mount('AudioLanguageList', { value: ['zzz'], stored: true });
		expect(screen.getByText('zzz')).toBeInTheDocument();
		await fireEvent.input(screen.getByLabelText('Add value'), { target: { value: 'German (deu)' } });
		expect(onchange).toHaveBeenLastCalledWith(['zzz', 'deu']);
		await fireEvent.click(screen.getByRole('button', { name: 'Remove zzz' }));
		expect(onchange).toHaveBeenLastCalledWith([]);
	});
});
