import { describe, expect, it } from 'vitest';
import { parseDuration, parseIndexList } from '../track-filters';

describe('parseIndexList', () => {
	it('splits on commas', () => {
		expect(parseIndexList('1,2,3')).toEqual([1, 2, 3]);
	});

	it('splits on spaces', () => {
		expect(parseIndexList('1 2 3')).toEqual([1, 2, 3]);
	});

	it('splits on commas and spaces mixed', () => {
		expect(parseIndexList('1, 2 ,3  4')).toEqual([1, 2, 3, 4]);
	});

	it('drops zero, negatives, decimals and words', () => {
		expect(parseIndexList('0, -1, 2.5, abc, 7')).toEqual([7]);
	});

	it('gives an empty list for an empty string', () => {
		expect(parseIndexList('')).toEqual([]);
	});

	it('gives an empty list for only separators', () => {
		expect(parseIndexList(' , ,, ')).toEqual([]);
	});

	it('keeps order and duplicates as typed', () => {
		expect(parseIndexList('5, 1, 5, 3')).toEqual([5, 1, 5, 3]);
	});
});

describe('parseDuration', () => {
	it('parses a number of seconds', () => {
		expect(parseDuration('90')).toBe(90);
	});

	it('keeps a zero', () => {
		expect(parseDuration('0')).toBe(0);
	});

	it('gives null for a blank input', () => {
		expect(parseDuration('')).toBeNull();
	});

	it('gives NaN for non-numeric text', () => {
		expect(parseDuration('abc')).toBeNaN();
	});
});
