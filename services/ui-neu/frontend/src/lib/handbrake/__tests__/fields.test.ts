import { describe, it, expect } from 'vitest';
import type { HandbrakeSchemaSlimView, SlimKey } from '$lib/types/api.gen';
import fixture from './fixtures/slim-schema.json';
import {
	TABS,
	fieldKind,
	fieldOptions,
	fieldView,
	groupsForTab,
	keysForTab,
	numberLimits,
	optionLabel
} from '../fields';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const key = (name: string): SlimKey => {
	const found = [...schema.keys, ...schema.audio_item_keys].find((k) => k.name === name);
	if (!found) throw new Error(name);
	return found;
};

describe('fieldKind', () => {
	it.each([
		['ChapterMarkers', 'checkbox'],
		['VideoFramerateMode', 'select'],
		['AudioBitrate', 'select'],
		['PictureWidth', 'number'],
		['AudioLanguageList', 'chips'],
		['AudioCopyMask', 'chips'],
		['AudioList', 'audio-list'],
		['PresetName', 'text']
	])('%s is %s', (name, kind) => {
		expect(fieldKind(key(name))).toBe(kind);
	});

	it('maps a float without a source to number', () => {
		expect(fieldKind({ ...key('PictureWidth'), type: 'float' })).toBe('number');
	});
});

describe('fieldOptions', () => {
	it('is null for a key without a source', () => {
		expect(fieldOptions(key('PictureWidth'), schema, {})).toBeNull();
	});

	it('reads a static enum from the schema', () => {
		expect(fieldOptions(key('VideoFramerateMode'), schema, {})).toEqual(schema.static_enums['VideoFramerateMode']);
	});

	it('reads a schema list and appends the extras once', () => {
		const opts = fieldOptions(key('AudioSamplerate'), schema, {})!;
		expect(opts).toContain('auto');
		expect(opts.filter((v) => v === 'auto')).toHaveLength(1);
	});

	it('does not repeat an extra the list already has', () => {
		const k = key('AudioBitrate');
		const patched = { ...schema, lists: { ...schema.lists, audio_bitrates: [-1, 128] } };
		expect(fieldOptions(k, patched, {})).toEqual([-1, 128]);
	});

	it('uses the filter named by the ref', () => {
		expect(fieldOptions(key('PictureChromaSmoothPreset'), schema, {})).toEqual(schema.filters['chroma_smooth'].presets);
		expect(fieldOptions(key('PictureChromaSmoothTune'), schema, {})).toEqual(schema.filters['chroma_smooth'].tunes);
	});

	it('follows the selector key chosen in context', () => {
		expect(fieldOptions(key('PictureDenoisePreset'), schema, { PictureDenoiseFilter: 'nlmeans' })).toEqual(
			schema.filters['nlmeans'].presets
		);
		expect(fieldOptions(key('PictureDenoiseTune'), schema, { PictureDenoiseFilter: 'hqdn3d' })).toEqual(
			schema.filters['hqdn3d'].tunes
		);
	});

	it('resolves a selector value through the alias table', () => {
		expect(fieldOptions(key('PictureDeinterlacePreset'), schema, { PictureDeinterlaceFilter: 'deinterlace' })).toEqual(
			schema.filters['yadif'].presets
		);
	});

	it('is empty when the selector is off or unset', () => {
		expect(fieldOptions(key('PictureDenoisePreset'), schema, { PictureDenoiseFilter: 'off' })).toEqual([]);
		expect(fieldOptions(key('PictureDenoisePreset'), schema, {})).toEqual([]);
		expect(fieldOptions(key('PictureDenoiseTune'), schema, { PictureDenoiseFilter: 'off' })).toEqual([]);
	});

	it('lists mixdowns for the chosen audio encoder', () => {
		expect(fieldOptions(key('AudioMixdown'), schema, { AudioEncoder: 'av_aac' })).toEqual(
			schema.audio_mixdowns_by_encoder['av_aac']
		);
		expect(fieldOptions(key('AudioMixdown'), schema, { AudioEncoder: 'nope' })).toEqual([]);
		expect(fieldOptions(key('AudioMixdown'), schema, {})).toEqual([]);
	});

	it('never looks a selector or encoder up by the text [object Object]', () => {
		const trap = {
			...schema,
			filters: { ...schema.filters, '[object Object]': { presets: ['trap'], tunes: ['trap'] } },
			audio_mixdowns_by_encoder: { ...schema.audio_mixdowns_by_encoder, '[object Object]': ['trap'] }
		} as unknown as HandbrakeSchemaSlimView;
		expect(fieldOptions(key('PictureDenoisePreset'), trap, { PictureDenoiseFilter: { a: 1 } })).toEqual([]);
		expect(fieldOptions(key('AudioMixdown'), trap, { AudioEncoder: { a: 1 } })).toEqual([]);
	});

	it('reads a numeric selector value as its text', () => {
		const numeric = {
			...schema,
			filters: { ...schema.filters, '3': { presets: ['three'], tunes: [] } }
		} as unknown as HandbrakeSchemaSlimView;
		expect(fieldOptions(key('PictureDenoisePreset'), numeric, { PictureDenoiseFilter: 3 })).toEqual(['three']);
	});

	it('is empty for an unknown static enum, list or source kind', () => {
		const src = (kind: string, ref: string): SlimKey => ({ ...key('PictureWidth'), source: { kind, ref } });
		expect(fieldOptions(src('static', 'nope'), schema, {})).toEqual([]);
		expect(fieldOptions(src('schema_list', 'nope'), schema, {})).toEqual([]);
		expect(fieldOptions(src('other', 'x'), schema, {})).toEqual([]);
	});
});

describe('numberLimits', () => {
	it('is null when the key has none', () => {
		expect(numberLimits(key('PictureWidth'))).toBeNull();
	});

	it('maps the limits tuple', () => {
		expect(numberLimits({ ...key('PictureWidth'), limits: [1, 9] })).toEqual({ min: 1, max: 9 });
	});
});

describe('tabs', () => {
	it('lists the seven tabs in order', () => {
		expect(TABS.map((t) => t.id)).toEqual([
			'summary',
			'dimensions',
			'filters',
			'video',
			'audio',
			'subtitles',
			'chapters'
		]);
		expect(TABS.map((t) => t.label)).toEqual([
			'Summary',
			'Dimensions',
			'Filters',
			'Video',
			'Audio',
			'Subtitles',
			'Chapters'
		]);
	});

	it('picks the keys of one tab', () => {
		const names = keysForTab(schema, 'chapters').map((k) => k.name);
		expect(names).toEqual(['ChapterMarkers']);
		expect(keysForTab(schema, 'filters').every((k) => k.tab === 'filters')).toBe(true);
	});
});

describe('optionLabel', () => {
	const key = {
		name: 'VideoQualityType',
		option_labels: { '1': 'Average bitrate', '2': 'Constant quality' }
	} as unknown as SlimKey;

	it('returns the schema label for a value', () => {
		expect(optionLabel(key, 2)).toBe('Constant quality');
	});
	it('falls back to the value, with or without a label map', () => {
		expect(optionLabel(key, 7)).toBe('7');
		expect(optionLabel({ name: 'X' } as unknown as SlimKey, 'a')).toBe('a');
	});
});

describe('fieldView', () => {
	const base = { value: undefined, inherited: undefined, stored: false, options: null };

	it('selects the inherited option and keeps numeric raw values', () => {
		const view = fieldView(key('AudioBitrate'), { ...base, options: [-1, 128, 'auto'], inherited: 128 });
		expect(view.kind).toBe('select');
		expect(view.options.map((o) => [o.value, o.raw, o.selected])).toEqual([
			['-1', -1, false],
			['128', 128, true],
			['auto', 'auto', false]
		]);
	});

	it('prefers the stored value over the inherited one', () => {
		const view = fieldView(key('AudioBitrate'), { ...base, options: [1, 2], value: 1, inherited: 2, stored: true });
		expect(view.shown).toBe(1);
		expect(view.options.map((o) => o.selected)).toEqual([true, false]);
		expect(view.stored).toBe(true);
	});

	it('selects nothing for an unstored select with no inherited value', () => {
		const view = fieldView(key('AudioBitrate'), { ...base, options: [1, 2] });
		expect(view.options.map((o) => o.selected)).toEqual([false, false]);
	});

	it('treats null options as an empty list', () => {
		expect(fieldView(key('AudioBitrate'), base).options).toEqual([]);
	});

	it('labels options through the schema', () => {
		const labelled = { ...key('AudioBitrate'), option_labels: { '1': 'Average' } } as SlimKey;
		expect(fieldView(labelled, { ...base, options: [1, 2] }).options.map((o) => o.label)).toEqual(['Average', '2']);
	});

	it('shows the inherited value as a placeholder with an empty input', () => {
		const view = fieldView(key('PictureWidth'), { ...base, inherited: 1920 });
		expect([view.inputValue, view.placeholder]).toEqual(['', '1920']);
	});

	it('shows the stored value as the input value with no placeholder', () => {
		const view = fieldView(key('PictureWidth'), { ...base, stored: true, value: 7 });
		expect([view.inputValue, view.placeholder]).toEqual(['7', undefined]);
	});

	it('reads a missing value as empty text', () => {
		const view = fieldView(key('PictureWidth'), base);
		expect([view.inputValue, view.placeholder, view.shown == null]).toEqual(['', '', true]);
	});

	it('takes limits from the schema and an explicit range over them', () => {
		const limited = { ...key('PictureWidth'), limits: [1, 9] } as unknown as SlimKey;
		const fromSchema = fieldView(limited, base);
		expect([fromSchema.min, fromSchema.max, fromSchema.step]).toEqual([1, 9, undefined]);
		const ranged = fieldView(limited, { ...base, range: { min: 2, max: 5, step: 0.5 } });
		expect([ranged.min, ranged.max, ranged.step]).toEqual([2, 5, 0.5]);
		const none = fieldView(key('PictureWidth'), base);
		expect([none.min, none.max]).toEqual([undefined, undefined]);
	});

	it('lists chip values as strings, and none for a non-list value', () => {
		expect(fieldView(key('AudioLanguageList'), { ...base, inherited: ['eng', 2] }).chipValues).toEqual(['eng', '2']);
		expect(fieldView(key('AudioLanguageList'), { ...base, inherited: null }).chipValues).toEqual([]);
	});
});

describe('groupsForTab', () => {
	const k = (name: string, group: string) => ({ name, group }) as unknown as SlimKey;

	it('groups keys by group in first-appearance order, keeping the key order', () => {
		const groups = groupsForTab([k('a', 'Size'), k('b', 'Cropping'), k('c', 'Size'), k('d', 'Cropping')]);
		expect(groups.map((g) => [g.group, g.keys.map((x) => x.name)])).toEqual([
			['Size', ['a', 'c']],
			['Cropping', ['b', 'd']]
		]);
	});

	it('is empty for no keys', () => {
		expect(groupsForTab([])).toEqual([]);
	});
});
