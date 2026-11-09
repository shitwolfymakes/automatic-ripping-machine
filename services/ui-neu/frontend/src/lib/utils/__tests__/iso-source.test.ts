import { describe, it, expect } from 'vitest';
import { isoSourceFor, isoKindFor } from '../iso-source';

describe('isoSourceFor', () => {
	const sources = { d1: '/isos/a.iso' };

	it('returns the source of a drive that has one', () => {
		expect(isoSourceFor('d1', sources)).toBe('/isos/a.iso');
	});

	it('returns null for a drive with no entry', () => {
		expect(isoSourceFor('d2', sources)).toBeNull();
	});

	it('returns null for a null, undefined or empty drive id', () => {
		expect(isoSourceFor(null, sources)).toBeNull();
		expect(isoSourceFor(undefined, sources)).toBeNull();
		expect(isoSourceFor('', { '': '/x.iso' })).toBeNull();
	});

	it('returns null when the map is missing', () => {
		expect(isoSourceFor('d1', null)).toBeNull();
		expect(isoSourceFor('d1', undefined)).toBeNull();
	});
});

describe('isoKindFor', () => {
	const kinds = { d1: 'folder' as const, d3: 'iso' as const };

	it('returns the kind of a drive that has one', () => {
		expect(isoKindFor('d1', kinds)).toBe('folder');
		expect(isoKindFor('d3', kinds)).toBe('iso');
	});

	it('defaults to iso for a drive with no entry', () => {
		expect(isoKindFor('d2', kinds)).toBe('iso');
	});

	it('defaults to iso for a null, undefined or empty drive id', () => {
		expect(isoKindFor(null, kinds)).toBe('iso');
		expect(isoKindFor(undefined, kinds)).toBe('iso');
		expect(isoKindFor('', { '': 'folder' })).toBe('iso');
	});

	it('defaults to iso when the map is missing', () => {
		expect(isoKindFor('d1', null)).toBe('iso');
		expect(isoKindFor('d1', undefined)).toBe('iso');
	});
});
