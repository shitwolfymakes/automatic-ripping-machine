import { describe, it, expect } from 'vitest';
import type { SlimKey } from '$lib/types/api.gen';
import { changedCount, changedLabel } from '../group-summary';

const keys = [{ name: 'A' }, { name: 'B' }, { name: 'C' }] as SlimKey[];

describe('changedCount', () => {
	it('counts the keys the predicate reports stored', () => {
		expect(changedCount(keys, (n) => n !== 'B')).toBe(2);
		expect(changedCount(keys, () => false)).toBe(0);
		expect(changedCount([], () => true)).toBe(0);
	});
});

describe('changedLabel', () => {
	it('is null for none, else the count', () => {
		expect(changedLabel(0)).toBeNull();
		expect(changedLabel(1)).toBe('1 changed');
		expect(changedLabel(3)).toBe('3 changed');
	});
});
