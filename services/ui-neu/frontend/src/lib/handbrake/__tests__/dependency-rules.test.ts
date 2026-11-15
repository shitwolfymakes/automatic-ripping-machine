import { describe, expect, it } from 'vitest';
import { DEPENDENCY_RULES, fieldVisible, isApplicable, textMatches } from '../dependency-rules';

const cases: [string, Record<string, unknown>, boolean][] = [
	['PictureTopCrop', { PictureCropMode: 3 }, true],
	['PictureRightCrop', { PictureCropMode: 1 }, false],
	['PicturePadLeft', { PicturePadMode: 'custom' }, true],
	['PicturePadTop', { PicturePadMode: 'none' }, false],
	['PicturePadColor', { PicturePadMode: 'none' }, false],
	['PicturePadColor', { PicturePadMode: 'custom' }, true],
	['PicturePARWidth', { PicturePAR: 'custom' }, true],
	['PicturePARHeight', { PicturePAR: 'auto' }, false],
	['VideoAvgBitrate', { VideoQualityType: 1 }, true],
	['VideoMultiPass', { VideoQualityType: 2 }, false],
	['VideoTurboMultiPass', { VideoQualityType: 1 }, true],
	['VideoQualitySlider', { VideoQualityType: 2 }, true],
	['VideoQualitySlider', { VideoQualityType: 1 }, false],
	['PictureDenoisePreset', { PictureDenoiseFilter: 'nlmeans' }, true],
	['PictureDenoiseTune', { PictureDenoiseFilter: 'off' }, false],
	['PictureSharpenCustom', { PictureSharpenFilter: 'unsharp', PictureSharpenPreset: 'custom' }, true],
	['PictureSharpenCustom', { PictureSharpenFilter: 'unsharp', PictureSharpenPreset: 'medium' }, false],
	['PictureSharpenCustom', { PictureSharpenFilter: 'off', PictureSharpenPreset: 'custom' }, false],
	['PictureDeinterlaceTune', { PictureDeinterlaceFilter: 'decomb' }, true],
	['PictureDeblockTune', { PictureDeblockPreset: 'medium' }, true],
	['PictureDeblockTune', { PictureDeblockPreset: 'off' }, false],
	['PictureCombDetectCustom', { PictureCombDetectPreset: 'custom' }, true],
	['PictureColorspaceCustom', { PictureColorspacePreset: 'off' }, false],
	['PictureChromaSmoothCustom', { PictureChromaSmoothPreset: 'custom' }, true],
	['PictureDetelecineCustom', { PictureDetelecine: 'custom' }, true],
	['PictureDetelecineCustom', { PictureDetelecine: 'off' }, false],
	['AudioLanguageList', { AudioTrackSelectionBehavior: 'first' }, true],
	['AudioLanguageList', { AudioTrackSelectionBehavior: 'none' }, false],
	['SubtitleLanguageList', { SubtitleTrackSelectionBehavior: 'none' }, false],
	['SubtitleLanguageList', { SubtitleTrackSelectionBehavior: 'all' }, true],
	['AudioTrackQuality', { AudioTrackQualityEnable: true }, true],
	['AudioTrackQuality', { AudioTrackQualityEnable: false }, false],
	['AudioBitrate', { AudioTrackQualityEnable: true }, false],
	['AudioBitrate', {}, true],
	['x264Option', { x264UseAdvancedOptions: true }, true],
	['x264Option', { x264UseAdvancedOptions: false }, false],
	['SomeUngatedKey', {}, true]
];

describe('isApplicable', () => {
	it.each(cases)('%s with %j -> %s', (name, ctx, expected) => {
		expect(isApplicable(name, ctx)).toBe(expected);
	});

	it('exposes the rules as data', () => {
		expect(DEPENDENCY_RULES.length).toBeGreaterThan(0);
	});
});

describe('fieldVisible', () => {
	const open = { text: '', changedOnly: false };

	it('hides a gated-off field even when it holds a stored value', () => {
		expect(fieldVisible('PictureTopCrop', 'Top crop', open, true, { PictureCropMode: 1 })).toBe(false);
	});

	it('hides an unstored field under changed-only', () => {
		expect(
			fieldVisible('PictureTopCrop', 'Top crop', { text: '', changedOnly: true }, false, { PictureCropMode: 3 })
		).toBe(false);
	});

	it('shows a stored field under changed-only', () => {
		expect(
			fieldVisible('PictureTopCrop', 'Top crop', { text: '', changedOnly: true }, true, { PictureCropMode: 3 })
		).toBe(true);
	});

	it('matches the label case-insensitively', () => {
		expect(
			fieldVisible('PictureTopCrop', 'Top crop', { text: 'TOP C', changedOnly: false }, false, { PictureCropMode: 3 })
		).toBe(true);
	});

	it('hides a field that matches neither name nor label', () => {
		expect(
			fieldVisible('PictureTopCrop', 'Top crop', { text: 'zzz', changedOnly: false }, false, { PictureCropMode: 3 })
		).toBe(false);
	});

	it('shows an applicable field for empty text', () => {
		expect(fieldVisible('Anything', 'Anything', open, false, {})).toBe(true);
	});
});

describe('textMatches', () => {
	it('matches the label, case-insensitively, ignoring surrounding spaces', () => {
		expect(textMatches('AlignAVStart', 'Align audio and video start', ' ALIGN AUDIO ')).toBe(true);
	});
	it('matches the key name', () => {
		expect(textMatches('AlignAVStart', 'Align audio and video start', 'avstart')).toBe(true);
	});
	it('does not match something else', () => {
		expect(textMatches('AlignAVStart', 'Align audio and video start', 'zzz')).toBe(false);
	});
});
