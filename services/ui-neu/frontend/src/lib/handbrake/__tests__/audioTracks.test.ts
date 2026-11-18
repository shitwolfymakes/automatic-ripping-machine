import { describe, it, expect } from 'vitest';
import type { HandbrakeSchemaSlimView, SettingIssue } from '$lib/types/api.gen';
import fixture from './fixtures/slim-schema.json';
import {
	addTrack,
	clearTrackField,
	listIssues,
	mixdownsFor,
	moveTrack,
	removeTrack,
	rowEncoder,
	rowIssue,
	rowKeys,
	rowOptions,
	samplerates,
	setTrackField,
	visibleTrackKeys
} from '../audioTracks';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const itemKey = (name: string) => schema.audio_item_keys.find((k) => k.name === name)!;
const a = { AudioEncoder: 'av_aac' };
const b = { AudioEncoder: 'ac3' };
const c = { AudioEncoder: 'opus' };

describe('audioTracks', () => {
	it('addTrack appends the template item without touching the input', () => {
		const list = [a];
		const next = addTrack(list, schema);
		expect(list).toEqual([a]);
		expect(next).toHaveLength(2);
		expect(next[1]).toMatchObject({ AudioEncoder: 'copy:ac3', AudioMixdown: 'dpl2', AudioBitrate: 192 });
		expect(Object.keys(next[1])).toHaveLength(schema.audio_item_keys.length);
	});

	it('removeTrack drops one row', () => {
		expect(removeTrack([a, b, c], 1)).toEqual([a, c]);
	});

	it('moveTrack swaps neighbours and leaves out-of-range moves unchanged', () => {
		expect(moveTrack([a, b, c], 1, -1)).toEqual([b, a, c]);
		expect(moveTrack([a, b, c], 1, 1)).toEqual([a, c, b]);
		const list = [a, b];
		const same = moveTrack(list, 0, -1);
		expect(same).toEqual(list);
		expect(same).not.toBe(list);
		expect(moveTrack(list, 1, 1)).toEqual(list);
		expect(moveTrack(list, 5, -1)).toEqual(list);
		expect(moveTrack(list, -1, 1)).toEqual(list);
	});

	it('setTrackField and clearTrackField change only the named row', () => {
		const list = [a, b];
		expect(setTrackField(list, 1, 'AudioBitrate', 128)).toEqual([a, { ...b, AudioBitrate: 128 }]);
		expect(clearTrackField([a, { ...b, AudioBitrate: 128 }], 1, 'AudioBitrate')).toEqual([a, b]);
		expect(list).toEqual([a, b]);
	});

	it('rowEncoder reads the row, then the schema default, then empty', () => {
		expect(rowEncoder(a, schema)).toBe('av_aac');
		expect(rowEncoder({}, schema)).toBe('copy:ac3');
		expect(rowEncoder({}, { ...schema, audio_item_keys: [] })).toBe('');
	});

	it('rowEncoder prints a non-string value as its text, never [object Object]', () => {
		expect(rowEncoder({ AudioEncoder: 5 }, schema)).toBe('5');
		expect(rowEncoder({ AudioEncoder: true }, schema)).toBe('true');
		expect(rowEncoder({ AudioEncoder: { nested: 1 } }, schema)).toBe('');
		const objectDefault = {
			...schema,
			audio_item_keys: schema.audio_item_keys.map((k) => (k.name === 'AudioEncoder' ? { ...k, default: { x: 1 } } : k))
		};
		expect(rowEncoder({}, objectDefault)).toBe('');
		const numberDefault = {
			...schema,
			audio_item_keys: schema.audio_item_keys.map((k) => (k.name === 'AudioEncoder' ? { ...k, default: 7 } : k))
		};
		expect(rowEncoder({}, numberDefault)).toBe('7');
	});

	it('mixdownsFor narrows to the encoder, and a passthrough encoder offers none only', () => {
		expect(mixdownsFor(schema, 'av_aac')).toContain('5point1');
		expect(mixdownsFor(schema, 'copy:ac3')).toEqual(['none']);
		expect(mixdownsFor(schema, 'nope')).toEqual([]);
		expect(mixdownsFor({ ...schema, audio_item_keys: [] }, 'av_aac')).toEqual([]);
	});

	it('samplerates is the schema-wide list as strings (the slim view has no per-encoder rates)', () => {
		const extras = (schema.source_extras.AudioSamplerate ?? []).map(String);
		expect(samplerates(schema)).toEqual([...new Set([...schema.lists.audio_samplerates.map(String), ...extras])]);
		expect(samplerates(schema)).toEqual(expect.arrayContaining(schema.lists.audio_samplerates.map(String)));
		expect(samplerates({ ...schema, audio_item_keys: [] })).toEqual([]);
	});

	it('treat a key without a source as having no options', () => {
		const bare = {
			...schema,
			audio_item_keys: schema.audio_item_keys.map((k) =>
				k.name === 'AudioMixdown' || k.name === 'AudioSamplerate' ? { ...k, source: null } : k
			)
		};
		expect(mixdownsFor(bare, 'av_aac')).toEqual([]);
		expect(samplerates(bare)).toEqual([]);
	});

	it('rowKeys orders encoder first, then the row layout, with extras last', () => {
		const names = rowKeys(schema).map((k) => k.name);
		expect(names.slice(0, 8)).toEqual([
			'AudioEncoder',
			'AudioMixdown',
			'AudioSamplerate',
			'AudioBitrate',
			'AudioTrackQualityEnable',
			'AudioTrackQuality',
			'AudioTrackGainSlider',
			'AudioTrackDRCSlider'
		]);
		expect(names).toHaveLength(schema.audio_item_keys.length);
		expect(names.slice(8)).toContain('AudioDitherMethod');
	});

	it('rowOptions picks the right list per key', () => {
		expect(rowOptions(itemKey('AudioMixdown'), { AudioEncoder: 'copy:ac3' }, schema)).toEqual(['none']);
		expect(rowOptions(itemKey('AudioSamplerate'), a, schema)).toEqual(samplerates(schema));
		expect(rowOptions(itemKey('AudioEncoder'), a, schema)).toEqual(schema.lists.audio_encoders);
		expect(rowOptions(itemKey('AudioTrackGainSlider'), a, schema)).toBeNull();
	});

	it('rowIssue and listIssues route issues by key', () => {
		const issues = [
			{ key: 'AudioList[0].AudioMixdown', message: 'm', code: 'not_in_list' },
			{ key: 'AudioList', message: 'whole', code: 'wrong_type' },
			{ key: 'Other', message: 'x', code: 'wrong_type' }
		] as SettingIssue[];
		expect(rowIssue(issues, 0, 'AudioMixdown')?.message).toBe('m');
		expect(rowIssue(issues, 1, 'AudioMixdown')).toBeUndefined();
		expect(listIssues(issues).map((i) => i.message)).toEqual(['whole']);
	});
});

describe('visibleTrackKeys', () => {
	const all = { text: '', changedOnly: false };
	const names = (track: Record<string, unknown>, f = all, ctx: Record<string, unknown> = {}) =>
		visibleTrackKeys(rowKeys(schema), track, ctx, f).map((k) => k.name);

	it('shows bitrate, not quality, while the track does not use quality', () => {
		expect(names({})).toContain('AudioBitrate');
		expect(names({})).not.toContain('AudioTrackQuality');
	});

	it('shows quality, not bitrate, once the track uses quality', () => {
		const shown = names({ AudioTrackQualityEnable: true, AudioBitrate: 128 });
		expect(shown).toContain('AudioTrackQuality');
		expect(shown).not.toContain('AudioBitrate');
	});

	it('lets the track override the panel context', () => {
		expect(names({ AudioTrackQualityEnable: false }, all, { AudioTrackQualityEnable: true })).toContain('AudioBitrate');
	});

	it('keeps only the fields matching the filter text', () => {
		expect(names({}, { text: 'gain', changedOnly: false })).toEqual(['AudioTrackGainSlider']);
		expect(names({}, { text: 'track', changedOnly: false })).toEqual([
			'AudioTrackQualityEnable',
			'AudioTrackGainSlider',
			'AudioTrackDRCSlider'
		]);
	});

	it('keeps only the fields the track sets under Changed only', () => {
		expect(names({ AudioMixdown: 'stereo' }, { text: '', changedOnly: true })).toEqual(['AudioMixdown']);
	});
});
