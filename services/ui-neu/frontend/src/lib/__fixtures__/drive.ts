import type { DriveSummary, IsoSourceKind } from '$lib/api/dashboard';

/** A dashboard drive record; an enrolled optical drive unless overridden. */
export function createDriveSummary(overrides: Partial<DriveSummary> = {}): DriveSummary {
	return { name: 'sr0', kind: 'optical', source: null, retired: false, ...overrides };
}

/** A virtual drive reading an ISO (or, with `source`, a folder). */
export function createIsoDrive(
	name: string,
	source: IsoSourceKind = 'iso',
	overrides: Partial<DriveSummary> = {}
): DriveSummary {
	return createDriveSummary({ name, kind: 'virtual', source, ...overrides });
}
