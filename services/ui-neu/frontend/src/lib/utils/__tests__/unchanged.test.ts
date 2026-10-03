import { describe, expect, it } from 'vitest';
import { unchanged } from '../unchanged';

describe('unchanged', () => {
	it('treats equal arrays as unchanged', () => {
		expect(unchanged(['tmdb', 'tvmaze'], ['tmdb', 'tvmaze'])).toBe(true);
	});

	it('treats a reordered array as changed', () => {
		expect(unchanged(['tvmaze', 'tmdb'], ['tmdb', 'tvmaze'])).toBe(false);
	});

	it('treats arrays of different lengths as changed', () => {
		expect(unchanged(['tmdb'], ['tmdb', 'tvmaze'])).toBe(false);
		expect(unchanged(['tmdb', 'tvmaze'], ['tmdb'])).toBe(false);
	});

	it('treats null versus an array as changed', () => {
		expect(unchanged(null, ['tmdb'])).toBe(false);
		expect(unchanged(['tmdb'], null)).toBe(false);
	});

	it('falls through to === for equal scalars', () => {
		expect(unchanged('tmdb', 'tmdb')).toBe(true);
		expect(unchanged(300, 300)).toBe(true);
		expect(unchanged(true, true)).toBe(true);
		expect(unchanged('tmdb', 'omdb')).toBe(false);
		expect(unchanged(300, 301)).toBe(false);
	});
});
