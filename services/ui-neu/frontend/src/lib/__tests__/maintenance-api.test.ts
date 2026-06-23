import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, ok = true) {
	return { ok, status: ok ? 200 : 500, statusText: ok ? 'OK' : 'Error', json: () => Promise.resolve(data) };
}

import {
	fetchSummary,
	fetchOrphanLogs,
	fetchOrphanFolders,
	deleteLog,
	deleteFolder,
	bulkDeleteLogs,
	bulkDeleteFolders,
	dismissAllNotifications,
	purgeNotifications,
	cleanupTranscoder,
	clearRaw,
	fetchImageCacheStats,
	clearImageCache
} from '$lib/api/maintenance';

beforeEach(() => mockFetch.mockReset());

// Orphan cleanup / maintenance largely has no v3 backend; those functions are
// stubs that reject before any fetch. The image-cache stats/clear endpoints DO
// exist (image_cache.stats()/clear()) and hit the real backend.
describe('maintenance MISSING stubs', () => {
	it('fetchSummary rejects', async () => {
		await expect(fetchSummary()).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchOrphanLogs rejects', async () => {
		await expect(fetchOrphanLogs()).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchOrphanFolders rejects', async () => {
		await expect(fetchOrphanFolders()).rejects.toThrow(/not yet available in v3/);
	});

	it('deleteLog rejects', async () => {
		await expect(deleteLog('/tmp/test.log')).rejects.toThrow(/not yet available in v3/);
	});

	it('deleteFolder rejects', async () => {
		await expect(deleteFolder('/raw/orphan')).rejects.toThrow(/not yet available in v3/);
	});

	it('bulkDeleteLogs rejects', async () => {
		await expect(bulkDeleteLogs(['/a.log', '/b.log'])).rejects.toThrow(/not yet available in v3/);
	});

	it('bulkDeleteFolders rejects', async () => {
		await expect(bulkDeleteFolders(['/raw/a'])).rejects.toThrow(/not yet available in v3/);
	});

	it('dismissAllNotifications rejects', async () => {
		await expect(dismissAllNotifications()).rejects.toThrow(/not yet available in v3/);
	});

	it('purgeNotifications rejects', async () => {
		await expect(purgeNotifications()).rejects.toThrow(/not yet available in v3/);
	});

	it('cleanupTranscoder rejects', async () => {
		await expect(cleanupTranscoder()).rejects.toThrow(/not yet available in v3/);
	});

	it('clearRaw rejects', async () => {
		await expect(clearRaw()).rejects.toThrow(/not yet available in v3/);
	});
});

describe('image cache (real backend)', () => {
	it('fetchImageCacheStats GETs /api/images/cache', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ count: 2, size_mb: 1.5 }));
		const result = await fetchImageCacheStats();
		expect(mockFetch).toHaveBeenCalledWith('/api/images/cache', expect.objectContaining({ method: 'GET' }));
		expect(result).toEqual({ count: 2, size_mb: 1.5 });
	});

	it('clearImageCache POSTs /api/images/cache/clear', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ count: 0, size_mb: 0, cleared: 2, freed_bytes: 1024 }));
		const result = await clearImageCache();
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/images/cache/clear',
			expect.objectContaining({ method: 'POST' })
		);
		expect(result).toEqual({ count: 0, size_mb: 0, cleared: 2, freed_bytes: 1024 });
	});
});
