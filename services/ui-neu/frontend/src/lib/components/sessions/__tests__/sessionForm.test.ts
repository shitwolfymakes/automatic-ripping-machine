import { describe, it, expect } from 'vitest';
import { parseOverrides } from '../sessionForm';

describe('parseOverrides', () => {
	it('gives null for an empty field', () => {
		expect(parseOverrides('')).toBeNull();
	});

	it('gives null for a field of only spaces', () => {
		expect(parseOverrides('  \n\t ')).toBeNull();
	});

	it('gives the parsed object for JSON with spaces around it', () => {
		expect(parseOverrides('  {"a": 1}  ')).toEqual({ a: 1 });
	});

	it('throws a SyntaxError for text that is not JSON', () => {
		expect(() => parseOverrides('{nope')).toThrow(SyntaxError);
	});
});
