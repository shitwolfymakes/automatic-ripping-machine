import { describe, it, expect } from 'vitest';
import {
	numberInputText,
	parsePrescanInput,
	parseRipSpeed,
	PRESCAN_FIELDS,
	prescanInputTexts
} from '../drives/settings';

describe('prescanInputTexts', () => {
	it('shows four blank inputs when there is no drive', () => {
		expect(prescanInputTexts(undefined)).toEqual({
			prescan_cache_mb: '',
			prescan_timeout: '',
			prescan_retries: '',
			disc_enum_timeout: ''
		});
	});

	it('shows each override as text', () => {
		expect(
			prescanInputTexts({
				prescan_cache_mb: 64,
				prescan_timeout: 600,
				prescan_retries: 3,
				disc_enum_timeout: 120
			})
		).toEqual({
			prescan_cache_mb: '64',
			prescan_timeout: '600',
			prescan_retries: '3',
			disc_enum_timeout: '120'
		});
	});

	it('shows null as blank and 0 as 0', () => {
		expect(prescanInputTexts({ prescan_cache_mb: null, prescan_retries: 0 })).toEqual({
			prescan_cache_mb: '',
			prescan_timeout: '',
			prescan_retries: '0',
			disc_enum_timeout: ''
		});
	});
});

describe('PRESCAN_FIELDS', () => {
	it('lists the four fields in display order', () => {
		expect(PRESCAN_FIELDS.map((f) => f.key)).toEqual([
			'prescan_cache_mb',
			'prescan_timeout',
			'prescan_retries',
			'disc_enum_timeout'
		]);
	});

	it('gives each field a min below its max', () => {
		for (const f of PRESCAN_FIELDS) expect(f.min).toBeLessThan(f.max);
	});
});

describe('parseRipSpeed', () => {
	it.each([[''], ['   '], [null], [undefined]])('reads %j as null (clear the speed)', (raw) => {
		expect(parseRipSpeed(raw)).toBeNull();
	});

	it('reads a number that is not a string', () => {
		expect(parseRipSpeed(8)).toBe(8);
	});

	it('accepts 1 and 99 and rejects 0 and 100', () => {
		expect(parseRipSpeed('1')).toBe(1);
		expect(parseRipSpeed('99')).toBe(99);
		expect(parseRipSpeed('0')).toBeUndefined();
		expect(parseRipSpeed('100')).toBeUndefined();
	});

	it('rejects text that is not a number', () => {
		expect(parseRipSpeed('abc')).toBeUndefined();
	});

	it('trims the input and keeps the leading digits like parseInt', () => {
		expect(parseRipSpeed(' 12 ')).toBe(12);
		expect(parseRipSpeed('12abc')).toBe(12);
	});
});

describe('parsePrescanInput', () => {
	const range = { min: 10, max: 500 };

	it('reads a blank input as null that is not the default', () => {
		expect(parsePrescanInput('', range, 128)).toEqual({ value: null, matchesDefault: false });
	});

	it('keeps an in-range number that is not the default', () => {
		expect(parsePrescanInput('64', range, 128)).toEqual({ value: 64, matchesDefault: false });
	});

	it('stores a value equal to the default as null', () => {
		expect(parsePrescanInput('128', range, 128)).toEqual({ value: null, matchesDefault: true });
	});

	it('keeps the number when there is no default', () => {
		expect(parsePrescanInput('64', range, undefined)).toEqual({
			value: 64,
			matchesDefault: false
		});
	});

	it('rejects a number below min, above max, or text', () => {
		expect(parsePrescanInput('9', range, 128)).toBeUndefined();
		expect(parsePrescanInput('501', range, 128)).toBeUndefined();
		expect(parsePrescanInput('abc', range, 128)).toBeUndefined();
	});
});

describe('numberInputText', () => {
	it('writes a number as text, 0 included', () => {
		expect(numberInputText(12)).toBe('12');
		expect(numberInputText(0)).toBe('0');
	});

	it('writes null and undefined as blank', () => {
		expect(numberInputText(null)).toBe('');
		expect(numberInputText(undefined)).toBe('');
	});
});
