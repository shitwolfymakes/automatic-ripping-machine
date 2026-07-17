import { it, expect } from 'vitest';
import { jobPoster, posterSrc, POSTER_PLACEHOLDER } from './poster';

it('jobPoster prefers the manual override over the auto url', () => {
	expect(jobPoster({ poster_url: 'auto.jpg', poster_url_manual: 'manual.jpg' })).toBe('manual.jpg');
});

it('jobPoster falls back to the auto url when no manual override', () => {
	expect(jobPoster({ poster_url: 'auto.jpg', poster_url_manual: null })).toBe('auto.jpg');
});

it('jobPoster returns null when neither is set', () => {
	expect(jobPoster({ poster_url: null, poster_url_manual: null })).toBeNull();
	expect(jobPoster(null)).toBeNull();
	expect(jobPoster(undefined)).toBeNull();
});

it('posterSrc proxies external urls and placeholders empties', () => {
	expect(posterSrc(null)).toBe(POSTER_PLACEHOLDER);
	expect(posterSrc('https://image.tmdb.org/x.jpg')).toContain('/api/images/proxy?url=');
	expect(posterSrc('/local/path.jpg')).toBe('/local/path.jpg');
});
