import { describe, it, expect } from 'vitest';
import type {
	HandbrakeSchemaSlimView,
	SettingIssue,
	SlimFamily,
	SlimKey,
	TranscodePresetView
} from '$lib/types/api.gen';
import { ApiError, NETWORK_ERROR_MESSAGE } from '$lib/api/client';
import fixture from './fixtures/slim-schema.json';
import {
	CPU_HERE_NOTE,
	audioListValue,
	blockOf,
	commonOf,
	applyField,
	baseVideoEncoder,
	cardFamilies,
	clearsSettings,
	isVaapiEncoder,
	commonKeys,
	draftToCreate,
	draftToUpdate,
	footerNote,
	inheritedDepth,
	inheritedValue,
	initialDraft,
	issuesFor,
	keyShown,
	audioListShown,
	panelContext,
	onEncoderChange,
	onToolChange,
	rowFlags,
	saveFailure,
	schemaLoadError,
	settingsCount,
	showTabs,
	sidebarTitle,
	panelCards,
	usageLabel,
	type Draft
} from '../sidebarModel';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const family = (name: string): SlimFamily => schema.families.find((f) => f.name === name)!;
const key = (name: string): SlimKey => schema.keys.find((k) => k.name === name)!;
const issue = (over: Partial<SettingIssue>): SettingIssue => ({
	key: 'VideoQualitySlider',
	encoder: null,
	code: 'out_of_range',
	message: 'Too high',
	...over
});

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

describe('footerNote', () => {
	it('is the CPU note only with the host note', () => {
		expect(footerNote(preset({ host_notes: ['encodes_on_cpu_here'] }))).toBe(CPU_HERE_NOTE);
		expect(CPU_HERE_NOTE).toBe('Encodes on CPU on this host: no verified non-AMD GPU for this codec');
		expect(footerNote(preset({ host_notes: [] }))).toBeNull();
		expect(footerNote(preset({ host_notes: undefined }))).toBeNull();
		expect(footerNote(null)).toBeNull();
	});
});

describe('settingsCount', () => {
	it('counts common keys and every block key', () => {
		expect(settingsCount({ common: { A: 1, B: 2 }, encoders: { x264: { C: 1 }, x265: { C: 1, D: 2 } } })).toBe(5);
		expect(settingsCount(null)).toBe(0);
		expect(settingsCount({})).toBe(0);
	});
});

describe('rowFlags', () => {
	it('names the settings count, issues and the CPU note', () => {
		expect(rowFlags(preset({ issues: [issue({})], host_notes: ['encodes_on_cpu_here'] }))).toEqual({
			settings: '2 settings',
			needsReview: true,
			cpuHere: true
		});
		expect(rowFlags(preset({ handbrake_settings: { common: { A: 1 } } })).settings).toBe('1 setting');
	});

	it('is empty for a plain preset or none', () => {
		const empty = { settings: null, needsReview: false, cpuHere: false };
		expect(rowFlags(preset({ handbrake_settings: null, issues: undefined }))).toEqual(empty);
		expect(rowFlags(null)).toEqual(empty);
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

describe('commonKeys reads the schema', () => {
	it('drops a key the schema calls ARM-owned', () => {
		const slim = { ...schema, arm_owned_keys: [...schema.arm_owned_keys, 'ChapterMarkers'] };
		expect(commonKeys(slim, 'chapters')).toEqual([]);
	});
});

describe('commonKeys hides what the schema hides', () => {
	it('never lists a hidden key', () => {
		expect(schema.hidden_keys).toContain('VideoScaler');
		expect(commonKeys(schema, 'dimensions').map((k) => k.name)).not.toContain('VideoScaler');
	});
});

describe('sidebarTitle and usageLabel', () => {
	it('names each mode', () => {
		expect(sidebarTitle('new')).toBe('New transcode preset');
		expect(sidebarTitle('edit')).toBe('Edit transcode preset');
		expect(sidebarTitle('view')).toBe('View transcode preset');
	});

	it('pluralises sessions', () => {
		expect(usageLabel(0)).toBe('Used by 0 sessions');
		expect(usageLabel(1)).toBe('Used by 1 session');
		expect(usageLabel(3)).toBe('Used by 3 sessions');
	});
});

describe('inherited values', () => {
	it('reads the base, then the schema default', () => {
		expect(inheritedValue(key('VideoQualityType'), { VideoQualityType: 1 })).toBe(1);
		expect(inheritedValue(key('VideoQualityType'), {})).toBe(2);
		expect(inheritedValue(key('VideoQualityType'), null)).toBe(2);
	});

	it('builds the panel context from the schema defaults, then the base, then the preset', () => {
		const ctx = panelContext(
			schema,
			{ common: { VideoQualityType: 1 } },
			{ PicturePadMode: 'custom', VideoQualityType: 2 }
		);
		expect(ctx.VideoQualityType).toBe(1);
		expect(ctx.PicturePadMode).toBe('custom');
		expect(ctx.PictureCropMode).toBe(0);
		expect(panelContext(schema, {}, null).VideoQualityType).toBe(2);
	});

	it('reads the base video encoder only when it is text', () => {
		expect(baseVideoEncoder({ VideoEncoder: 'x264' })).toBe('x264');
		expect(baseVideoEncoder({ VideoEncoder: 3 })).toBeNull();
		expect(baseVideoEncoder(null)).toBeNull();
	});

	it('inherits bit depth from a same-family base encoder, else 8', () => {
		expect(inheritedDepth(family('x265'), { VideoEncoder: 'x265_10bit' })).toEqual({ depth: 10, source: 'base' });
		expect(inheritedDepth(family('x265'), { VideoEncoder: 'x264' })).toEqual({ depth: 8, source: 'default' });
		expect(inheritedDepth(family('x265'), null)).toEqual({ depth: 8, source: 'default' });
	});
});

describe('settings access', () => {
	it('reads sections that may be missing', () => {
		expect(commonOf({})).toEqual({});
		expect(commonOf({ common: { A: 1 } })).toEqual({ A: 1 });
		expect(blockOf({}, 'x264')).toEqual({});
		expect(blockOf({ encoders: { x264: { B: 2 } } }, 'x264')).toEqual({ B: 2 });
	});

	it('takes the audio tracks from the preset, then the base, else none', () => {
		const tracks = [{ AudioEncoder: 'av_aac' }];
		expect(audioListValue(key('AudioList'), { common: { AudioList: tracks } }, null)).toEqual(tracks);
		expect(audioListValue(key('AudioList'), {}, { AudioList: tracks })).toEqual(tracks);
		expect(audioListValue(key('AudioList'), {}, { AudioList: 'junk' })).toEqual([]);
	});
});

describe('commonKeys', () => {
	it('leaves out ARM-owned and encoder-specific keys', () => {
		const video = commonKeys(schema, 'video').map((k) => k.name);
		expect(video).toContain('VideoQualityType');
		expect(video).not.toContain('VideoEncoder');
		expect(video).not.toContain('VideoHWDecode');
		expect(video).not.toContain('VideoPreset');
		expect(commonKeys(schema, 'summary').map((k) => k.name)).not.toContain('PresetName');
	});
});

describe('filtering', () => {
	const none = { text: '', changedOnly: false };
	const ctx = panelContext(schema, {}, null);

	it('shows a key matching the text, and only stored ones under Changed only', () => {
		expect(keyShown(key('VideoQualityType'), false, none, ctx)).toBe(true);
		expect(keyShown(key('VideoQualityType'), false, { text: 'rate control', changedOnly: false }, ctx)).toBe(true);
		expect(keyShown(key('VideoQualityType'), false, { text: 'denoise', changedOnly: false }, ctx)).toBe(false);
		expect(keyShown(key('VideoQualityType'), false, { text: '', changedOnly: true }, ctx)).toBe(false);
		expect(keyShown(key('VideoQualityType'), true, { text: '', changedOnly: true }, ctx)).toBe(true);
	});

	it('hides a key another setting gates off, even when it is stored', () => {
		expect(keyShown(key('VideoAvgBitrate'), true, none, ctx)).toBe(false);
		expect(keyShown(key('VideoAvgBitrate'), true, none, { ...ctx, VideoQualityType: 1 })).toBe(true);
	});

	it('shows the audio track list unfiltered, and while filtering only when a track shows a field', () => {
		const shown = [[key('AlignAVStart')]];
		expect(audioListShown(none, false, [])).toBe(true);
		expect(audioListShown({ text: 'gain', changedOnly: false }, false, [[], []])).toBe(false);
		expect(audioListShown({ text: 'gain', changedOnly: false }, false, [[], ...shown])).toBe(true);
	});

	it('under Changed only shows the audio track list only when the preset stores its own', () => {
		const shown = [[key('AlignAVStart')]];
		expect(audioListShown({ text: '', changedOnly: true }, false, shown)).toBe(false);
		expect(audioListShown({ text: '', changedOnly: true }, true, shown)).toBe(true);
	});
});

describe('cardFamilies', () => {
	it('pairs each card with its family and drops families the schema lacks', () => {
		const card = (family: string) => ({ family, label: family, state: 'open' as const, device: null });
		const pairs = cardFamilies([card('x264'), card('nope')], schema);
		expect(pairs).toEqual([{ card: card('x264'), family: family('x264') }]);
	});
});

describe('issues', () => {
	const list = [
		issue({ key: 'PictureWidth', message: 'w' }),
		issue({ key: 'VideoPreset', encoder: 'x264', message: 'p' }),
		issue({ key: 'preset_ref', message: 'ref' }),
		issue({ key: 'handbrake_settings', message: 'whole' }),
		issue({ key: 'NotAKey', message: 'unknown' }),
		issue({ key: 'AudioMixdown', message: 'mix' }),
		issue({ key: 'bit_depth', encoder: 'x265', message: 'depth' })
	];

	it('finds the issue of a common or preset-block field', () => {
		expect(issuesFor(list, 'PictureWidth')?.message).toBe('w');
		expect(issuesFor(list, 'VideoPreset')).toBeUndefined();
		expect(issuesFor(list, 'VideoPreset', 'x264')?.message).toBe('p');
		expect(issuesFor(list, 'preset_ref')?.message).toBe('ref');
	});

	it('pairs the reachable encoder cards with their families', () => {
		expect(panelCards(schema, 'cpu_h264', null, [], null).map((c) => c.family.name)).toEqual(['x264']);
		expect(panelCards(schema, 'preset', 'Fast 1080p30', [], { VideoEncoder: 'x265' })[0].card.family).toBe('x265');
	});
});

describe('schemaLoadError', () => {
	it('is an Error only while unavailable', () => {
		expect(schemaLoadError('unavailable', 'boom')?.message).toBe('boom');
		expect(schemaLoadError('unavailable', null)?.message).toBe('No HandBrake schema loaded yet');
		expect(schemaLoadError('ready', 'boom')).toBeNull();
	});
});

describe('saveFailure', () => {
	it('marks fields for a 422 with an issue list', () => {
		const issues = [issue({})];
		const f = saveFailure(new ApiError(422, 'API 422', { detail: { issues } }));
		expect(f).toEqual({ issues, message: 'Fix the marked settings and save again.', schemaMissing: false });
	});

	it('keeps a 422 without issues as a plain message', () => {
		expect(saveFailure(new ApiError(422, 'Bad name', { detail: 'Bad name' }))).toEqual({
			issues: null,
			message: 'Bad name',
			schemaMissing: false
		});
		expect(saveFailure(new ApiError(422, 'Bad', null)).issues).toBeNull();
	});

	it('flags a 503 as no schema loaded', () => {
		expect(saveFailure(new ApiError(503, 'No HandBrake schema loaded yet', null))).toEqual({
			issues: null,
			message: 'No HandBrake schema loaded yet',
			schemaMissing: true
		});
	});

	it('uses the network message for anything else', () => {
		expect(saveFailure(new TypeError('fetch failed')).message).toBe(NETWORK_ERROR_MESSAGE);
	});
});
