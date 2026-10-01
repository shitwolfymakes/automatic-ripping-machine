import { describe, it, expect } from 'vitest';
import { middleTruncate } from '../truncate';

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
