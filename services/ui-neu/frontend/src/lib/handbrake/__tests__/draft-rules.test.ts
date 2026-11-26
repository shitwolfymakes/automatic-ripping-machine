import { describe, it, expect } from 'vitest';
import type { HandbrakeSchemaSlimView } from '$lib/types/api.gen';
import fixture from './fixtures/slim-schema.json';
import { type Draft, initialDraft } from '../draft';
import { applyField, onEncoderChange, onToolChange } from '../draft-rules';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
function draft(over: Partial<Draft> = {}): Draft {
	return { ...initialDraft(null), ...over };
}

describe('onToolChange', () => {
	it('locks the encoder to preset for abcde and none', () => {
		expect(onToolChange(draft({ encoder: 'any_h264' }), 'abcde')).toMatchObject({ tool: 'abcde', encoder: 'preset' });
		expect(onToolChange(draft({ encoder: 'any_h264' }), 'none').encoder).toBe('preset');
	});

	it('keeps the encoder for HandBrake', () => {
		expect(onToolChange(draft({ tool: 'none', encoder: 'any_h264' }), 'handbrake').encoder).toBe('any_h264');
	});
});

describe('onEncoderChange (Review Focus 4)', () => {
	const settings = { common: { A: 1 }, encoders: { x264: { VideoPreset: 'slow' }, x265: { VideoPreset: 'fast' } } };

	it('drops blocks of families the new encoder cannot reach', () => {
		const next = onEncoderChange(draft({ encoder: 'any_h264', settings }), 'any_h265', schema);
		expect(next.encoder).toBe('any_h265');
		expect(next.settings).toEqual({ common: { A: 1 }, encoders: { x265: { VideoPreset: 'fast' } } });
	});

	it('keeps the base encoder family for the preset encoder', () => {
		const next = onEncoderChange(draft({ preset_ref: 'Fast 1080p30', settings }), 'preset', schema, 'x264');
		expect(Object.keys(next.settings.encoders!)).toEqual(['x264']);
	});
});

describe('applyField', () => {
	const settings = { common: {}, encoders: { x264: { VideoTune: 'film' } } };

	it('routes tool and encoder edits through their rules', () => {
		expect(applyField(draft({ encoder: 'any_h264' }), 'tool', 'none', schema, {}).encoder).toBe('preset');
		expect(applyField(draft({ encoder: 'any_h264', settings }), 'encoder', 'any_h265', schema, {}).settings).toEqual({
			common: {},
			encoders: {}
		});
	});

	it('only sets the encoder without a schema', () => {
		const next = applyField(draft({ encoder: 'any_h264', settings }), 'encoder', 'any_h265', null, {});
		expect(next).toMatchObject({ encoder: 'any_h265', settings });
	});

	it('stores an empty base preset as null and other fields as given', () => {
		expect(applyField(draft({ preset_ref: 'Fast 1080p30' }), 'preset_ref', '', schema, {}).preset_ref).toBeNull();
		expect(applyField(draft(), 'preset_ref', 'Fast 480p30', schema, {}).preset_ref).toBe('Fast 480p30');
		expect(applyField(draft(), 'name', 'N', schema, {}).name).toBe('N');
	});
});

describe('applyField on the base preset of a preset-encoder draft', () => {
	const settings = { common: { A: 1 }, encoders: { x264: { VideoTune: 'film' }, x265: { VideoTune: 'grain' } } };
	const bases = { 'Fast 1080p30': { VideoEncoder: 'x264' }, 'H.265 MKV 1080p30': { VideoEncoder: 'x265_10bit' } };

	it('drops the blocks a loaded new base no longer reaches', () => {
		const next = applyField(draft({ settings }), 'preset_ref', 'H.265 MKV 1080p30', schema, bases);
		expect(next.preset_ref).toBe('H.265 MKV 1080p30');
		expect(next.settings).toEqual({ common: { A: 1 }, encoders: { x265: { VideoTune: 'grain' } } });
	});

	it('drops every block when the base is cleared', () => {
		const next = applyField(draft({ preset_ref: 'Fast 1080p30', settings }), 'preset_ref', '', schema, bases);
		expect(next.settings).toEqual({ common: { A: 1 }, encoders: {} });
	});

	it('keeps the blocks while the new base has not loaded', () => {
		expect(applyField(draft({ settings }), 'preset_ref', 'Fast 480p30', schema, bases).settings).toEqual(settings);
	});

	it('keeps the blocks without a schema or for another encoder', () => {
		expect(applyField(draft({ settings }), 'preset_ref', 'Fast 1080p30', null, bases).settings).toEqual(settings);
		const anyCodec = draft({ encoder: 'any_h264', settings });
		expect(applyField(anyCodec, 'preset_ref', 'Fast 1080p30', schema, bases).settings).toEqual(settings);
	});

	it('resolves the base family from the loaded bases on an encoder change', () => {
		const start = draft({ encoder: 'any_h264', preset_ref: 'Fast 1080p30', settings });
		expect(Object.keys(applyField(start, 'encoder', 'preset', schema, bases).settings.encoders!)).toEqual(['x264']);
	});

	it('reaches no family on an encoder change while the base has not loaded', () => {
		const start = draft({ encoder: 'any_h264', preset_ref: 'Fast 480p30', settings });
		expect(applyField(start, 'encoder', 'preset', schema, bases).settings.encoders).toEqual({});
	});
});
