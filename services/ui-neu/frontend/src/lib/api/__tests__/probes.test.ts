import { describe, it, expect, vi } from 'vitest';
import { probeGuestAccess, probeFirstRun } from '../probes';

function reply(status: number, body?: () => unknown) {
	return { ok: status >= 200 && status < 300, status, json: body ?? (async () => ({})) };
}

function fetchReturning(r: unknown) {
	return vi.fn().mockResolvedValue(r) as unknown as typeof fetch & ReturnType<typeof vi.fn>;
}

describe('probeGuestAccess', () => {
	it('reports open for an ok reply and asks /api/system/version', async () => {
		const f = fetchReturning(reply(200));
		expect(await probeGuestAccess(f)).toBe('open');
		expect(f).toHaveBeenCalledWith('/api/system/version');
	});

	it('reports closed for a 401', async () => {
		expect(await probeGuestAccess(fetchReturning(reply(401)))).toBe('closed');
	});

	it('reports unknown for any other status', async () => {
		expect(await probeGuestAccess(fetchReturning(reply(503)))).toBe('unknown');
	});

	it('reports unknown when the fetch throws', async () => {
		const f = vi.fn().mockRejectedValue(new Error('down')) as unknown as typeof fetch;
		expect(await probeGuestAccess(f)).toBe('unknown');
	});
});

describe('probeFirstRun', () => {
	it('reports true when first_run is true and asks /api/setup/status', async () => {
		const f = fetchReturning(reply(200, async () => ({ first_run: true })));
		expect(await probeFirstRun(f)).toBe(true);
		expect(f).toHaveBeenCalledWith('/api/setup/status');
	});

	it('reports false when first_run is false', async () => {
		expect(await probeFirstRun(fetchReturning(reply(200, async () => ({ first_run: false }))))).toBe(false);
	});

	it('reports false when first_run is missing', async () => {
		expect(await probeFirstRun(fetchReturning(reply(200, async () => ({}))))).toBe(false);
	});

	it('reports null for a non-ok reply', async () => {
		expect(await probeFirstRun(fetchReturning(reply(503)))).toBeNull();
	});

	it('reports null when the JSON parse throws', async () => {
		const bad = async () => {
			throw new Error('bad json');
		};
		expect(await probeFirstRun(fetchReturning(reply(200, bad)))).toBeNull();
	});

	it('reports null when the fetch throws', async () => {
		const f = vi.fn().mockRejectedValue(new Error('down')) as unknown as typeof fetch;
		expect(await probeFirstRun(f)).toBeNull();
	});
});
