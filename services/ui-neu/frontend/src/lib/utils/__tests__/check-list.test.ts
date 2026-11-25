import { describe, it, expect } from 'vitest';
import { checkedEntries, setChecked } from '$lib/utils/check-list';

const KNOWN = ['artist', 'album', 'title', 'cover'];

describe('checkedEntries', () => {
	it('keeps the known entries in the field order, whatever order the value has', () => {
		expect(checkedEntries(['cover', 'artist'], KNOWN)).toEqual(['artist', 'cover']);
	});

	it('drops unknown entries and repeats', () => {
		expect(checkedEntries(['genre', 'title', 'title'], KNOWN)).toEqual(['title']);
	});

	it('ticks nothing for a value that is not a list', () => {
		expect(checkedEntries(null, KNOWN)).toEqual([]);
		expect(checkedEntries('artist', KNOWN)).toEqual([]);
	});
});

describe('setChecked', () => {
	it('ticks an entry into its place in the field order', () => {
		expect(setChecked(['artist', 'cover'], KNOWN, 'title', true)).toEqual(['artist', 'title', 'cover']);
	});

	it('unticks an entry', () => {
		expect(setChecked(['artist', 'title'], KNOWN, 'artist', false)).toEqual(['title']);
	});

	it('ticking an entry twice keeps it once', () => {
		expect(setChecked(['title'], KNOWN, 'title', true)).toEqual(['title']);
	});

	it('starts from nothing when the value is not a list', () => {
		expect(setChecked(undefined, KNOWN, 'album', true)).toEqual(['album']);
	});
});
