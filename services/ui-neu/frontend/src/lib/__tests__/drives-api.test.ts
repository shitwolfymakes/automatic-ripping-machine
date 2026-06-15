import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, ok = true) {
	return { ok, status: ok ? 200 : 500, statusText: ok ? 'OK' : 'Error', json: () => Promise.resolve(data) };
}

function emptyResponse() {
	return { ok: true, status: 204, statusText: 'No Content', json: () => Promise.reject(new Error('no body')) };
}

import {
	fetchDrives,
	updateDrive,
	deleteDrive,
	rescanDrives,
	fetchDriveDiagnostic,
	scanDrive,
	ejectDrive
} from '../api/drives';

beforeEach(() => mockFetch.mockReset());

describe('fetchDrives', () => {
	it('GETs /api/drives', async () => {
		mockFetch.mockResolvedValue(jsonResponse([{ id: 'drv_1' }]));
		const result = await fetchDrives();
		expect(mockFetch).toHaveBeenCalledWith('/api/drives', expect.objectContaining({ method: 'GET' }));
		expect(result).toEqual([{ id: 'drv_1' }]);
	});
});

describe('updateDrive', () => {
	it('PATCHes /api/drives/:id', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ id: 'drv_x', display_name: 'New Name' }));
		const result = await updateDrive('drv_x', { display_name: 'New Name' });
		expect(mockFetch).toHaveBeenCalledWith('/api/drives/drv_x', expect.objectContaining({
			method: 'PATCH',
			body: JSON.stringify({ display_name: 'New Name' })
		}));
		expect(result).toEqual({ id: 'drv_x', display_name: 'New Name' });
	});
});

describe('deleteDrive', () => {
	it('DELETEs /api/drives/:id', async () => {
		mockFetch.mockResolvedValue(emptyResponse());
		await expect(deleteDrive('drv_x')).resolves.toBeUndefined();
		expect(mockFetch).toHaveBeenCalledWith('/api/drives/drv_x', expect.objectContaining({ method: 'DELETE' }));
	});
});

describe('rescanDrives', () => {
	it('POSTs /api/drives/rescan with no query by default', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ online: 1, stale: 0 }));
		const result = await rescanDrives();
		expect(mockFetch).toHaveBeenCalledWith('/api/drives/rescan', expect.objectContaining({ method: 'POST' }));
		expect(result).toEqual({ online: 1, stale: 0 });
	});

	it('POSTs /api/drives/rescan?force=true when force is set', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ online: 1, stale: 0 }));
		await rescanDrives(true);
		expect(mockFetch).toHaveBeenCalledWith('/api/drives/rescan?force=true', expect.objectContaining({ method: 'POST' }));
	});
});

describe('fetchDriveDiagnostic', () => {
	it('GETs /api/drives/diagnostic', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ drives: [] }));
		const result = await fetchDriveDiagnostic();
		expect(mockFetch).toHaveBeenCalledWith('/api/drives/diagnostic', expect.objectContaining({ method: 'GET' }));
		expect(result).toEqual({ drives: [] });
	});
});

describe('scanDrive (MISSING in v3)', () => {
	it('rejects with a not-available error', async () => {
		await expect(scanDrive('drv_x')).rejects.toThrow(/not yet available in v3/);
		expect(mockFetch).not.toHaveBeenCalled();
	});
});

describe('ejectDrive (MISSING in v3)', () => {
	it('rejects with a not-available error', async () => {
		await expect(ejectDrive('drv_x', 'eject')).rejects.toThrow(/not yet available in v3/);
		expect(mockFetch).not.toHaveBeenCalled();
	});
});
