import { describe, it, expect } from 'vitest';
import type { MediaType, RipPresetView, TranscodePresetView } from '$lib/types/api.gen';
import { copyName, isRipPreset, ripPresetCopy, transcodePresetCopy } from '../session-presets';

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

	it('copies null track filters as null', () => {
		expect(ripPresetCopy(makeRip() as RipPresetView).track_filters_json).toBeNull();
	});
});

describe('transcodePresetCopy', () => {
	it('copies the whole body, carrying preset_ref and extra_args', () => {
		const p = { ...makeTranscode(), preset_ref: 'Fast 1080p30', extra_args: '--foo' } as TranscodePresetView;
		expect(transcodePresetCopy(p)).toEqual({
			name: 'tc t1 (copy)',
			media_type: 'movie',
			tool: 'handbrake',
			preset_ref: 'Fast 1080p30',
			container: 'mkv',
			encoder: 'any_h265',
			extra_args: '--foo'
		});
	});

	it('turns missing preset_ref and extra_args into null', () => {
		const p = { ...makeTranscode(), preset_ref: undefined, extra_args: undefined } as unknown as TranscodePresetView;
		const body = transcodePresetCopy(p);
		expect(body.preset_ref).toBeNull();
		expect(body.extra_args).toBeNull();
	});
});
