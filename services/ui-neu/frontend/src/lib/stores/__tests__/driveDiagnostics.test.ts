import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const fetchDriveDiagnosticMock = vi.fn();
vi.mock('$lib/api/drives', () => ({
	fetchDriveDiagnostic: (...a: unknown[]) => fetchDriveDiagnosticMock(...a)
}));

import { DriveDiagnostics } from '$lib/stores/drive-diagnostics.svelte';

const RESULT = { drives: [], system: [] };

beforeEach(() => {
	fetchDriveDiagnosticMock.mockReset();
	vi.useFakeTimers();
	vi.setSystemTime(new Date('2026-01-02T03:04:05'));
});

afterEach(() => {
	vi.useRealTimers();
});

describe('DriveDiagnostics', () => {
	it('starts idle, closed, without a result, error or last run', () => {
		const diag = new DriveDiagnostics();
		expect(diag.running).toBe(false);
		expect(diag.result).toBeNull();
		expect(diag.error).toBeNull();
		expect(diag.open).toBe(false);
		expect(diag.lastRun).toBeNull();
	});

	it('toggle opens and closes the disclosure', () => {
		const diag = new DriveDiagnostics();
		diag.toggle();
		expect(diag.open).toBe(true);
		diag.toggle();
		expect(diag.open).toBe(false);
	});

	it('run stores the result, the last run time and opens the disclosure', async () => {
		fetchDriveDiagnosticMock.mockResolvedValue(RESULT);
		const diag = new DriveDiagnostics();
		await diag.run();
		expect(diag.result).toEqual(RESULT);
		expect(diag.lastRun).toBe(new Date('2026-01-02T03:04:05').toLocaleTimeString());
		expect(diag.open).toBe(true);
		expect(diag.error).toBeNull();
		expect(diag.running).toBe(false);
	});

	it('run is running while the fetch is pending and ignores a second run', async () => {
		let resolve: (v: unknown) => void = () => {};
		fetchDriveDiagnosticMock.mockReturnValue(new Promise((r) => (resolve = r)));
		const diag = new DriveDiagnostics();
		const first = diag.run();
		expect(diag.running).toBe(true);
		await diag.run();
		expect(fetchDriveDiagnosticMock).toHaveBeenCalledTimes(1);
		resolve(RESULT);
		await first;
		expect(diag.running).toBe(false);
	});

	it('run failing with an Error shows its message and clears the result', async () => {
		fetchDriveDiagnosticMock.mockResolvedValueOnce(RESULT).mockRejectedValueOnce(new Error('boom'));
		const diag = new DriveDiagnostics();
		await diag.run();
		const lastRun = diag.lastRun;
		await diag.run();
		expect(diag.error).toBe('boom');
		expect(diag.result).toBeNull();
		expect(diag.open).toBe(true);
		expect(diag.lastRun).toBe(lastRun);
		expect(diag.running).toBe(false);
	});

	it('run failing with a non-Error shows the fallback message and clears the result', async () => {
		fetchDriveDiagnosticMock.mockResolvedValueOnce(RESULT).mockRejectedValueOnce('nope');
		const diag = new DriveDiagnostics();
		await diag.run();
		await diag.run();
		expect(diag.error).toBe('Diagnostic failed');
		expect(diag.result).toBeNull();
		expect(diag.open).toBe(true);
		expect(diag.lastRun).not.toBeNull();
	});

	it('run clears an earlier error when it starts', async () => {
		fetchDriveDiagnosticMock.mockRejectedValueOnce(new Error('boom'));
		const diag = new DriveDiagnostics();
		await diag.run();
		expect(diag.error).toBe('boom');
		let resolve: (v: unknown) => void = () => {};
		fetchDriveDiagnosticMock.mockReturnValueOnce(new Promise((r) => (resolve = r)));
		const second = diag.run();
		expect(diag.error).toBeNull();
		resolve(RESULT);
		await second;
	});
});
