import { describe, it, expect } from 'vitest';
import { pathBasename, pathTrail } from '../path';

describe('pathBasename', () => {
	it('returns an empty string for null, undefined and an empty path', () => {
		expect(pathBasename(null)).toBe('');
		expect(pathBasename(undefined)).toBe('');
		expect(pathBasename('')).toBe('');
	});

	it('returns a bare name unchanged', () => {
		expect(pathBasename('movie.mkv')).toBe('movie.mkv');
	});

	it('returns the last segment of a nested path', () => {
		expect(pathBasename('/data/out/movie.mkv')).toBe('movie.mkv');
	});

	it('drops one trailing slash', () => {
		expect(pathBasename('/data/out/movie/')).toBe('movie');
	});

	it('drops several trailing slashes', () => {
		expect(pathBasename('/data/out/movie///')).toBe('movie');
	});

	it('returns an empty string for the root path', () => {
		expect(pathBasename('/')).toBe('');
	});

	it.each([
		['a', 'a'],
		['a/b', 'b'],
		['/a/b/', 'b'],
		['a//', 'a'],
		['//', ''],
		['/', ''],
		['/a', 'a'],
		['a//b', 'b']
	])('returns the same basename for %j as before the rewrite', (input, expected) => {
		expect(pathBasename(input)).toBe(expected);
	});
});

describe('pathTrail', () => {
	it('returns an empty trail for an empty path', () => {
		expect(pathTrail('')).toEqual([]);
	});

	it('returns one entry for a single segment', () => {
		expect(pathTrail('a')).toEqual([{ label: 'a', path: 'a' }]);
	});

	it('pairs each of three segments with the path accumulated up to it', () => {
		expect(pathTrail('a/b/c')).toEqual([
			{ label: 'a', path: 'a' },
			{ label: 'b', path: 'a/b' },
			{ label: 'c', path: 'a/b/c' }
		]);
	});

	it.each([
		[
			'/a/b',
			[
				{ label: 'a', path: 'a' },
				{ label: 'b', path: 'a/b' }
			]
		],
		[
			'a/b/',
			[
				{ label: 'a', path: 'a' },
				{ label: 'b', path: 'a/b' }
			]
		],
		[
			'a//b',
			[
				{ label: 'a', path: 'a' },
				{ label: 'b', path: 'a/b' }
			]
		]
	])('drops the empty segments of %j', (input, expected) => {
		expect(pathTrail(input)).toEqual(expected);
	});
});
