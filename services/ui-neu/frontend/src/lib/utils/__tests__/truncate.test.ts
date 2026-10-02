import { describe, it, expect } from 'vitest';
import { middleTruncate, pathTailTruncate } from '../truncate';

describe('middleTruncate', () => {
	it('keeps short names', () => {
		expect(middleTruncate('a.iso', 36)).toBe('a.iso');
	});

	it('keeps names at exactly the limit', () => {
		const name = 'x'.repeat(36);
		expect(middleTruncate(name, 36)).toBe(name);
	});

	it('keeps the end and extension', () => {
		const out = middleTruncate('The_Grand_Budapest_Hotel_2014_BLURAY_Criterion_Collection_Disc_1.iso', 36);
		expect(out.length).toBe(36);
		expect(out.endsWith('Disc_1.iso')).toBe(true);
		expect(out).toContain('...');
	});

	it('truncates further for the mobile (26 char) breakpoint', () => {
		const out = middleTruncate('The_Grand_Budapest_Hotel_2014_BLURAY_Criterion_Collection_Disc_1.iso', 26);
		expect(out.length).toBe(26);
		expect(out.endsWith('Disc_1.iso')).toBe(true);
		expect(out).toContain('...');
	});
});

describe('pathTailTruncate', () => {
	it('keeps a short path whole', () => {
		expect(pathTailTruncate('Movies/Fantasy', 40)).toBe('Movies/Fantasy');
	});

	it('drops leading segments so the end of the path stays readable', () => {
		expect(pathTailTruncate('Films/Box Sets/Lord of the Rings/Extended (2001)/Fellowship', 40)).toBe(
			'.../Extended (2001)/Fellowship'
		);
	});

	it('falls back to a plain left cut when the last segment alone is too long', () => {
		const out = pathTailTruncate('a/' + 'x'.repeat(60), 20);
		expect(out).toBe('...' + 'x'.repeat(17));
	});
});
