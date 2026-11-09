import { describe, it, expect } from 'vitest';
import { defaultSessionChoices, manualRipSessionChoices, mediaTypesCompatible } from './sessions';

const presets = [
	{ id: 'p-none', tool: 'none' },
	{ id: 'p-hb', tool: 'handbrake' }
];
const bare = { id: 's-bare', transcode_preset_id: null };
const none = { id: 's-none', transcode_preset_id: 'p-none' };
const encode = { id: 's-enc', transcode_preset_id: 'p-hb' };
const dangling = { id: 's-dangling', transcode_preset_id: 'p-missing' };
const all = [bare, none, encode, dangling];

describe('manualRipSessionChoices', () => {
	it('returns the same array with the transcoder on', () => {
		expect(manualRipSessionChoices(all, presets, true)).toBe(all);
	});

	it('keeps a session with no preset and one whose preset tool is none', () => {
		expect(manualRipSessionChoices(all, presets, false)).toEqual([bare, none]);
	});

	it('drops an encode session and one whose preset id is not in the list', () => {
		const result = manualRipSessionChoices([encode, dangling], presets, false);
		expect(result).toEqual([]);
	});
});

describe('defaultSessionChoices', () => {
	it('returns the same array with the transcoder on', () => {
		expect(defaultSessionChoices(all, presets, true, encode.id)).toBe(all);
	});

	it('appends an encode default at the end with the transcoder off', () => {
		expect(defaultSessionChoices(all, presets, false, encode.id)).toEqual([bare, none, encode]);
	});

	it('does not repeat a passthrough default', () => {
		expect(defaultSessionChoices(all, presets, false, none.id)).toEqual([bare, none]);
	});

	it.each([['s-gone'], [null], [undefined]])('gives the passthrough list alone for default id %s', (id) => {
		expect(defaultSessionChoices(all, presets, false, id)).toEqual([bare, none]);
	});
});

describe('mediaTypesCompatible (mirrors auto_session._media_types_compatible)', () => {
	it.each([
		['movie', 'movie', true],
		['movie', 'tv', true],
		['tv', 'movie', true],
		['movie', 'iso', true],
		['data', 'iso', true],
		['tv', 'data', true],
		['data', 'data', true],
		['music', 'music', true],
		['music', 'movie', false],
		['movie', 'music', false],
		['music', 'iso', false],
		['data', 'movie', false]
	])('job %s, session %s -> %s', (job, session, expected) => {
		expect(mediaTypesCompatible(job, session)).toBe(expected);
	});
});
