import { describe, it, expect } from 'vitest';
import { spliceToken, withInput, withText } from '../../../notifications/event-templates';

describe('withInput', () => {
	it('starts a new override set when there are none (undefined)', () => {
		expect(withInput(undefined, 'a', '1')).toEqual({ a: '1' });
	});

	it('starts a new override set when there are none (null)', () => {
		expect(withInput(null, 'a', '1')).toEqual({ a: '1' });
	});

	it('adds an override beside the existing ones', () => {
		expect(withInput({ a: '1' }, 'b', '2')).toEqual({ a: '1', b: '2' });
	});

	it('replaces an existing override', () => {
		expect(withInput({ a: '1' }, 'a', '2')).toEqual({ a: '2' });
	});

	it('removes one of two overrides when its value is blank', () => {
		expect(withInput({ a: '1', b: '2' }, 'a', '')).toEqual({ b: '2' });
	});

	it('gives null when the last override is cleared', () => {
		expect(withInput({ a: '1' }, 'a', '')).toBeNull();
	});

	it('leaves the overrides alone when a blank value clears a missing key', () => {
		expect(withInput({ a: '1' }, 'z', '')).toEqual({ a: '1' });
	});

	it('does not change the overrides it was given', () => {
		const inputs = { a: '1' };
		withInput(inputs, 'b', '2');
		expect(inputs).toEqual({ a: '1' });
	});
});

describe('spliceToken', () => {
	it('inserts the token at a caret', () => {
		expect(spliceToken('abcd', 2, 2, '{x}')).toEqual({ text: 'ab{x}cd', caret: 5 });
	});

	it('replaces a selection with the token', () => {
		expect(spliceToken('abcd', 1, 3, '{x}')).toEqual({ text: 'a{x}d', caret: 4 });
	});

	it('appends the token at the end', () => {
		expect(spliceToken('abcd', 4, 4, '{x}')).toEqual({ text: 'abcd{x}', caret: 7 });
	});

	it('inserts into empty text', () => {
		expect(spliceToken('', 0, 0, '{x}')).toEqual({ text: '{x}', caret: 3 });
	});

	it('clamps a start and an end past the text to its length', () => {
		expect(spliceToken('ab', 10, 20, '{x}')).toEqual({ text: 'ab{x}', caret: 5 });
	});
});

describe('withText', () => {
	it('sets the title and keeps the body', () => {
		expect(withText({ title: 'old', body: 'b' }, 'title', 'new')).toEqual({ title: 'new', body: 'b' });
	});

	it('sets the body and keeps the title', () => {
		expect(withText({ title: 't', body: 'old' }, 'body', 'new')).toEqual({ title: 't', body: 'new' });
	});

	it('gives null for a blank title', () => {
		expect(withText({ title: 't', body: 'b' }, 'title', '')).toEqual({ title: null, body: 'b' });
	});

	it('gives null for a blank body', () => {
		expect(withText({ title: 't', body: 'b' }, 'body', '')).toEqual({ title: 't', body: null });
	});

	it('gives null for the other field when it is missing', () => {
		expect(withText({}, 'title', 'new')).toEqual({ title: 'new', body: null });
		expect(withText({}, 'body', 'new')).toEqual({ title: null, body: 'new' });
	});

	it('gives null for the other field when it is null', () => {
		expect(withText({ title: null, body: null }, 'title', 'new')).toEqual({ title: 'new', body: null });
	});

	it('returns the template without its input overrides', () => {
		// #539 tracks this: the overrides are dropped when a variable is inserted.
		const result = withText({ title: 't', body: 'b', inputs: { a: '1' } }, 'title', 'new');
		expect(result).toEqual({ title: 'new', body: 'b' });
		expect(result).not.toHaveProperty('inputs');
	});
});
