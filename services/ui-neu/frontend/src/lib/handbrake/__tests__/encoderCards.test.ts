import { describe, it, expect } from 'vitest';
import type { EncoderAvailabilityView, HandbrakeSchemaSlimView, SlimFamily } from '$lib/types/api.gen';
import fixture from './fixtures/slim-schema.json';
import {
	blockDefault,
	blockFields,
	cardKey,
	cardOpen,
	cardVariant,
	cardStatusLine,
	depthOptions,
	depthText,
	encoderCards,
	perEncoderLine,
	showsAmdNote,
	visibleCardFields,
	type EncoderCard
} from '../encoderCards';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const family = (name: string): SlimFamily => schema.families.find((f) => f.name === name)!;

function entry(id: string, over: Partial<EncoderAvailabilityView> = {}): EncoderAvailabilityView {
	return {
		id,
		label: id,
		group: 'any',
		engine: 'handbrake',
		kind: 'gpu',
		vendor: null,
		codec: 'h264',
		available: false,
		reason: null,
		...over
	};
}
const nvidia = entry('nvenc_h264', { label: 'NVIDIA H.264', group: 'nvenc', vendor: 'nvenc', available: true });
const amd = entry('vaapi_h264', { label: 'AMD H.264', group: 'vaapi', vendor: 'vaapi', available: true });

describe('encoderCards', () => {
	it('orders any_h264 by vendor rank then CPU, with states', () => {
		const cards = encoderCards('any_h264', null, schema, [nvidia, amd], null);
		expect(cards.map((c) => [c.family, c.state])).toEqual([
			['nvenc_h264', 'verified'],
			['qsv_h264', 'collapsed'],
			['x264', 'cpu-fallback']
		]);
		expect(cards[0].device).toBe('NVIDIA H.264');
		expect(cards[1].device).toBeNull();
	});

	it('skips a GPU family the schema lacks', () => {
		const slim = { ...schema, families: schema.families.filter((f) => f.name !== 'qsv_h264') };
		expect(encoderCards('any_h264', null, slim, [], null).map((c) => c.family)).toEqual(['nvenc_h264', 'x264']);
	});

	it('pins a cpu id to its one open family', () => {
		expect(encoderCards('cpu_h265', null, schema, [], null)).toEqual([
			{ family: 'x265', label: 'x265', state: 'open', device: null }
		]);
	});

	it('pins a GPU id, verified when available', () => {
		expect(encoderCards('nvenc_h264', null, schema, [nvidia], null)[0].state).toBe('verified');
		expect(encoderCards('qsv_h264', null, schema, [], null)[0].state).toBe('open');
	});

	it('maps the base preset encoder variant to its family', () => {
		const cards = encoderCards('preset', 'H.265 MKV 1080p30', schema, [], 'x265_10bit');
		expect(cards.map((c) => [c.family, c.state])).toEqual([['x265', 'open']]);
	});

	it('has no card for a preset without a base, or for vaapi or unknown ids', () => {
		expect(encoderCards('preset', null, schema, [], 'x265')).toEqual([]);
		expect(encoderCards('preset', 'Base', schema, [], null)).toEqual([]);
		expect(encoderCards('vaapi_h264', null, schema, [amd], null)).toEqual([]);
		expect(encoderCards('bogus', null, schema, [], null)).toEqual([]);
	});

	it('uses svt_av1 for cpu av1', () => {
		expect(encoderCards('any_av1', null, schema, [], null).at(-1)?.family).toBe('svt_av1');
	});
});

describe('blockFields', () => {
	const names = (f: string) => blockFields(schema, family(f)).map((k) => k.name);

	it('gives x264 multi-pass, turbo and advanced options', () => {
		expect(names('x264')).toEqual([
			'VideoPreset',
			'VideoTune',
			'VideoProfile',
			'VideoLevel',
			'VideoQualitySlider',
			'VideoMultiPass',
			'VideoTurboMultiPass',
			'x264UseAdvancedOptions',
			'x264Option',
			'VideoOptionExtra'
		]);
	});

	it('gives NVENC neither multi-pass nor turbo nor advanced options', () => {
		expect(names('nvenc_h264')).toEqual([
			'VideoPreset',
			'VideoTune',
			'VideoProfile',
			'VideoLevel',
			'VideoQualitySlider',
			'VideoOptionExtra'
		]);
	});

	it('gives x265 turbo but no advanced options', () => {
		expect(names('x265')).toContain('VideoTurboMultiPass');
		expect(names('x265')).not.toContain('x264UseAdvancedOptions');
		expect(names('x265')).not.toContain('x264Option');
	});

	it('skips a key the schema lacks', () => {
		const slim = { ...schema, keys: schema.keys.filter((k) => k.name !== 'VideoTune') };
		expect(blockFields(slim, family('x264')).map((k) => k.name)).not.toContain('VideoTune');
	});
});

describe('blockFields reads its keys from the schema', () => {
	it('leaves out a key the schema does not call encoder-specific', () => {
		const slim = { ...schema, encoder_specific_keys: schema.encoder_specific_keys.filter((n) => n !== 'VideoLevel') };
		expect(blockFields(slim, family('x264')).map((k) => k.name)).not.toContain('VideoLevel');
	});

	it('puts a block key it has no display rank for last', () => {
		const slim = { ...schema, encoder_specific_keys: ['VideoFramerate', ...schema.encoder_specific_keys] };
		expect(
			blockFields(slim, family('x265'))
				.map((k) => k.name)
				.at(-1)
		).toBe('VideoFramerate');
	});
});

describe('showsAmdNote', () => {
	it('shows for any_* with an AMD device', () => {
		expect(showsAmdNote('any_h264', [nvidia, amd])).toBe(true);
	});
	it('hides without an AMD device or for pinned ids', () => {
		expect(showsAmdNote('any_h264', [nvidia])).toBe(false);
		expect(showsAmdNote('cpu_h264', [amd])).toBe(false);
	});
});

describe('cardStatusLine', () => {
	const card = (state: EncoderCard['state'], device: string | null = null): EncoderCard => ({
		family: 'x',
		label: 'X',
		state,
		device
	});

	it('names the verified device', () => {
		expect(cardStatusLine(card('verified', 'nvidia://0'))).toBe('Verified on nvidia://0');
	});

	it('says the CPU card is the fallback', () => {
		expect(cardStatusLine(card('cpu-fallback'))).toBe('Fallback when no GPU is free');
	});

	it('says a GPU family with no verified device has none', () => {
		expect(cardStatusLine(card('collapsed'))).toBe('No verified device');
	});

	it('has nothing to report for a card with no hardware state', () => {
		expect(cardStatusLine(card('open'))).toBe('');
	});
});

describe('perEncoderLine', () => {
	it('names the preset encoder and why each card keeps its own values', () => {
		expect(perEncoderLine('Any GPU H.264')).toBe(
			'Any GPU H.264 can land on the encoders below. Each keeps its own speed preset, profile, level and quality, because the values differ between them.'
		);
	});
});

describe('blockDefault', () => {
	const key = (name: string) => schema.keys.find((k) => k.name === name)!;
	const x264 = family('x264').variants[0];

	it("takes the schema default when it is one of the variant's values", () => {
		expect(blockDefault(key('VideoPreset'), x264, null)).toBe('medium');
	});

	it("falls back to the variant's first value when the default is not offered", () => {
		expect(blockDefault(key('VideoTune'), x264, null)).toBe('none');
	});

	it("takes the base preset's value when it names this variant's encoder", () => {
		expect(blockDefault(key('VideoPreset'), x264, { VideoEncoder: 'x264', VideoPreset: 'slow' })).toBe('slow');
	});

	it('ignores the base value when it is for another encoder or not offered', () => {
		expect(blockDefault(key('VideoPreset'), x264, { VideoEncoder: 'x265', VideoPreset: 'slow' })).toBe('medium');
		expect(blockDefault(key('VideoPreset'), x264, { VideoEncoder: 'x264', VideoPreset: 'bogus' })).toBe('medium');
	});

	it('has no default when the variant offers no values for the list', () => {
		expect(blockDefault(key('VideoPreset'), { ...x264, presets: [] }, null)).toBeNull();
	});

	it('has no default for a key that is not a variant list', () => {
		expect(blockDefault(key('VideoQualitySlider'), x264, null)).toBeNull();
	});
});

describe('visibleCardFields', () => {
	const all = { text: '', changedOnly: false };
	const v8 = family('x264').variants[0];
	const cq = { VideoQualityType: 2 };

	it('lists bit depth and every applicable block field, in display order', () => {
		expect(visibleCardFields(schema, family('x264'), v8, {}, cq, all)).toEqual([
			'bit_depth',
			...blockFields(schema, family('x264'))
				.map((k) => k.name)
				.filter((n) => n !== 'VideoMultiPass' && n !== 'VideoTurboMultiPass' && n !== 'x264Option')
		]);
	});

	it('hides multi-pass and turbo under constant quality, the quality slider under average bitrate', () => {
		const vbr = visibleCardFields(schema, family('x264'), v8, {}, { VideoQualityType: 1 }, all);
		expect(vbr).toContain('VideoMultiPass');
		expect(vbr).toContain('VideoTurboMultiPass');
		expect(vbr).not.toContain('VideoQualitySlider');
	});

	it('reads gates from the block over the panel context', () => {
		const shown = visibleCardFields(schema, family('x264'), v8, { x264UseAdvancedOptions: true }, cq, all);
		expect(shown).toContain('x264Option');
	});

	it('keeps only the fields matching the filter text', () => {
		expect(visibleCardFields(schema, family('x264'), v8, {}, cq, { text: 'preset', changedOnly: false })).toEqual([
			'VideoPreset'
		]);
		expect(visibleCardFields(schema, family('x264'), v8, {}, cq, { text: 'bit depth', changedOnly: false })).toEqual([
			'bit_depth'
		]);
	});

	it('keeps only stored fields under Changed only', () => {
		const block = { bit_depth: 10, VideoTune: 'film' };
		expect(visibleCardFields(schema, family('x264'), v8, block, cq, { text: '', changedOnly: true })).toEqual([
			'bit_depth',
			'VideoTune'
		]);
	});
});

describe('cardOpen', () => {
	const c = (state: EncoderCard['state']): EncoderCard => ({ family: 'qsv_h264', label: 'QSV', state, device: null });

	it('keeps a collapsed card closed until expanded or it stores a value', () => {
		expect(cardOpen(c('collapsed'), {}, false)).toBe(false);
		expect(cardOpen(c('collapsed'), {}, true)).toBe(true);
		expect(cardOpen(c('collapsed'), { VideoPreset: 'quality' }, false)).toBe(true);
	});

	it('opens every other card', () => {
		expect(cardOpen(c('open'), {}, false)).toBe(true);
		expect(cardOpen(c('cpu-fallback'), {}, false)).toBe(true);
	});
});

describe('card labels', () => {
	const x264 = family('x264');
	const key = (name: string) => schema.keys.find((k) => k.name === name)!;

	it('resolves the variant from the block depth, then the inherited depth, else the first variant', () => {
		expect(cardVariant(x264, { bit_depth: 10 }, 8).depth).toBe(10);
		expect(cardVariant(x264, {}, 10).depth).toBe(10);
		expect(cardVariant(x264, { bit_depth: 99 }, 8)).toBe(x264.variants[0]);
	});

	it('offers each variant depth, selecting the stored one', () => {
		expect(depthText(10)).toBe('10-bit');
		expect(depthOptions(x264, {})).toEqual([
			{ text: '8-bit', selected: false },
			{ text: '10-bit', selected: false }
		]);
		expect(depthOptions(x264, { bit_depth: 10 }).filter((o) => o.selected)).toEqual([
			{ text: '10-bit', selected: true }
		]);
	});

	it('adds a stored depth no variant offers as a selected extra option', () => {
		expect(depthOptions(x264, { bit_depth: 12 }).at(-1)).toEqual({ text: '12-bit', selected: true });
		expect(depthOptions(x264, { bit_depth: 12 })).toHaveLength(3);
	});

	it('shows variant lists as selects, renames extra options and names the quality scale', () => {
		const v = x264.variants[0];
		expect(cardKey(key('VideoPreset'), v).source).toEqual({ kind: 'variant', ref: 'VideoPreset' });
		expect(cardKey(key('VideoOptionExtra'), v).label).toBe('Extra encoder options');
		expect(cardKey(key('VideoQualitySlider'), v).label).toBe('Quality (RF, 0 to 51)');
		expect(cardKey(key('VideoMultiPass'), v)).toBe(key('VideoMultiPass'));
	});

	it('filters card fields by the label the card shows, not the schema label', () => {
		const v = x264.variants[0];
		const fields = (text: string) =>
			visibleCardFields(schema, x264, v, {}, { VideoQualityType: 2 }, { text, changedOnly: false });
		expect(key('VideoOptionExtra').label).toBe('Additional encoder options');
		expect(fields('extra encoder')).toEqual(['VideoOptionExtra']);
		expect(fields('additional')).toEqual([]);
		expect(fields('(rf')).toEqual(['VideoQualitySlider']);
		expect(fields('constant')).toEqual([]);
	});
});
