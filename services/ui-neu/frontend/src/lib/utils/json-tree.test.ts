import { describe, it, expect } from 'vitest';
import { classifyJsonValue } from './json-tree';

describe('classifyJsonValue', () => {
	it('classifies a non-empty object', () => {
		const c = classifyJsonValue({ a: 1, b: 'x' });
		expect(c.kind).toBe('object');
		expect(c.isContainer).toBe(true);
		expect(c.preview).toBe('{…}');
		expect(c.entries).toEqual([
			{ key: 'a', value: 1 },
			{ key: 'b', value: 'x' }
		]);
	});

	it('classifies an empty object as a non-container', () => {
		const c = classifyJsonValue({});
		expect(c.kind).toBe('object');
		expect(c.isContainer).toBe(false);
		expect(c.preview).toBe('{}');
		expect(c.entries).toEqual([]);
	});

	it('classifies a non-empty array with index keys', () => {
		const c = classifyJsonValue(['x', 'y']);
		expect(c.kind).toBe('array');
		expect(c.isContainer).toBe(true);
		expect(c.preview).toBe('[2]');
		expect(c.entries).toEqual([
			{ key: '0', value: 'x' },
			{ key: '1', value: 'y' }
		]);
	});

	it('classifies an empty array as a non-container', () => {
		const c = classifyJsonValue([]);
		expect(c.kind).toBe('array');
		expect(c.isContainer).toBe(false);
		expect(c.preview).toBe('[]');
		expect(c.entries).toEqual([]);
	});

	it('classifies a string', () => {
		const c = classifyJsonValue('hello');
		expect(c).toEqual({ kind: 'string', isContainer: false, preview: 'hello', entries: [] });
	});

	it('classifies a number', () => {
		const c = classifyJsonValue(42);
		expect(c).toEqual({ kind: 'number', isContainer: false, preview: '42', entries: [] });
	});

	it('classifies a boolean', () => {
		expect(classifyJsonValue(true).preview).toBe('true');
		expect(classifyJsonValue(false).preview).toBe('false');
		expect(classifyJsonValue(true).kind).toBe('boolean');
	});

	it('classifies null', () => {
		expect(classifyJsonValue(null)).toEqual({ kind: 'null', isContainer: false, preview: 'null', entries: [] });
	});

	it('classifies undefined defensively as null', () => {
		expect(classifyJsonValue(undefined)).toEqual({ kind: 'null', isContainer: false, preview: 'null', entries: [] });
	});
});
