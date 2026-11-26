import { describe, it, expect } from 'vitest';
import { posterSrc, POSTER_PLACEHOLDER } from '../poster';

describe('posterSrc', () => {
	it('returns placeholder for null', () => {
		expect(posterSrc(null)).toBe(POSTER_PLACEHOLDER);
	});

	it('returns placeholder for undefined', () => {
		expect(posterSrc(undefined)).toBe(POSTER_PLACEHOLDER);
	});

	it('returns placeholder for empty string', () => {
		expect(posterSrc('')).toBe(POSTER_PLACEHOLDER);
	});

	it('returns relative path unchanged', () => {
		expect(posterSrc('/images/poster.jpg')).toBe('/images/poster.jpg');
	});

	it('proxies https URL through backend', () => {
		const url = 'https://m.media-amazon.com/images/poster.jpg';
		expect(posterSrc(url)).toBe(`/api/images/proxy?url=${encodeURIComponent(url)}`);
	});

	it('proxies https URL from tmdb through backend', () => {
		const url = 'https://image.tmdb.org/t/p/w500/poster.jpg';
		expect(posterSrc(url)).toBe(`/api/images/proxy?url=${encodeURIComponent(url)}`);
	});

	it('returns path-only strings unchanged', () => {
		expect(posterSrc('poster.jpg')).toBe('poster.jpg');
	});
});
