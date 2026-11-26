import { describe, expect, it } from 'vitest';
import { plural } from '../plural';

describe('plural', () => {
	it('uses the singular for exactly one', () => {
		expect(plural(1, 'drive')).toBe('drive');
	});

	it('appends an s by default for every other count', () => {
		expect(plural(0, 'drive')).toBe('drives');
		expect(plural(2, 'drive')).toBe('drives');
	});

	it('uses the given plural form', () => {
		expect(plural(1, 'match', 'matches')).toBe('match');
		expect(plural(3, 'match', 'matches')).toBe('matches');
	});
});
