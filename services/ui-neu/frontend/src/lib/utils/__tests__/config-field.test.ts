import { describe, it, expect } from 'vitest';
import { readOnlyValue } from '../../settings/config-field';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

const f = (over: Partial<ConfigFieldMeta>): ConfigFieldMeta => ({
	key: 'k',
	group: 'G',
	tier: 'operator',
	label: 'Label',
	help: 'Help',
	type: 'string',
	editable: false,
	enum_values: null,
	...over
});

describe('readOnlyValue', () => {
	const bool = f({ type: 'bool' });

	it('shows True for a true bool', () => {
		expect(readOnlyValue(bool, true)).toBe('True');
	});

	it('shows False for a false bool', () => {
		expect(readOnlyValue(bool, false)).toBe('False');
	});

	it('reads a truthy non-bool as True', () => {
		expect(readOnlyValue(bool, 'yes')).toBe('True');
	});

	it('reads a falsy non-bool as False', () => {
		expect(readOnlyValue(bool, '')).toBe('False');
		expect(readOnlyValue(bool, null)).toBe('False');
	});

	describe('ranked', () => {
		const ranked = f({ type: 'ranked', enum_labels: { a: 'Alpha', b: 'Beta' } });

		it('joins a list by its labels', () => {
			expect(readOnlyValue(ranked, ['b', 'a'])).toBe('Beta, Alpha');
		});

		it('shows a value with no label as itself', () => {
			expect(readOnlyValue(ranked, ['a', 'z'])).toBe('Alpha, z');
		});

		it('shows values as themselves when the field has no enum_labels', () => {
			expect(readOnlyValue(f({ type: 'ranked' }), ['a', 'b'])).toBe('a, b');
		});

		it('shows a dash for an empty list', () => {
			expect(readOnlyValue(ranked, [])).toBe('-');
		});

		it('shows a dash for a value that is not a list', () => {
			expect(readOnlyValue(ranked, 'a')).toBe('-');
			expect(readOnlyValue(ranked, null)).toBe('-');
		});
	});

	describe('any other type', () => {
		it('shows a string as it is', () => {
			expect(readOnlyValue(f({}), 'hello')).toBe('hello');
		});

		it('shows a number as text', () => {
			expect(readOnlyValue(f({ type: 'int' }), 42)).toBe('42');
		});

		it('shows a dash for null and undefined', () => {
			expect(readOnlyValue(f({}), null)).toBe('-');
			expect(readOnlyValue(f({}), undefined)).toBe('-');
		});
	});
});
