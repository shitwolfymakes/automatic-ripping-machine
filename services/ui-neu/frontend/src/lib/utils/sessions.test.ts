import { describe, it, expect } from 'vitest';
import {
	countByMediaType,
	defaultSessionChoices,
	manualRipSessionChoices,
	mediaTypesCompatible,
	sessionsForDisc
} from '../sessions/sessions';

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

describe('sessionsForDisc', () => {
	const movie = { id: 'movie', media_type: 'movie' };
	const tv = { id: 'tv', media_type: 'tv' };
	const music = { id: 'music', media_type: 'music' };
	const data = { id: 'data', media_type: 'data' };
	const mixed = [movie, tv, music, data];

	it.each([
		['bluray', [movie, tv]],
		['dvd', [movie, tv]],
		['cd', [tv, music]],
		['data', [tv, data]]
	] as const)('a %s disc takes its media type plus tv', (discType, expected) => {
		expect(sessionsForDisc(mixed, discType)).toEqual(expected);
	});

	it('offers every session for an unknown disc', () => {
		expect(sessionsForDisc(mixed, 'unknown')).toEqual(mixed);
	});

	it.each(['bluray', 'dvd', 'cd', 'data', 'unknown'] as const)('keeps a tv session for a %s disc', (discType) => {
		expect(sessionsForDisc([tv], discType)).toEqual([tv]);
	});

	it('keeps the input order', () => {
		const first = { id: 'a', media_type: 'movie' };
		const second = { id: 'b', media_type: 'tv' };
		const third = { id: 'c', media_type: 'movie' };
		expect(sessionsForDisc([third, second, first], 'dvd')).toEqual([third, second, first]);
	});
});

describe('countByMediaType', () => {
	it('counts zero in all and of every media type when there are no sessions', () => {
		expect(countByMediaType([])).toEqual({ all: 0, movie: 0, tv: 0, music: 0, data: 0, iso: 0 });
	});

	it('counts each media type, with two sessions of one type', () => {
		const sessions = [
			{ media_type: 'movie' },
			{ media_type: 'tv' },
			{ media_type: 'movie' },
			{ media_type: 'music' },
			{ media_type: 'iso' }
		];
		expect(countByMediaType(sessions)).toEqual({ all: 5, movie: 2, tv: 1, music: 1, data: 0, iso: 1 });
	});

	it('counts a session of an unlisted media type in all only', () => {
		expect(countByMediaType([{ media_type: 'game' }, { media_type: 'data' }])).toEqual({
			all: 2,
			movie: 0,
			tv: 0,
			music: 0,
			data: 1,
			iso: 0
		});
	});
});
