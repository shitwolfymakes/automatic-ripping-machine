import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, ok = true) {
	return { ok, status: ok ? 200 : 500, statusText: ok ? 'OK' : 'Error', json: () => Promise.resolve(data) };
}

function emptyResponse() {
	return { ok: true, status: 204, statusText: 'No Content', json: () => Promise.reject(new Error('no body')) };
}

import { fetchIsoLibrary, startIsoRip, cancelIsoRip } from '../api/iso';

beforeEach(() => mockFetch.mockReset());

describe('fetchIsoLibrary', () => {
	it('GETs /api/iso/library with no query by default', async () => {
		const listing = { host_path: '/mnt/nas/iso', subpath: '', parent_subpath: null, entries: [] };
		mockFetch.mockResolvedValue(jsonResponse(listing));
		const result = await fetchIsoLibrary();
		expect(mockFetch).toHaveBeenCalledWith('/api/iso/library', expect.objectContaining({ method: 'GET' }));
		expect(result).toEqual(listing);
	});

	it('GETs /api/iso/library?subpath=... when a subpath is given', async () => {
		const listing = { host_path: '/mnt/nas/iso', subpath: 'Movies', parent_subpath: '', entries: [] };
		mockFetch.mockResolvedValue(jsonResponse(listing));
		await fetchIsoLibrary('Movies');
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/iso/library?subpath=Movies',
			expect.objectContaining({ method: 'GET' })
		);
	});
});

describe('startIsoRip', () => {
	it('POSTs /api/iso/rips with the path and session id', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ drive_id: 'drv_iso1' }));
		const result = await startIsoRip('Movies/a.iso', 'ses_1');
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/iso/rips',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ path: 'Movies/a.iso', session_id: 'ses_1' })
			})
		);
		expect(result).toEqual({ drive_id: 'drv_iso1' });
	});

	it('sends a null session id when none is chosen', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ drive_id: 'drv_iso2' }));
		await startIsoRip('a.iso', null);
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/iso/rips',
			expect.objectContaining({ body: JSON.stringify({ path: 'a.iso', session_id: null }) })
		);
	});
});

describe('cancelIsoRip', () => {
	it('DELETEs /api/iso/rips/:drive_id', async () => {
		mockFetch.mockResolvedValue(emptyResponse());
		await expect(cancelIsoRip('drv_iso1')).resolves.toBeUndefined();
		expect(mockFetch).toHaveBeenCalledWith('/api/iso/rips/drv_iso1', expect.objectContaining({ method: 'DELETE' }));
	});
});
