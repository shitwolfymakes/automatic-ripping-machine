import { describe, it, expect } from 'vitest';
import type { HandbrakeSchemaSlimView, HandbrakeSettings, SettingIssue, SlimFamily } from '$lib/types/api.gen';
import fixture from './fixtures/slim-schema.json';
import type { EncoderCard } from '../encoder-cards';
import { AUDIO_LIST_ID } from '../audio-tracks';
import {
	firstIssueTarget,
	issueTarget,
	placedIssues,
	presetBlockMessages,
	unplacedIssues,
	unplacedText,
	type PanelInput
} from '../issue-placement';

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

	it('places block fields and bit depth of open reachable cards only', () => {
		const list = [
			issue('VideoPreset', 'x264'),
			issue('VideoPreset', 'x265'),
			issue('VideoPreset', 'qsv_h264'),
			issue('bit_depth', 'x264'),
			issue('bit_depth', 'qsv_h264')
		];
		expect(unplaced(list, panel())).toEqual(['x265|VideoPreset', 'qsv_h264|VideoPreset', 'qsv_h264|bit_depth']);
		expect(unplaced(list, panel({}, ['qsv_h264']))).toEqual(['x265|VideoPreset']);
	});
});

describe('placedIssues', () => {
	it('keeps the issues a rendered input shows, in form order', () => {
		const list = [issue('PictureWidth'), issue('PictureTopCrop'), issue('preset_ref')];
		expect(placedIssues(list, panel()).map((i) => i.key)).toEqual(['preset_ref', 'PictureWidth']);
	});

	it('orders the preset block by its render order, then tabs by strip order', () => {
		const list = [
			issue('VideoPreset', 'x264'),
			issue('extra_args'),
			issue('PictureWidth'),
			issue('preset_ref'),
			issue('bit_depth', 'x264'),
			issue('name')
		];
		expect(placedIssues(list, panel()).map((i) => `${i.encoder ?? ''}|${i.key}`)).toEqual([
			'|name',
			'|preset_ref',
			'|extra_args',
			'|PictureWidth',
			'x264|bit_depth',
			'x264|VideoPreset'
		]);
	});

	it('has nothing to place without issues', () => {
		expect(placedIssues([], panel())).toEqual([]);
		expect(unplacedIssues([], panel())).toEqual([]);
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

describe('issueTarget', () => {
	it('targets a preset-block field by its tp- id, with no tab', () => {
		expect(issueTarget(issue('name'), schema)).toEqual({ id: 'tp-name', tab: null });
		expect(issueTarget(issue('preset_ref'), null)).toEqual({ id: 'tp-preset-ref', tab: null });
		expect(issueTarget(issue('extra_args'), schema)).toEqual({ id: 'tp-extra-args', tab: null });
	});

	it('targets an encoder card field on the Video tab, prefixed by the family', () => {
		expect(issueTarget(issue('VideoPreset', 'x264'), schema)).toEqual({ id: 'x264-tunable-VideoPreset', tab: 'video' });
	});

	it("targets an encoder card's bit depth select", () => {
		expect(issueTarget(issue('bit_depth', 'x265'), schema)).toEqual({ id: 'x265-bit-depth', tab: 'video' });
	});

	it('targets a track field by track index, on its key tab', () => {
		expect(issueTarget(issue('AudioList[1].AudioBitrate'), schema)).toEqual({
			id: 'audio-1-tunable-AudioBitrate',
			tab: 'audio'
		});
	});

	it('targets the whole audio track list on the Audio tab', () => {
		expect(issueTarget(issue('AudioList'), schema)).toEqual({ id: AUDIO_LIST_ID, tab: 'audio' });
	});

	it('targets a common field on its key tab', () => {
		expect(issueTarget(issue('PictureWidth'), schema)).toEqual({ id: 'tunable-PictureWidth', tab: 'dimensions' });
	});

	it('has no tab for a key the schema lacks, or with no schema', () => {
		expect(issueTarget(issue('NotAKey'), schema)).toEqual({ id: 'tunable-NotAKey', tab: null });
		expect(issueTarget(issue('PictureWidth'), null).tab).toBeNull();
		expect(issueTarget(issue('AudioList[0].Nope'), schema).tab).toBeNull();
		expect(issueTarget(issue('AudioList[0].AudioBitrate'), null).tab).toBeNull();
	});
});

describe('firstIssueTarget', () => {
	it('targets the first issue in form order a rendered input shows, skipping unplaced ones', () => {
		const list = [issue('PictureTopCrop'), issue('VideoPreset', 'x264'), issue('PictureWidth')];
		expect(firstIssueTarget(list, panel())).toEqual({ id: 'tunable-PictureWidth', tab: 'dimensions' });
	});

	it('targets a preset-block issue with no panel', () => {
		expect(firstIssueTarget([issue('PictureWidth'), issue('preset_ref')], null)).toEqual({
			id: 'tp-preset-ref',
			tab: null
		});
	});

	it('is null when no issue is placed', () => {
		expect(firstIssueTarget([issue('PictureTopCrop')], panel())).toBeNull();
		expect(firstIssueTarget([], panel())).toBeNull();
	});
});

describe('presetBlockMessages', () => {
	it('keys preset-block issues by input id, first issue per field, skipping settings and encoder issues', () => {
		const first = { ...issue('name'), message: 'Taken' };
		const second = { ...issue('name'), message: 'Too long' };
		const list = [first, second, issue('extra_args'), issue('PictureWidth'), issue('name', 'x264')];
		expect(presetBlockMessages(list)).toEqual({ 'tp-name': 'Taken', 'tp-extra-args': 'extra_args' });
	});
});
