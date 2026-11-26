import type { IsoLibraryListing, SystemDiagnosticsResponse } from '$lib/types/api.gen';

/** The reason shown when drives can't be enrolled because the ripper is down. */
export const RIPPER_DOWN_REASON = "Drives can't be enrolled until the ripper service is fixed. See System check.";

/** The ISO library's state on the Drives step. */
export interface IsoStatus {
	on: boolean;
	count: number;
	path: string | null;
}

/** Why drives can't be enrolled, or null when the ripper_manager check is fine or absent. */
export function enrollBlockReason(diagnostics: SystemDiagnosticsResponse): string | null {
	const check = diagnostics.checks.find((c) => c.name === 'ripper_manager');
	return check && check.status !== 'ok' ? RIPPER_DOWN_REASON : null;
}

/** The ISO library's status: on with its image count and host path, or off when it did not load. */
export function isoStatus(library: IsoLibraryListing | null): IsoStatus {
	if (!library) return { on: false, count: 0, path: null };
	return { on: true, count: library.entries.filter((e) => e.kind === 'iso').length, path: library.host_path };
}
