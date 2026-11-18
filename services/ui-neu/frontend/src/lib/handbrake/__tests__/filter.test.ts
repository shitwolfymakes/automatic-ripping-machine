import { describe, it, expect } from 'vitest';
import type { HandbrakeSchemaSlimView, HandbrakeSettings, SlimFamily } from '$lib/types/api.gen';
import fixture from './fixtures/slim-schema.json';
import { firstTabWithMatch, tabVisibleCounts, visibleTab, type VisibleInput } from '../filter';
import { toPayload } from '../settings-edit';
import type { EncoderCard } from '../encoder-cards';
import { TABS, type TabId } from '../fields';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const family = (name: string): SlimFamily => schema.families.find((f) => f.name === name)!;
const card = (name: string, state: EncoderCard['state'] = 'open') => ({
	card: { family: name, label: name, state, device: null },
	family: family(name)
});
const zero = (over: Partial<Record<TabId, number>> = {}) =>
	({ ...Object.fromEntries(TABS.map((t) => [t.id, 0])), ...over }) as Record<TabId, number>;

function input(over: Partial<VisibleInput> = {}): VisibleInput {
	return {
		schema,
		settings: {},
		base: null,
		filter: { text: '', changedOnly: false },
		cards: [card('x264'), card('nvenc_h264')],
		expanded: [],
		...over
	};
}
const text = (t: string, over: Partial<VisibleInput> = {}) =>
	input({ filter: { text: t, changedOnly: false }, ...over });
const names = (tab: TabId, i: VisibleInput) => visibleTab(i, tab).rows.map((r) => r.key.name);
const twoTracks: HandbrakeSettings = { common: { AudioList: [{ AudioEncoder: 'av_aac' }, { AudioEncoder: 'ac3' }] } };

describe('visibleTab', () => {
	it('lists the applicable common keys of the tab, leaving out ARM-owned and encoder-specific ones', () => {
		expect(names('summary', input())).toEqual([
			'AlignAVStart',
			'InlineParameterSets',
			'MetadataPassthru',
			'Mp4iPodCompatible',
			'Optimize'
		]);
		expect(names('video', input())).not.toContain('VideoPreset');
		expect(names('video', input())).not.toContain('VideoAvgBitrate');
	});

	it("shows the audio track list as its own row with each track's visible fields", () => {
		const v = visibleTab(text('gain', { settings: twoTracks }), 'audio');
		expect(v.rows).toEqual([{ key: schema.keys.find((k) => k.name === 'AudioList'), row: 'audio-list' }]);
		expect(v.tracks.map((t) => t.map((k) => k.name))).toEqual([['AudioTrackGainSlider'], ['AudioTrackGainSlider']]);
	});

	it('takes the tracks from the base when the preset stores none', () => {
		const v = visibleTab(text('gain', { base: { AudioList: [{}, {}, {}] } }), 'audio');
		expect(v.tracks).toHaveLength(3);
	});

	it('drops the audio track list when no track field matches', () => {
		const v = visibleTab(text('fallback'), 'audio');
		expect(v.rows.map((r) => r.row)).toEqual(['field']);
		expect(v.tracks).toEqual([]);
	});

	it('keeps an empty audio track list unfiltered, so a track can be added', () => {
		const v = visibleTab(input({ settings: { common: { AudioList: [] } } }), 'audio');
		expect(v.rows.map((r) => r.row)).toContain('audio-list');
		expect(v.tracks).toEqual([]);
	});

	it('drops a card whose only matching field is gated off', () => {
		expect(visibleTab(text('multi-pass'), 'video').cards).toEqual([]);
		const settings = { common: { VideoQualityType: 1 } };
		expect(visibleTab(text('multi-pass', { settings }), 'video').cards.map((c) => c.fields)).toEqual([
			['VideoMultiPass']
		]);
	});

	it('holds the cards with a visible field only on the video tab', () => {
		expect(visibleTab(text('preset'), 'video').cards.map((c) => c.fields)).toEqual([['VideoPreset'], ['VideoPreset']]);
		expect(visibleTab(text('preset'), 'summary').cards).toEqual([]);
		expect(visibleTab(text('denoise'), 'video').cards).toEqual([]);
	});
});

describe('tabVisibleCounts', () => {
	it('without a filter counts every rendered input, even with nothing stored', () => {
		const counts = tabVisibleCounts(input({ settings: twoTracks }));
		expect(counts.summary).toBe(5);
		expect(counts.chapters).toBe(1);
		expect(counts.dimensions).toBe(names('dimensions', input()).length);
		const audioCommon = names('audio', input()).filter((n) => n !== 'AudioList').length;
		const perTrack = visibleTab(input({ settings: twoTracks }), 'audio').tracks[0].length;
		expect(counts.audio).toBe(audioCommon + 2 * perTrack);
		const cards = visibleTab(input(), 'video').cards.reduce((n, c) => n + c.fields.length, 0);
		expect(counts.video).toBe(names('video', input()).length + cards);
		for (const t of TABS) expect(counts[t.id]).toBeGreaterThan(0);
	});

	it('"track" counts the matching common keys plus the matching fields of each track, and nothing on Video', () => {
		const counts = tabVisibleCounts(text('track', { settings: twoTracks }));
		expect(counts.video).toBe(0);
		expect(names('audio', text('track'))).toEqual([
			'AudioAutomaticNamingBehavior',
			'AudioList',
			'AudioTrackNamePassthru',
			'AudioTrackSelectionBehavior'
		]);
		expect(counts.audio).toBe(3 + 2 * 3);
	});

	it('"gain" counts one field per track', () => {
		expect(tabVisibleCounts(text('gain', { settings: twoTracks })).audio).toBe(2);
	});

	it('"preset" counts the preset of each reachable card only', () => {
		const settings = { encoders: { x265: { VideoPreset: 'slow' } } };
		expect(tabVisibleCounts(text('preset', { settings })).video).toBe(2);
		expect(tabVisibleCounts(text('preset', { settings, cards: [card('x264')] })).video).toBe(1);
	});

	it('does not count the fields of a collapsed card until it is expanded or stores a value', () => {
		const cards = [card('x264'), card('qsv_h264', 'collapsed')];
		const v = visibleTab(text('preset', { cards }), 'video');
		expect(v.cards.map((c) => c.open)).toEqual([true, false]);
		expect(tabVisibleCounts(text('preset', { cards })).video).toBe(1);
		expect(tabVisibleCounts(text('preset', { cards, expanded: ['qsv_h264'] })).video).toBe(2);
		const settings = { encoders: { qsv_h264: { VideoPreset: 'quality' } } };
		expect(tabVisibleCounts(text('preset', { cards, settings })).video).toBe(2);
	});

	it('does not count a gated field that holds a value, which still saves', () => {
		const settings = { common: { VideoQualityType: 2, VideoAvgBitrate: 5000 } };
		expect(tabVisibleCounts(text('average bitrate', { settings })).video).toBe(0);
		expect(names('video', text('average bitrate', { settings }))).toEqual([]);
		expect(toPayload(settings)?.common?.VideoAvgBitrate).toBe(5000);
	});

	it('under Changed only counts stored inputs only', () => {
		const settings = { common: { PictureWidth: 1280, AudioList: [{ AudioMixdown: 'stereo' }] } };
		const counts = tabVisibleCounts(input({ settings, filter: { text: '', changedOnly: true } }));
		expect(counts).toEqual(zero({ dimensions: 1, audio: 1 }));
	});

	it('feeds firstTabWithMatch a tab that has something to show', () => {
		const counts = tabVisibleCounts(text('gain', { settings: twoTracks }));
		expect(firstTabWithMatch(counts, 'summary')).toBe('audio');
	});
});

describe('firstTabWithMatch', () => {
	it('stays on the current tab when it matches', () => {
		expect(firstTabWithMatch(zero({ video: 2, audio: 1 }), 'audio')).toBe('audio');
	});
	it('moves to the first tab with a match', () => {
		expect(firstTabWithMatch(zero({ video: 2, audio: 1 }), 'summary')).toBe('video');
	});
	it('stays put when nothing matches', () => {
		expect(firstTabWithMatch(zero(), 'filters')).toBe('filters');
	});
});
