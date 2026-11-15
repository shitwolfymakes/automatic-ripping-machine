import { describe, it, expect } from 'vitest';
import type { HandbrakeSchemaSlimView, HandbrakeSettings, SettingIssue, SlimFamily } from '$lib/types/api.gen';
import fixture from './fixtures/slim-schema.json';
import type { EncoderCard } from '../encoderCards';
import { unplacedIssues, unplacedText, type PanelInput } from '../issuePlacement';

const schema = fixture as unknown as HandbrakeSchemaSlimView;
const family = (name: string): SlimFamily => schema.families.find((f) => f.name === name)!;
const card = (name: string, state: EncoderCard['state'] = 'open') => ({
	card: { family: name, label: name, state, device: null },
	family: family(name)
});
const issue = (key: string, encoder: string | null = null): SettingIssue => ({
	key,
	encoder,
	code: 'out_of_range',
	message: key
});

function panel(settings: HandbrakeSettings = {}, expanded: string[] = []): PanelInput {
	return { schema, settings, base: null, cards: [card('x264'), card('qsv_h264', 'collapsed')], expanded };
}
const unplaced = (issues: SettingIssue[], input: PanelInput | null) =>
	unplacedIssues(issues, input).map((i) => `${i.encoder ?? ''}|${i.key}`);

describe('unplacedIssues', () => {
	it('places preset-block fields only; without a panel every settings issue is unplaced', () => {
		const list = [issue('preset_ref'), issue('name', 'x264'), issue('PictureWidth')];
		expect(unplaced(list, null)).toEqual(['x264|name', '|PictureWidth']);
	});

	it('leaves an issue on a field another setting hides unplaced', () => {
		expect(unplaced([issue('PictureTopCrop')], panel())).toEqual(['|PictureTopCrop']);
		expect(unplaced([issue('PictureTopCrop')], panel({ common: { PictureCropMode: 3 } }))).toEqual([]);
	});

	it('places rendered common fields and the audio track list, not unknown keys or the whole object', () => {
		const list = [issue('PictureWidth'), issue('AudioList'), issue('handbrake_settings'), issue('NotAKey')];
		expect(unplaced(list, panel())).toEqual(['|handbrake_settings', '|NotAKey']);
	});

	it('places a track field only where that track renders it', () => {
		const list = [
			issue('AudioList[0].AudioBitrate'),
			issue('AudioList[0].AudioTrackQuality'),
			issue('AudioList[5].AudioBitrate'),
			issue('AudioMixdown')
		];
		expect(unplaced(list, panel())).toEqual([
			'|AudioList[0].AudioTrackQuality',
			'|AudioList[5].AudioBitrate',
			'|AudioMixdown'
		]);
	});

	it('places block fields of open reachable cards only, and never bit depth', () => {
		const list = [
			issue('VideoPreset', 'x264'),
			issue('VideoPreset', 'x265'),
			issue('VideoPreset', 'qsv_h264'),
			issue('bit_depth', 'x264')
		];
		expect(unplaced(list, panel())).toEqual(['x265|VideoPreset', 'qsv_h264|VideoPreset', 'x264|bit_depth']);
		expect(unplaced(list, panel({}, ['qsv_h264']))).toEqual(['x265|VideoPreset', 'x264|bit_depth']);
	});
});

describe('unplacedText', () => {
	const text = (key: string, encoder: string | null = null, s: HandbrakeSchemaSlimView | null = schema) =>
		unplacedText({ ...issue(key, encoder), message: 'Bad' }, s);

	it('names the setting by its label', () => {
		expect(text('PictureTopCrop')).toBe('Top crop: Bad');
		expect(text('VideoPreset', 'x265')).toBe('Encoder preset (x265): Bad');
		expect(text('bit_depth', 'x264')).toBe('Bit depth (x264): Bad');
		expect(text('AudioList[1].AudioBitrate')).toBe('Audio track 2 Bitrate (kbit/s): Bad');
	});

	it('falls back to the message alone', () => {
		expect(text('handbrake_settings')).toBe('Bad');
		expect(text('AudioList[0].Nope')).toBe('Bad');
		expect(text('PictureTopCrop', null, null)).toBe('Bad');
	});
});
