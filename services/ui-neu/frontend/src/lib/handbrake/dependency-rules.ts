// Which settings apply given the other settings' effective values, and
// whether a field is shown under the current filter.

import type { FilterState } from './visibility';

export type Context = Record<string, unknown>;

export type DependencyRule = { keys: readonly string[]; applies: (ctx: Context) => boolean };

const whenEquals = (key: string, value: unknown, keys: readonly string[]): DependencyRule => ({
	keys,
	applies: (ctx) => ctx[key] === value
});

const whenNot = (key: string, value: unknown, keys: readonly string[]): DependencyRule => ({
	keys,
	applies: (ctx) => ctx[key] !== value
});

// Filters with a selector (Picture<F>Filter) that gate a preset, a tune and a custom string.
const SELECTOR_FILTERS = ['Deinterlace', 'Denoise', 'Sharpen'];

// Filters controlled by their preset alone.
const PRESET_ONLY_FILTERS = ['ChromaSmooth', 'Deblock', 'Colorspace', 'CombDetect'];

const selectorRules = (f: string): DependencyRule[] => [
	whenNot(`Picture${f}Filter`, 'off', [`Picture${f}Preset`, `Picture${f}Tune`]),
	{
		keys: [`Picture${f}Custom`],
		applies: (ctx) => ctx[`Picture${f}Filter`] !== 'off' && ctx[`Picture${f}Preset`] === 'custom'
	}
];

const presetOnlyRules = (f: string): DependencyRule[] => [
	whenNot(`Picture${f}Preset`, 'off', [`Picture${f}Tune`]),
	whenEquals(`Picture${f}Preset`, 'custom', [`Picture${f}Custom`])
];

export const DEPENDENCY_RULES: readonly DependencyRule[] = [
	whenEquals('PictureCropMode', 3, ['PictureTopCrop', 'PictureBottomCrop', 'PictureLeftCrop', 'PictureRightCrop']),
	whenEquals('PicturePadMode', 'custom', ['PicturePadTop', 'PicturePadBottom', 'PicturePadLeft', 'PicturePadRight']),
	whenNot('PicturePadMode', 'none', ['PicturePadColor']),
	whenEquals('PicturePAR', 'custom', ['PicturePARWidth', 'PicturePARHeight']),
	whenEquals('VideoQualityType', 1, ['VideoAvgBitrate', 'VideoMultiPass', 'VideoTurboMultiPass']),
	whenEquals('VideoQualityType', 2, ['VideoQualitySlider']),
	...SELECTOR_FILTERS.flatMap(selectorRules),
	...PRESET_ONLY_FILTERS.flatMap(presetOnlyRules),
	whenEquals('PictureDetelecine', 'custom', ['PictureDetelecineCustom']),
	whenNot('AudioTrackSelectionBehavior', 'none', ['AudioLanguageList']),
	whenNot('SubtitleTrackSelectionBehavior', 'none', ['SubtitleLanguageList']),
	whenEquals('AudioTrackQualityEnable', true, ['AudioTrackQuality']),
	whenNot('AudioTrackQualityEnable', true, ['AudioBitrate']),
	whenEquals('x264UseAdvancedOptions', true, ['x264Option'])
];

export function isApplicable(name: string, ctx: Context): boolean {
	return DEPENDENCY_RULES.every((rule) => !rule.keys.includes(name) || rule.applies(ctx));
}

// The filter box matches the key name or its label, ignoring case.
export function textMatches(name: string, label: string, text: string): boolean {
	const needle = text.trim().toLowerCase();
	return name.toLowerCase().includes(needle) || label.toLowerCase().includes(needle);
}

export function fieldVisible(name: string, label: string, f: FilterState, stored: boolean, ctx: Context): boolean {
	return isApplicable(name, ctx) && (!f.changedOnly || stored) && textMatches(name, label, f.text);
}
