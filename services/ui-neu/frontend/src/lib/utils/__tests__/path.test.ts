import { describe, it, expect } from 'vitest';
import { pathBasename } from '../path';

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
});
