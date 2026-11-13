import { describe, it, expect, vi } from 'vitest';
import {
	humanizeContainer,
	humanizeIdentificationMode,
	humanizeMediaType,
	humanizeOutputMode,
	humanizeTool,
	humanizeTrackSelection,
	ripPresetSummary,
	transcodePresetSummary
} from '../sessions/preset-labels';

describe('humanizeOutputMode', () => {
	it.each([
		['tracks', 'Tracks'],
		['iso', 'ISO image'],
		['data_copy', 'File copy'],
		['folder', 'Disc backup (folder)']
	])('maps %s -> %s', (mode, label) => {
		expect(humanizeOutputMode(mode)).toBe(label);
	});

	it('passes an unknown mode through and shows - for none', () => {
		expect(humanizeOutputMode('weird')).toBe('weird');
		expect(humanizeOutputMode(null)).toBe('-');
	});
});

describe('humanizeMediaType', () => {
	it.each([
		['movie', 'Movie'],
		['tv', 'TV'],
		['music', 'Music'],
		['data', 'Data'],
		['iso', 'ISO']
	])('maps %s -> %s', (type, label) => {
		expect(humanizeMediaType(type)).toBe(label);
	});

	it('passes an unknown type through and shows - for none', () => {
		expect(humanizeMediaType('weird')).toBe('weird');
		expect(humanizeMediaType(null)).toBe('-');
	});
});

describe('humanizeTrackSelection', () => {
	it.each([
		['main_feature', 'Main feature'],
		['all_tracks', 'All tracks'],
		['archive', 'Archive'],
		['custom', 'Custom']
	])('maps %s -> %s', (selection, label) => {
		expect(humanizeTrackSelection(selection)).toBe(label);
	});

	it('passes an unknown selection through and shows - for none', () => {
		expect(humanizeTrackSelection('weird')).toBe('weird');
		expect(humanizeTrackSelection(null)).toBe('-');
	});
});

describe('humanizeIdentificationMode', () => {
	it.each([
		['required', 'ID required'],
		['skip', 'ID skip'],
		['deferred_placeholder', 'ID deferred']
	])('maps %s -> %s', (mode, label) => {
		expect(humanizeIdentificationMode(mode)).toBe(label);
	});

	it('passes an unknown mode through and shows - for none', () => {
		expect(humanizeIdentificationMode('weird')).toBe('weird');
		expect(humanizeIdentificationMode(null)).toBe('-');
	});
});

describe('humanizeTool', () => {
	it.each([
		['handbrake', 'HandBrake'],
		['abcde', 'abcde'],
		['none', 'None']
	])('maps %s -> %s', (tool, label) => {
		expect(humanizeTool(tool)).toBe(label);
	});

	it('passes an unknown tool through and shows - for none', () => {
		expect(humanizeTool('weird')).toBe('weird');
		expect(humanizeTool(null)).toBe('-');
	});
});

describe('humanizeContainer', () => {
	it.each([
		['mkv', 'MKV'],
		['mp4', 'MP4'],
		['webm', 'WebM'],
		['flac', 'FLAC'],
		['mp3', 'MP3'],
		['ogg', 'OGG'],
		['iso', 'ISO'],
		['none', 'None']
	])('maps %s -> %s', (container, label) => {
		expect(humanizeContainer(container)).toBe(label);
	});

	it('passes an unknown container through and shows - for none', () => {
		expect(humanizeContainer('weird')).toBe('weird');
		expect(humanizeContainer(null)).toBe('-');
	});
});

describe('labelFrom fallbacks', () => {
	it('shows - for undefined', () => {
		expect(humanizeOutputMode(undefined)).toBe('-');
		expect(humanizeContainer(undefined)).toBe('-');
	});

	it('gives an empty value back as it is', () => {
		expect(humanizeMediaType('')).toBe('');
		expect(humanizeTool('')).toBe('');
	});

	it('gives a value named like an Object prototype member back as itself', () => {
		expect(humanizeTrackSelection('constructor')).toBe('constructor');
		expect(humanizeIdentificationMode('toString')).toBe('toString');
	});
});

describe('ripPresetSummary', () => {
	it("joins a preset's three labels in order", () => {
		expect(
			ripPresetSummary({
				track_selection: 'main_feature',
				identification_mode: 'required',
				output_mode: 'tracks'
			})
		).toBe('Main feature | ID required | Tracks');
	});
});

describe('transcodePresetSummary', () => {
	const preset = { tool: 'handbrake', container: 'mkv', encoder: 'any_h265' } as const;

	it('joins the tool, container and encoder name', () => {
		const encoderName = vi.fn(() => 'Any GPU H.265');
		expect(transcodePresetSummary(preset, encoderName)).toBe('HandBrake | MKV | Any GPU H.265');
		expect(encoderName).toHaveBeenCalledWith('any_h265');
	});

	it('leaves out an encoder name that is empty', () => {
		expect(transcodePresetSummary(preset, () => '')).toBe('HandBrake | MKV');
	});
});
