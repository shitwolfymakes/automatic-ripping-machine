import { describe, it, expect } from 'vitest';
import { isTextField } from '$lib/utils/text-field';

describe('isTextField', () => {
	it('is true for an input', () => {
		expect(isTextField(document.createElement('input'))).toBe(true);
	});

	it('is true for a textarea', () => {
		expect(isTextField(document.createElement('textarea'))).toBe(true);
	});

	it('is true for a contentEditable element', () => {
		const el = document.createElement('div');
		// jsdom leaves isContentEditable undefined, so report it as a browser does
		Object.defineProperty(el, 'isContentEditable', { value: true });
		expect(isTextField(el)).toBe(true);
	});

	it('is false for a button', () => {
		// jsdom's undefined isContentEditable makes the result undefined, not false
		expect(isTextField(document.createElement('button'))).toBeFalsy();
	});

	it('is false for a plain div', () => {
		expect(isTextField(document.createElement('div'))).toBeFalsy();
	});

	it('is false for null', () => {
		expect(isTextField(null)).toBe(false);
	});
});
