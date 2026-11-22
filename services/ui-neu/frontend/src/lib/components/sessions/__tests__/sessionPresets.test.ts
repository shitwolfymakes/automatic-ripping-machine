import { describe, it, expect } from 'vitest';
import type { MediaType, RipPresetView, TranscodePresetView } from '$lib/types/api.gen';
import { copyName, isRipPreset, ripPresetCopy, transcodePresetCopy } from '../sessionPresets';

const makeRip = (id = 'r1', name = 'rip r1') => ({
	id,
	name,
	media_type: 'movie' as MediaType,
	is_builtin: false,
	track_selection: 'main_feature' as const,
	identification_mode: 'required' as const,
	output_mode: 'tracks' as const,
	track_filters_json: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null
});

const makeTranscode = (id = 't1', name = 'tc t1') => ({
	id,
	name,
	media_type: 'movie' as MediaType,
	is_builtin: false,
	tool: 'handbrake' as const,
	preset_ref: null,
	handbrake_settings: null,
	container: 'mkv' as const,
	encoder: 'any_h265',
	extra_args: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null
});

describe('isRipPreset', () => {
	it('is true for a rip preset', () => {
		expect(isRipPreset(makeRip() as RipPresetView)).toBe(true);
	});

	it('is false for a transcode preset', () => {
		expect(isRipPreset(makeTranscode() as TranscodePresetView)).toBe(false);
	});
});

describe('copyName', () => {
	it('appends (copy) to the name', () => {
		expect(copyName('Alpha')).toBe('Alpha (copy)');
	});

	it('numbers the copy when (copy) is taken, using the next free number', () => {
		expect(copyName('Alpha', ['Alpha', 'Alpha (copy)'])).toBe('Alpha (copy 2)');
		expect(copyName('Alpha', ['Alpha (copy)', 'Alpha (copy 2)', 'Alpha (copy 4)'])).toBe('Alpha (copy 3)');
	});

	it('numbers from the original when cloning a copy', () => {
		expect(copyName('Alpha (copy)', ['Alpha', 'Alpha (copy)'])).toBe('Alpha (copy 2)');
		expect(copyName('Alpha (copy 2)', ['Alpha (copy)', 'Alpha (copy 2)'])).toBe('Alpha (copy 3)');
	});

	it('treats names that differ only in case or surrounding spaces as taken', () => {
		expect(copyName('Alpha', [' alpha (COPY) '])).toBe('Alpha (copy 2)');
	});

	it('keeps a name that only looks like a copy in the middle', () => {
		expect(copyName('Alpha (copy) Beta')).toBe('Alpha (copy) Beta (copy)');
	});
});

describe('ripPresetCopy', () => {
	it('copies the whole body, carrying the track filters', () => {
		const filters = { min_length: 600 };
		const p = { ...makeRip(), track_filters_json: filters } as RipPresetView;
		expect(ripPresetCopy(p)).toEqual({
			name: 'rip r1 (copy)',
			media_type: 'movie',
			track_selection: 'main_feature',
			identification_mode: 'required',
			output_mode: 'tracks',
			track_filters_json: filters
		});
	});

	it('names the copy clear of the taken names', () => {
		expect(ripPresetCopy(makeRip() as RipPresetView, ['rip r1 (copy)']).name).toBe('rip r1 (copy 2)');
	});

	it('copies null track filters as null', () => {
		expect(ripPresetCopy(makeRip() as RipPresetView).track_filters_json).toBeNull();
	});
});

describe('transcodePresetCopy', () => {
	it('keeps the HandBrake settings, so a clone of a tuned preset encodes the same', () => {
		const settings = { video: { quality: 20 } };
		const p = { ...makeTranscode(), handbrake_settings: settings } as unknown as TranscodePresetView;
		expect(transcodePresetCopy(p).handbrake_settings).toEqual(settings);
	});

	it('copies the whole body, carrying preset_ref and extra_args', () => {
		const p = { ...makeTranscode(), preset_ref: 'Fast 1080p30', extra_args: '--foo' } as TranscodePresetView;
		expect(transcodePresetCopy(p)).toEqual({
			name: 'tc t1 (copy)',
			media_type: 'movie',
			tool: 'handbrake',
			preset_ref: 'Fast 1080p30',
			handbrake_settings: null,
			container: 'mkv',
			encoder: 'any_h265',
			extra_args: '--foo'
		});
	});

	it('names the copy clear of the taken names', () => {
		expect(transcodePresetCopy(makeTranscode() as TranscodePresetView, ['tc t1 (copy)']).name).toBe('tc t1 (copy 2)');
	});

	it('turns missing preset_ref and extra_args into null', () => {
		const p = { ...makeTranscode(), preset_ref: undefined, extra_args: undefined } as unknown as TranscodePresetView;
		const body = transcodePresetCopy(p);
		expect(body.preset_ref).toBeNull();
		expect(body.extra_args).toBeNull();
	});
});
