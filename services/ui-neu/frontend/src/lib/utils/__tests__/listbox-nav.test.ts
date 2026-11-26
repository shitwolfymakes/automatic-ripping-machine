import { describe, it, expect } from 'vitest';
import { isListboxNavKey, nextRowIndex } from '../listbox-nav';

describe('isListboxNavKey', () => {
	it.each(['ArrowDown', 'ArrowUp', 'Home', 'End'])('is true for %s', (key) => {
		expect(isListboxNavKey(key)).toBe(true);
	});

	it.each(['Enter', ' ', 'Tab', 'a', 'toString'])('is false for %j', (key) => {
		expect(isListboxNavKey(key)).toBe(false);
	});
});

describe('nextRowIndex', () => {
	it('moves ArrowDown to the next row', () => {
		expect(nextRowIndex('ArrowDown', 1, 3)).toBe(2);
	});

	it('keeps focus on ArrowDown from the last row', () => {
		expect(nextRowIndex('ArrowDown', 2, 3)).toBeNull();
	});

	it('moves ArrowUp to the previous row', () => {
		expect(nextRowIndex('ArrowUp', 1, 3)).toBe(0);
	});

	it('keeps focus on ArrowUp from the first row', () => {
		expect(nextRowIndex('ArrowUp', 0, 3)).toBeNull();
	});

	it('moves Home to the first row and End to the last', () => {
		expect(nextRowIndex('Home', 2, 3)).toBe(0);
		expect(nextRowIndex('End', 0, 3)).toBe(2);
	});

	it('keeps focus on Home and End in an empty list', () => {
		expect(nextRowIndex('Home', 0, 0)).toBeNull();
		expect(nextRowIndex('End', 0, 0)).toBeNull();
	});

	it('keeps focus on ArrowDown in an empty list', () => {
		expect(nextRowIndex('ArrowDown', 0, 0)).toBeNull();
	});

	it('keeps focus on a key that is not a navigation key', () => {
		expect(nextRowIndex('Enter', 0, 3)).toBeNull();
	});
});
