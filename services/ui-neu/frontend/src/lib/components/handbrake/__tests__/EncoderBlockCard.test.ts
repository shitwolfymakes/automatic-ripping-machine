import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import { fireEvent } from '@testing-library/svelte';
import type { HandbrakeSchemaSlimView, SettingIssue, SlimFamily } from '$lib/types/api.gen';
import fixture from '$lib/handbrake/__tests__/fixtures/slim-schema.json';
import { blockFields, type EncoderCard } from '$lib/handbrake/encoderCards';
import EncoderBlockCard from '../EncoderBlockCard.svelte';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const family = (name: string): SlimFamily => schema.families.find((f) => f.name === name)!;
const allFields = (name: string) => ['bit_depth', ...blockFields(schema, family(name)).map((k) => k.name)];
const card = (over: Partial<EncoderCard> = {}): EncoderCard => ({
	family: 'x264',
	label: 'x264',
	state: 'open',
	device: null,
	...over
});

function baseProps(name: string, over: Record<string, unknown> = {}) {
	return {
		schema,
		family: family(name),
		card: card({ family: name, label: name }),
		block: {},
		base: null,
		inheritedDepth: 8,
		depthSource: 'default',
		open: true,
		fields: allFields(name),
		issues: [] as SettingIssue[],
		readonly: false,
		onchange: vi.fn(),
		onreset: vi.fn(),
		onexpand: vi.fn(),
		...over
	};
}

function mount(name: string, over: Record<string, unknown> = {}) {
	const onchange = vi.fn();
	const onreset = vi.fn();
	renderComponent(EncoderBlockCard, {
		props: {
			schema,
			family: family(name),
			card: card({ family: name, label: name }),
			block: {},
			base: null,
			inheritedDepth: 8,
			depthSource: 'default',
			open: true,
			fields: allFields(name),
			issues: [] as SettingIssue[],
			readonly: false,
			onchange,
			onreset,
			onexpand: vi.fn(),
			...over
		}
	});
	return { onchange, onreset };
}

describe('EncoderBlockCard', () => {
	afterEach(() => cleanup());

	it('carries the shared form card class', () => {
		mount('x264');
		expect(screen.getByRole('region', { name: 'x264' })).toHaveClass('form-card', 'encoder-card');
	});

	it('shows multi-pass, turbo and advanced options on x264', () => {
		mount('x264');
		expect(screen.getByLabelText('Multi-pass encoding')).toBeTruthy();
		expect(screen.getByLabelText('Turbo first pass')).toBeTruthy();
		expect(screen.getByLabelText('Use x264 advanced options')).toBeTruthy();
		expect(screen.getByLabelText('x264 advanced options')).toBeTruthy();
		expect(screen.getByLabelText('Extra encoder options')).toBeTruthy();
	});

	it('hides multi-pass, turbo and advanced options on NVENC', () => {
		mount('nvenc_h264');
		expect(screen.queryByLabelText('Multi-pass encoding')).toBeNull();
		expect(screen.queryByLabelText('Turbo first pass')).toBeNull();
		expect(screen.queryByLabelText('Use x264 advanced options')).toBeNull();
		expect(screen.queryByLabelText('x264 advanced options')).toBeNull();
	});

	it('labels the quality field with the scale and range', () => {
		mount('x264');
		expect(screen.getByLabelText('Quality (RF, 0 to 51)')).toBeTruthy();
	});

	it('renders only the fields it is given', () => {
		mount('x264', { fields: ['VideoPreset'] });
		expect(screen.getByLabelText('Encoder preset')).toBeTruthy();
		expect(screen.queryByLabelText('Bit depth')).toBeNull();
		expect(screen.queryByLabelText('Multi-pass encoding')).toBeNull();
		expect(screen.queryByLabelText('Encoder tune')).toBeNull();
	});

	it('renders bit depth alone when it is the only field', () => {
		mount('x264', { fields: ['bit_depth'] });
		expect(screen.getByLabelText('Bit depth')).toBeTruthy();
		expect(screen.queryByLabelText('Encoder preset')).toBeNull();
	});

	it('enables multi-pass and turbo when shown', () => {
		mount('x264');
		expect((screen.getByLabelText('Multi-pass encoding') as HTMLInputElement).disabled).toBe(false);
		expect((screen.getByLabelText('Turbo first pass') as HTMLInputElement).disabled).toBe(false);
		expect(screen.queryByText('Applies with average bitrate only')).toBeNull();
	});

	it('offers the variant lists for the resolved depth', () => {
		mount('x264', { block: { bit_depth: 10 } });
		const profile = screen.getByLabelText('Encoder profile') as HTMLSelectElement;
		expect(Array.from(profile.options).map((o) => o.value)).toContain('high10');
	});

	it('falls back to the first variant when the depth has none', () => {
		mount('x264', { block: { bit_depth: 12 } });
		const profile = screen.getByLabelText('Encoder profile') as HTMLSelectElement;
		expect(Array.from(profile.options).map((o) => o.value)).toContain('baseline');
	});

	it('labels the empty bit depth option by where the depth comes from', () => {
		mount('x265', { inheritedDepth: 10, depthSource: 'base' });
		expect(screen.getByRole('option', { name: '10-bit, from base preset' })).toBeTruthy();
		cleanup();
		mount('x265');
		expect(screen.getByRole('option', { name: '8-bit, default' })).toBeTruthy();
	});

	it('updates the default depth label when the source changes', async () => {
		const { rerender } = renderComponent(EncoderBlockCard, {
			props: baseProps('x265')
		});
		expect(screen.getByRole('option', { name: '8-bit, default' })).toBeTruthy();
		await rerender({ ...baseProps('x265'), block: { bit_depth: 10 } });
		expect(screen.getByRole('option', { name: '8-bit, default' })).toBeTruthy();
		await rerender({ ...baseProps('x265'), inheritedDepth: 10, depthSource: 'base' });
		expect(screen.getByRole('option', { name: '10-bit, from base preset' })).toBeTruthy();
	});

	it('emits a numeric bit depth, and clears it on the empty option', async () => {
		const { onchange, onreset } = mount('x265');
		const select = screen.getByLabelText('Bit depth') as HTMLSelectElement;
		await fireEvent.change(select, { target: { value: '10-bit' } });
		expect(onchange).toHaveBeenCalledWith('bit_depth', 10);
		await fireEvent.change(select, { target: { value: '' } });
		expect(onreset).toHaveBeenCalledWith('bit_depth');
	});

	it('shows the stored bit depth selected', () => {
		mount('x265', { block: { bit_depth: 10 } });
		expect((screen.getByLabelText('Bit depth') as HTMLSelectElement).value).toBe('10-bit');
	});

	it('marks a stored bit depth as Changed; an unstored one is not', () => {
		mount('x265', { block: { bit_depth: 10 } });
		expect(screen.getByText('Changed')).toBeTruthy();
		cleanup();
		mount('x265');
		expect(screen.queryByText('Changed')).toBeNull();
	});

	it('keeps a stored bit depth no variant offers as a selected extra option', () => {
		mount('x264', { block: { bit_depth: 12 } });
		const select = screen.getByLabelText('Bit depth') as HTMLSelectElement;
		expect(select.value).toBe('12-bit');
		expect(Array.from(select.options).map((o) => o.text)).toEqual(['8-bit, default', '8-bit', '10-bit', '12-bit']);
	});

	it('marks the bit depth select with its issue and shows the message under it', () => {
		const issues = [
			{ key: 'bit_depth', encoder: 'x264', code: 'not_in_list', message: 'bad depth' },
			{ key: 'bit_depth', encoder: 'x265', code: 'not_in_list', message: 'other depth' }
		] as SettingIssue[];
		mount('x264', { block: { bit_depth: 12 }, issues });
		const select = screen.getByLabelText('Bit depth');
		expect(select).toHaveAttribute('aria-invalid', 'true');
		expect(select).toHaveAttribute('aria-describedby', 'x264-bit-depth-error');
		expect(document.getElementById('x264-bit-depth-error')).toHaveTextContent('bad depth');
		expect(screen.queryByText('other depth')).toBeNull();
	});

	it('leaves the bit depth select unmarked without an issue', () => {
		mount('x264');
		expect(screen.getByLabelText('Bit depth')).not.toHaveAttribute('aria-invalid');
	});

	it('resets a stored bit depth from its Reset link', async () => {
		const { onreset } = mount('x265', { block: { bit_depth: 10 } });
		await fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
		expect(onreset).toHaveBeenCalledWith('bit_depth');
	});

	it('routes field edits and resets with the key name', async () => {
		const { onchange, onreset } = mount('x264', { block: { VideoPreset: 'slow' } });
		await fireEvent.change(screen.getByLabelText('Encoder preset'), { target: { value: 'fast' } });
		expect(onchange).toHaveBeenCalledWith('VideoPreset', 'fast');
		await fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
		expect(onreset).toHaveBeenCalledWith('VideoPreset');
	});

	it('renders block issues under their field and ignores other encoders', () => {
		const issues = [
			{ key: 'VideoPreset', encoder: 'x264', code: 'not_in_list', message: 'bad preset' },
			{ key: 'VideoPreset', encoder: 'x265', code: 'not_in_list', message: 'other card' },
			{ key: 'VideoPreset', encoder: null, code: 'not_in_list', message: 'common one' }
		] as SettingIssue[];
		mount('x264', { issues });
		expect(screen.getByText('bad preset')).toBeTruthy();
		expect(screen.queryByText('other card')).toBeNull();
		expect(screen.queryByText('common one')).toBeNull();
	});

	it('disables every control when read only', () => {
		mount('x264', { readonly: true });
		expect((screen.getByLabelText('Bit depth') as HTMLSelectElement).disabled).toBe(true);
		expect((screen.getByLabelText('Encoder preset') as HTMLSelectElement).disabled).toBe(true);
	});

	it('prefixes ids with the family so two cards do not clash', () => {
		mount('x264');
		expect(document.getElementById('x264-tunable-VideoPreset')).not.toBeNull();
	});

	it('names the device on a verified card', () => {
		mount('nvenc_h264', { card: card({ family: 'nvenc_h264', state: 'verified', device: 'NVIDIA H.264' }) });
		expect(screen.getByText('Verified on NVIDIA H.264')).toBeTruthy();
	});

	it('labels the CPU fallback card', () => {
		mount('x264', { card: card({ state: 'cpu-fallback' }) });
		expect(screen.getByText('Fallback when no GPU is free')).toBeTruthy();
	});

	it('shows a closed card as its title and Set values anyway, which asks to expand it', async () => {
		const onexpand = vi.fn();
		const { rerender } = renderComponent(EncoderBlockCard, {
			props: baseProps('qsv_h264', { card: card({ family: 'qsv_h264', state: 'collapsed' }), open: false, onexpand })
		});
		expect(screen.queryByLabelText('Encoder preset')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Set values anyway' }));
		expect(onexpand).toHaveBeenCalledOnce();
		await rerender(baseProps('qsv_h264', { card: card({ family: 'qsv_h264', state: 'collapsed' }), open: true }));
		expect(screen.getByLabelText('Encoder preset')).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'Set values anyway' })).toBeNull();
	});

	it('keeps x264 advanced options off the x265 card', () => {
		mount('x265');
		expect(screen.queryByLabelText('Use x264 advanced options')).toBeNull();
		expect(screen.queryByLabelText('x264 advanced options')).toBeNull();
	});

	it('labels the quality field with the scale and range per encoder', () => {
		mount('nvenc_h264');
		expect(screen.getByLabelText('Quality (CQ, 1 to 51)')).toBeTruthy();
	});

	it('shows the encoder defaults as inherited when the block stores none', () => {
		mount('x264');
		expect((screen.getByLabelText('Encoder preset') as HTMLSelectElement).value).toBe('medium');
		expect((screen.getByLabelText('Encoder tune') as HTMLSelectElement).value).toBe('none');
		expect((screen.getByLabelText('Encoder profile') as HTMLSelectElement).value).toBe('auto');
		expect((screen.getByLabelText('Encoder level') as HTMLSelectElement).value).toBe('auto');
	});

	it("shows the base preset's value as inherited when the base runs this encoder", () => {
		mount('x264', { base: { VideoEncoder: 'x264', VideoPreset: 'slow' } });
		expect((screen.getByLabelText('Encoder preset') as HTMLSelectElement).value).toBe('slow');
	});

	it('shows a stored value over the inherited default', () => {
		mount('x264', { block: { VideoPreset: 'fast' } });
		expect((screen.getByLabelText('Encoder preset') as HTMLSelectElement).value).toBe('fast');
	});

	it('puts the status line under a collapsed title, beside a link-styled button', () => {
		mount('qsv_h264', {
			card: card({ family: 'qsv_h264', label: 'Intel QSV H.264', state: 'collapsed' }),
			open: false
		});
		expect(screen.getByRole('heading', { name: 'Intel QSV H.264' })).toBeTruthy();
		expect(screen.getByText('No verified device')).toBeTruthy();
		const button = screen.getByRole('button', { name: 'Set values anyway' });
		expect(button.classList.contains('btn-link')).toBe(true);
		expect(button.closest('h4')).toBeNull();
	});

	it('shows no status badge on a card with no hardware state', () => {
		mount('x264');
		expect(document.querySelector('.encoder-card-badge')).toBeNull();
	});
});
