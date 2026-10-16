import { describe, it, expect, vi, beforeEach } from 'vitest';

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn(() => Promise.resolve({ candidates: [] })) }));
vi.mock('../client', async (orig) => {
	const actual = (await orig()) as Record<string, unknown>;
	return { ...actual, apiFetch };
});

import { fetchMatchDetails, searchMetadata } from '../jobs';

describe('match picker API helpers', () => {
	beforeEach(() => apiFetch.mockClear());

	it('searchMetadata sends the year when given', async () => {
		await searchMetadata('kolchak', 'tv', 'tmdb', 1974);
		expect((apiFetch.mock.calls[0] as unknown[])[0]).toBe(
			'/api/metadata/search?title=kolchak&type=tv&provider=tmdb&year=1974'
		);
	});

	it('searchMetadata omits a missing year', async () => {
		await searchMetadata('kolchak', 'tv', undefined, null);
		expect((apiFetch.mock.calls[0] as unknown[])[0]).toBe('/api/metadata/search?title=kolchak&type=tv');
	});

	it('fetchMatchDetails builds the details URL', async () => {
		await fetchMatchDetails('tvmaze', 'tv', '1');
		expect((apiFetch.mock.calls[0] as unknown[])[0]).toBe('/api/metadata/details?provider=tvmaze&type=tv&id=1');
	});
});
