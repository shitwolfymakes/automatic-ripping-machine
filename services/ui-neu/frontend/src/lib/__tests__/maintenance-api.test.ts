import { describe, it, expect } from 'vitest';
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

// Orphan cleanup / maintenance has no v3 backend (ALL MISSING). Every function
// is a stub that rejects before any fetch; the maintenance UI is dormant.
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

	it('fetchImageCacheStats rejects', async () => {
		await expect(fetchImageCacheStats()).rejects.toThrow(/not yet available in v3/);
	});

	it('clearImageCache rejects', async () => {
		await expect(clearImageCache()).rejects.toThrow(/not yet available in v3/);
	});

	it('clearRaw rejects', async () => {
		await expect(clearRaw()).rejects.toThrow(/not yet available in v3/);
	});
});
