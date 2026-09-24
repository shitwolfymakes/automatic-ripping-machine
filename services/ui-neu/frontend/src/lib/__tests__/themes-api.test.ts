import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, ok = true, status = 200) {
	return { ok, status, statusText: ok ? 'OK' : 'Error', json: () => Promise.resolve(data) };
}

import { fetchThemes, fetchTheme, uploadTheme, deleteTheme } from '../api/themes';

beforeEach(() => mockFetch.mockReset());

describe('fetchThemes', () => {
	it('calls /api/themes', async () => {
		mockFetch.mockResolvedValue(jsonResponse([{ id: 'default', label: 'Default' }]));
		const result = await fetchThemes();
		expect(result).toEqual([{ id: 'default', label: 'Default' }]);
	});
});

describe('fetchTheme', () => {
	it('calls /api/themes/:id', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ id: 'dark', css: ':root{}' }));
		const result = await fetchTheme('dark');
		expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/api/themes/dark'), expect.any(Object));
		expect(result).toEqual({ id: 'dark', css: ':root{}' });
	});
});

describe('uploadTheme', () => {
	it('POSTs FormData to /api/themes', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ id: 'custom', css: '' }));
		const file = new File(['{}'], 'theme.json', { type: 'application/json' });
		await uploadTheme(file, 'body{}');
		expect(mockFetch).toHaveBeenCalledWith('/api/themes', expect.objectContaining({ method: 'POST' }));
	});
});

describe('deleteTheme', () => {
	it('DELETEs /api/themes/:id', async () => {
		mockFetch.mockResolvedValue(jsonResponse(null));
		await deleteTheme('custom');
		expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/api/themes/custom'), expect.objectContaining({ method: 'DELETE' }));
	});
});
