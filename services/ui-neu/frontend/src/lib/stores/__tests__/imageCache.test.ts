import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchImageCacheStatsMock = vi.fn();
const clearImageCacheMock = vi.fn();
vi.mock('$lib/api/maintenance', () => ({
	fetchImageCacheStats: (...a: unknown[]) => fetchImageCacheStatsMock(...a),
	clearImageCache: (...a: unknown[]) => clearImageCacheMock(...a)
}));

import { ImageCache } from '$lib/stores/image-cache.svelte';

beforeEach(() => {
	fetchImageCacheStatsMock.mockReset();
	clearImageCacheMock.mockReset();
});

describe('ImageCache', () => {
	it('starts with no stats, idle, closed and without feedback', () => {
		const cache = new ImageCache();
		expect(cache.stats).toBeNull();
		expect(cache.loading).toBe(false);
		expect(cache.busy).toBe(false);
		expect(cache.confirmOpen).toBe(false);
		expect(cache.feedback).toBeNull();
	});

	it('load stores the stats and clears loading', async () => {
		fetchImageCacheStatsMock.mockResolvedValue({ count: 3, size_mb: 1.5 });
		const cache = new ImageCache();
		await cache.load();
		expect(cache.stats).toEqual({ count: 3, size_mb: 1.5 });
		expect(cache.loading).toBe(false);
	});

	it('load is loading while the request runs', async () => {
		let resolve: (v: unknown) => void = () => {};
		fetchImageCacheStatsMock.mockReturnValue(new Promise((r) => (resolve = r)));
		const cache = new ImageCache();
		const pending = cache.load();
		expect(cache.loading).toBe(true);
		resolve({ count: 1, size_mb: 0.1 });
		await pending;
		expect(cache.loading).toBe(false);
	});

	it('load sets the stats to null when the request fails', async () => {
		fetchImageCacheStatsMock.mockResolvedValueOnce({ count: 3, size_mb: 1.5 });
		const cache = new ImageCache();
		await cache.load();
		fetchImageCacheStatsMock.mockRejectedValueOnce(new Error('down'));
		await cache.load();
		expect(cache.stats).toBeNull();
		expect(cache.loading).toBe(false);
	});

	it('clear reports one image with the freed MB to one decimal and reloads the stats', async () => {
		clearImageCacheMock.mockResolvedValue({ count: 0, size_mb: 0, cleared: 1, freed_bytes: 1572864 });
		fetchImageCacheStatsMock.mockResolvedValue({ count: 0, size_mb: 0 });
		const cache = new ImageCache();
		await cache.clear();
		expect(cache.feedback).toEqual({ type: 'success', message: 'Cleared 1 cached image (1.5 MB)' });
		expect(fetchImageCacheStatsMock).toHaveBeenCalledTimes(1);
		expect(cache.stats).toEqual({ count: 0, size_mb: 0 });
		expect(cache.busy).toBe(false);
	});

	it('clear pluralises several images', async () => {
		clearImageCacheMock.mockResolvedValue({ count: 0, size_mb: 0, cleared: 4, freed_bytes: 2097152 });
		fetchImageCacheStatsMock.mockResolvedValue({ count: 0, size_mb: 0 });
		const cache = new ImageCache();
		await cache.clear();
		expect(cache.feedback?.message).toBe('Cleared 4 cached images (2.0 MB)');
	});

	it('clear treats missing cleared and freed_bytes as zero', async () => {
		clearImageCacheMock.mockResolvedValue({ count: 0, size_mb: 0 });
		fetchImageCacheStatsMock.mockResolvedValue({ count: 0, size_mb: 0 });
		const cache = new ImageCache();
		await cache.clear();
		expect(cache.feedback).toEqual({ type: 'success', message: 'Cleared 0 cached images (0.0 MB)' });
	});

	it('clear closes the dialog and is busy while it runs', async () => {
		let resolve: (v: unknown) => void = () => {};
		clearImageCacheMock.mockReturnValue(new Promise((r) => (resolve = r)));
		fetchImageCacheStatsMock.mockResolvedValue({ count: 0, size_mb: 0 });
		const cache = new ImageCache();
		cache.confirmOpen = true;
		const pending = cache.clear();
		expect(cache.busy).toBe(true);
		expect(cache.confirmOpen).toBe(false);
		resolve({ count: 0, size_mb: 0 });
		await pending;
		expect(cache.busy).toBe(false);
	});

	it('clear shows the error message when the request fails with an Error', async () => {
		clearImageCacheMock.mockRejectedValue(new Error('boom'));
		const cache = new ImageCache();
		await cache.clear();
		expect(cache.feedback).toEqual({ type: 'error', message: 'boom' });
		expect(cache.busy).toBe(false);
	});

	it('clear shows a generic message when the failure is not an Error', async () => {
		clearImageCacheMock.mockRejectedValue('nope');
		const cache = new ImageCache();
		await cache.clear();
		expect(cache.feedback).toEqual({ type: 'error', message: 'Failed to clear cache' });
	});
});
