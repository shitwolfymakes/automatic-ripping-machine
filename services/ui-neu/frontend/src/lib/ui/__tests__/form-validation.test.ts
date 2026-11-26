import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	NAME_REQUIRED,
	errorId,
	firstInvalid,
	focusField,
	focusFirstInvalid,
	invalidAttrs,
	nameErrors
} from '$lib/ui/form-validation';

afterEach(() => {
	document.body.innerHTML = '';
	vi.restoreAllMocks();
});

function input(id: string): HTMLInputElement {
	const el = document.createElement('input');
	el.id = id;
	document.body.append(el);
	return el;
}

describe('firstInvalid', () => {
	it('returns the first invalid id in form order, not error order', () => {
		expect(firstInvalid({ c: 'x', b: 'y' }, ['a', 'b', 'c'])).toBe('b');
	});

	it('returns null when no field in the order has an error', () => {
		expect(firstInvalid({}, ['a', 'b'])).toBeNull();
		expect(firstInvalid({ z: 'x' }, ['a'])).toBeNull();
	});
});

describe('nameErrors', () => {
	it('flags a blank or whitespace name under the given id', () => {
		expect(nameErrors('n', '')).toEqual({ n: NAME_REQUIRED });
		expect(nameErrors('n', '   ')).toEqual({ n: 'Name is required' });
	});

	it('passes a non-blank name', () => {
		expect(nameErrors('n', 'Movies')).toEqual({});
	});
});

describe('errorId and invalidAttrs', () => {
	it('names the message element after the field', () => {
		expect(errorId('tp-name')).toBe('tp-name-error');
	});

	it('marks a field with a message and points it at the message', () => {
		expect(invalidAttrs('tp-name', 'Name is required')).toEqual({
			'aria-invalid': 'true',
			'aria-describedby': 'tp-name-error'
		});
	});

	it('adds nothing to a valid field', () => {
		expect(invalidAttrs('tp-name', undefined)).toEqual({});
		expect(invalidAttrs('tp-name', '')).toEqual({});
	});
});

describe('focusField', () => {
	it('focuses the element and scrolls it to the centre', () => {
		const el = input('f');
		const scroll = vi.fn();
		el.scrollIntoView = scroll;
		focusField('f');
		expect(document.activeElement).toBe(el);
		expect(scroll).toHaveBeenCalledWith({ block: 'center' });
	});

	it('still focuses where scrollIntoView is missing', () => {
		const el = input('f');
		Object.defineProperty(el, 'scrollIntoView', { value: undefined });
		focusField('f');
		expect(document.activeElement).toBe(el);
	});

	it('does nothing for an id with no element', () => {
		expect(() => focusField('missing')).not.toThrow();
	});
});

describe('focusFirstInvalid', () => {
	it('focuses the first invalid field and reports it found one', async () => {
		input('a');
		const b = input('b');
		expect(await focusFirstInvalid({ b: 'bad' }, ['a', 'b'])).toBe(true);
		expect(document.activeElement).toBe(b);
	});

	it('reports false and leaves focus alone when nothing is invalid', async () => {
		input('a');
		expect(await focusFirstInvalid({}, ['a'])).toBe(false);
		expect(document.activeElement).toBe(document.body);
	});
});
