// System health's labels, and the small decisions its summary and cards
// make about a result, a check, a storage path or a service.
import type { PathStatus, StorageRoot, SystemDiagnosticCheck, SystemDiagnosticsResponse } from '$lib/types/api.gen';

/** Operator-facing names for the storage roots. */
export const STORAGE_LABELS: Record<string, string> = {
	MEDIA_ROOT: 'Media library',
	RAW_ROOT: 'Raw rips',
	LOG_DIR: 'Logs'
};

/** One line saying what each storage root is for. */
export const STORAGE_HELP: Record<string, string> = {
	MEDIA_ROOT: 'Finished files are filed here.',
	RAW_ROOT: 'Rips land here before they are named and moved.',
	LOG_DIR: 'Rip and system logs.'
};

/** The names of the checks that report a service. */
export const SERVICE_CHECKS = ['ripper_manager', 'transcoder'];

/** The checks the setup walkthrough's System step is about: the set
 * the backend reconciles on (routers/setup.py _SYSTEM_STEP_CHECKS). */
export const SYSTEM_STEP_CHECKS: ReadonlySet<string> = new Set([
	'config',
	'MEDIA_ROOT',
	'RAW_ROOT',
	'LOG_DIR',
	...SERVICE_CHECKS
]);

/** Whether a check belongs to `scope`: every check for 'all', or only
 * the System step's for 'system'. */
export function inScope(scope: 'all' | 'system', name: string): boolean {
	return scope === 'all' || SYSTEM_STEP_CHECKS.has(name);
}

/** How a result's summary reads: whether everything is fine, how many
 * failing checks and paths it has, and how many distinct names those
 * are (a check and a path can share one). */
export interface HealthTally {
	allOk: boolean;
	issueCount: number;
	problemCount: number;
}

/** Tallies a result's failing checks (within `scope`) and failing
 * paths for the summary. */
export function healthTally(result: SystemDiagnosticsResponse, scope: 'all' | 'system'): HealthTally {
	const issues = result.checks.filter((c) => c.status !== 'ok' && inScope(scope, c.name));
	const pathIssues = result.paths.filter((p) => !p.exists || !p.writable);
	return {
		allOk: issues.length === 0 && pathIssues.length === 0,
		issueCount: issues.length + pathIssues.length,
		problemCount: new Set([...issues.map((c) => c.name), ...pathIssues.map((p) => p.name)]).size
	};
}

/** The checks that report a service, in the order they came. */
export function serviceChecks(checks: readonly SystemDiagnosticCheck[]): SystemDiagnosticCheck[] {
	return checks.filter((c) => SERVICE_CHECKS.includes(c.name));
}

/** The checks in `scope` that are neither a service nor a storage root,
 * in the order they came. */
export function otherChecks(
	checks: readonly SystemDiagnosticCheck[],
	scope: 'all' | 'system'
): SystemDiagnosticCheck[] {
	return checks.filter(
		(c) => !SERVICE_CHECKS.includes(c.name) && !(c.name in STORAGE_LABELS) && inScope(scope, c.name)
	);
}

// Operator-facing names for the backend's check keys.
const CHECK_LABELS: Record<string, string> = {
	config: 'Configuration',
	MEDIA_ROOT: 'Media root',
	RAW_ROOT: 'Raw root',
	LOG_DIR: 'Log directory',
	drives: 'Drives',
	makemkv_key: 'MakeMKV key',
	community_keydb: 'Community keydb',
	makemkv_sdf: 'MakeMKV SDF',
	transcoder: 'Transcoder',
	ripper_manager: 'Ripper manager'
};

/** Operator-facing names for the services. */
export const SERVICE_LABELS: Record<string, string> = { ripper_manager: 'Ripper service', transcoder: 'Transcoder' };

/** A storage root's operator-facing name, or its key when it has none. */
export function storageLabel(name: string): string {
	return STORAGE_LABELS[name] ?? name;
}

/** The line saying what a storage root is for, or an empty one. */
export function storageHelp(name: string): string {
	return STORAGE_HELP[name] ?? '';
}

/** A service's operator-facing name, or its key when it has none. */
export function serviceLabel(name: string): string {
	return SERVICE_LABELS[name] ?? name;
}

/** A check's operator-facing name, or its key when it has none. */
export function checkLabel(name: string): string {
	return CHECK_LABELS[name] ?? name;
}

/** A check row's detail: the check's own detail, or "OK" (or its
 * status, when it isn't ok) for a check that has none. */
export function checkDetail(c: Pick<SystemDiagnosticCheck, 'status' | 'detail'>): string {
	return c.detail ?? (c.status === 'ok' ? 'OK' : c.status);
}

/** How much space the named storage root has free, or that it is still
 * being measured. */
export function freeLabel(storage: readonly StorageRoot[] | null, name: string): string {
	const root = storage?.find((r) => r.name === name);
	return root ? `${Math.round(root.free_gb)} GB free` : 'Measuring...';
}

/** The badge a service's status shows. */
export function serviceBadge(status: string): {
	text: string;
	tone: string;
	glyph: 'check-circle' | 'x-circle' | 'warning';
} {
	if (status === 'ok') return { text: 'OK', tone: 'success', glyph: 'check-circle' };
	if (status === 'error') return { text: 'Problem', tone: 'danger', glyph: 'x-circle' };
	return { text: 'Problem', tone: 'warning', glyph: 'warning' };
}

/** A service card's one-line description: what the ripper manager or
 * the transcoder can do, given its status and where it runs. */
export function serviceDescription(c: Pick<SystemDiagnosticCheck, 'name' | 'status' | 'location'>): string {
	if (c.name === 'ripper_manager') {
		return c.status === 'ok'
			? 'ARM can start a ripper for each drive you enroll.'
			: "ARM can't start a ripper for your drives. Drives can't be enrolled until this is fixed.";
	}
	if (c.location === 'none') return 'This install only rips; encoding happens elsewhere or not at all.';
	return c.status === 'ok' ? 'Encode containers can run.' : "Encode containers can't start right now.";
}

/** Where a service runs: "This server", or "Remote host <name>"
 * ("Remote host" when the name is missing). Null for any other location. */
export function serviceHost(c: Pick<SystemDiagnosticCheck, 'location' | 'remote_host'>): string | null {
	if (c.location === 'local') return 'This server';
	if (c.location === 'remote') return `Remote host ${c.remote_host ?? ''}`.trim();
	return null;
}

/** The host a service runs on, or "Ripper only" for a service that runs
 * nowhere. Null when the check does not say. */
export function locationLabel(c: SystemDiagnosticCheck): string | null {
	return c.location === 'none' ? 'Ripper only' : serviceHost(c);
}

/** A storage path's status: error when missing, warning when read-only,
 * else ok. */
export function pathState(p: PathStatus): SystemDiagnosticCheck['status'] {
	if (!p.exists) return 'error';
	if (!p.writable) return 'warning';
	return 'ok';
}

/** A storage path's state in words. */
export function pathDetail(p: PathStatus): string {
	if (!p.exists) return 'missing';
	if (!p.writable) return 'not writable';
	return 'writable';
}
