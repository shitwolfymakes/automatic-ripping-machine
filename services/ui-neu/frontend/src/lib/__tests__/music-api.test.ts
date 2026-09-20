import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);
function jsonResponse(data: unknown) {
	return { ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve(data) };
}
import { searchMusicMetadata, resolveJob } from '../api/jobs';
beforeEach(() => mockFetch.mockReset());

describe('searchMusicMetadata', () => {
	it('sends query only by default', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ candidates: [] }));
		await searchMusicMetadata('abbey road');
		const url = mockFetch.mock.calls[0][0] as string;
		expect(url).toContain('/api/metadata/music/search?');
		expect(url).toContain('query=abbey+road');
		expect(url).not.toContain('artist=');
		expect(url).not.toContain('track_count=');
	});
	it('adds artist + track_count when given', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ candidates: [] }));
		await searchMusicMetadata('abbey road', { artist: 'beatles', track_count: 17 });
		const url = mockFetch.mock.calls[0][0] as string;
		expect(url).toContain('artist=beatles');
		expect(url).toContain('track_count=17');
	});
});

describe('resolveJob with disc fields', () => {
	it('includes disc_number/disc_total in the body', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ job: {}, fan_out: [] }));
		await resolveJob('job_1', { title: 'Abbey Road', year: 1969, disc_number: 1, disc_total: 2, metadata: { artist: 'X' } });
		const body = JSON.parse((mockFetch.mock.calls[0][1] as RequestInit).body as string);
		expect(body).toEqual({ title: 'Abbey Road', year: 1969, disc_number: 1, disc_total: 2, metadata: { artist: 'X' } });
	});
});
