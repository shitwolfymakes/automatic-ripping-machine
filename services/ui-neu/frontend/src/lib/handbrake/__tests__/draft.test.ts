import { describe, it, expect } from 'vitest';
import type { TranscodePresetView } from '$lib/types/api.gen';
import {
	type Draft,
	clearsSettings,
	draftToCreate,
	draftToUpdate,
	initialDraft,
	isVaapiEncoder,
	settingsCount,
	showTabs
} from '../draft';

function preset(over: Partial<TranscodePresetView> = {}): TranscodePresetView {
	return {
		id: 't1',
		name: 'Movies',
		media_type: 'tv',
		is_builtin: false,
		tool: 'handbrake',
		preset_ref: 'Fast 1080p30',
		handbrake_settings: { common: { PictureWidth: 1280 }, encoders: { x264: { VideoPreset: 'slow' } } },
		issues: [],
		host_notes: [],
		container: 'mp4',
		encoder: 'any_h264',
		extra_args: '--x',
		created_by_user_id: null,
		created_at: null,
		updated_at: null,
		...over
	};
}

function draft(over: Partial<Draft> = {}): Draft {
	return { ...initialDraft(null), ...over };
}

describe('initialDraft', () => {
	it('starts a new preset on HandBrake defaults with nothing stored', () => {
		expect(initialDraft(null)).toEqual({
			name: '',
			media_type: 'movie',
			tool: 'handbrake',
			preset_ref: null,
			container: 'mkv',
			encoder: 'preset',
			extra_args: '',
			settings: { common: {}, encoders: {} }
		});
	});

	it('copies an existing preset, null extra args as empty text', () => {
		const d = initialDraft(preset({ extra_args: null }));
		expect(d).toMatchObject({ name: 'Movies', media_type: 'tv', preset_ref: 'Fast 1080p30', encoder: 'any_h264' });
		expect(d.extra_args).toBe('');
		expect(d.settings).toEqual({ common: { PictureWidth: 1280 }, encoders: { x264: { VideoPreset: 'slow' } } });
	});

	it('fills missing settings sections', () => {
		expect(initialDraft(preset({ handbrake_settings: null })).settings).toEqual({ common: {}, encoders: {} });
		expect(initialDraft(preset({ handbrake_settings: { common: { A: 1 } } })).settings).toEqual({
			common: { A: 1 },
			encoders: {}
		});
	});
});

describe('draftToCreate / draftToUpdate', () => {
	it('creates with every field and the settings payload', () => {
		const d = draft({ name: 'N', extra_args: '--y', settings: { common: { A: 1 }, encoders: {} } });
		expect(draftToCreate(d)).toEqual({
			name: 'N',
			media_type: 'movie',
			tool: 'handbrake',
			preset_ref: null,
			container: 'mkv',
			encoder: 'preset',
			extra_args: '--y',
			handbrake_settings: { common: { A: 1 }, encoders: {} }
		});
	});

	it('sends null settings once everything is cleared (Review Focus 2)', () => {
		const d = draft({ settings: { common: {}, encoders: { x264: {} } }, extra_args: '' });
		expect(draftToUpdate(d).handbrake_settings).toBeNull();
		expect(draftToUpdate(d).extra_args).toBeNull();
	});

	it('updates without media_type', () => {
		expect(draftToUpdate(draft())).not.toHaveProperty('media_type');
	});

	it('sends no settings when the tabs do not apply', () => {
		const stored = { common: { A: 1 }, encoders: {} };
		expect(draftToCreate(draft({ tool: 'abcde', settings: stored })).handbrake_settings).toBeNull();
		expect(draftToUpdate(draft({ encoder: 'vaapi_h264', settings: stored })).handbrake_settings).toBeNull();
	});
});

describe('settingsCount', () => {
	it('counts common keys and every block key', () => {
		expect(settingsCount({ common: { A: 1, B: 2 }, encoders: { x264: { C: 1 }, x265: { C: 1, D: 2 } } })).toBe(5);
		expect(settingsCount(null)).toBe(0);
		expect(settingsCount({})).toBe(0);
	});
});

describe('showTabs', () => {
	it('is HandBrake with a non-VAAPI encoder', () => {
		expect(showTabs(draft({ encoder: 'any_h264' }))).toBe(true);
		expect(showTabs(draft({ encoder: 'vaapi_h265' }))).toBe(false);
		expect(showTabs(draft({ tool: 'abcde' }))).toBe(false);
	});
});

describe('isVaapiEncoder and clearsSettings', () => {
	it('detects VAAPI catalog ids', () => {
		expect(isVaapiEncoder('vaapi_av1')).toBe(true);
		expect(isVaapiEncoder('any_h264')).toBe(false);
	});

	it('warns only when hidden tabs would drop stored settings', () => {
		const stored = { common: { A: 1 }, encoders: {} };
		expect(clearsSettings(draft({ tool: 'none', settings: stored }))).toBe(true);
		expect(clearsSettings(draft({ encoder: 'vaapi_h264', settings: stored }))).toBe(true);
		expect(clearsSettings(draft({ tool: 'none' }))).toBe(false);
		expect(clearsSettings(draft({ encoder: 'any_h264', settings: stored }))).toBe(false);
	});
});
