import { describe, it, expect } from 'vitest';
import type { HandbrakeSchemaSlimView, SlimFamily, SlimKey } from '$lib/types/api.gen';
import fixture from './fixtures/slim-schema.json';
import { panelContext } from '../base-values';
import { audioListShown, cardFamilies, commonKeys, keyShown, panelCards } from '../visibility';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const family = (name: string): SlimFamily => schema.families.find((f) => f.name === name)!;
const key = (name: string): SlimKey => schema.keys.find((k) => k.name === name)!;

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

describe('panelCards', () => {
	it('pairs the reachable encoder cards with their families', () => {
		expect(panelCards(schema, 'cpu_h264', null, [], null).map((c) => c.family.name)).toEqual(['x264']);
		expect(panelCards(schema, 'preset', 'Fast 1080p30', [], { VideoEncoder: 'x265' })[0].card.family).toBe('x265');
	});
});
