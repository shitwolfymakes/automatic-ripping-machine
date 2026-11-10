import { describe, expect, it } from 'vitest';
import type { IsoLibraryListing, SystemDiagnosticsResponse } from '$lib/types/api.gen';
import { RIPPER_DOWN_REASON, enrollBlockReason, isoStatus } from '../setup-drives';

function diagnostics(checks: Array<{ name: string; status: string }>): SystemDiagnosticsResponse {
	return { status: 'ok', checks, paths: [] } as unknown as SystemDiagnosticsResponse;
}

function library(entries: Array<{ kind: string }>, hostPath = '/isos'): IsoLibraryListing {
	return { host_path: hostPath, subpath: '', parent_subpath: null, entries } as unknown as IsoLibraryListing;
}

describe('enrollBlockReason', () => {
	it('blocks enrolment when the ripper_manager check is not ok', () => {
		const result = enrollBlockReason(diagnostics([{ name: 'ripper_manager', status: 'fail' }]));
		expect(result).toBe(RIPPER_DOWN_REASON);
	});

	it('does not block when the ripper_manager check is ok', () => {
		expect(enrollBlockReason(diagnostics([{ name: 'ripper_manager', status: 'ok' }]))).toBeNull();
	});

	it('does not block when there is no ripper_manager check', () => {
		expect(enrollBlockReason(diagnostics([{ name: 'database', status: 'fail' }]))).toBeNull();
	});
});

describe('isoStatus', () => {
	it('counts only the iso entries of a loaded library', () => {
		const result = isoStatus(library([{ kind: 'iso' }, { kind: 'dir' }, { kind: 'iso' }]));
		expect(result).toEqual({ on: true, count: 2, path: '/isos' });
	});

	it('reports an empty library as on with no images', () => {
		expect(isoStatus(library([]))).toEqual({ on: true, count: 0, path: '/isos' });
	});

	it('keeps a missing host path as it came', () => {
		const result = isoStatus(library([], ''));
		expect(result).toEqual({ on: true, count: 0, path: '' });
	});

	it('reports a library that did not load as off', () => {
		expect(isoStatus(null)).toEqual({ on: false, count: 0, path: null });
	});
});
