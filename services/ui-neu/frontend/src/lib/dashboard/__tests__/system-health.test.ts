import { describe, expect, it } from 'vitest';
import type { PathStatus, StorageRoot, SystemDiagnosticCheck, SystemDiagnosticsResponse } from '$lib/types/api.gen';
import {
	checkDetail,
	checkLabel,
	freeLabel,
	healthTally,
	inScope,
	locationLabel,
	otherChecks,
	pathDetail,
	pathState,
	serviceBadge,
	serviceChecks,
	serviceDescription,
	serviceHost,
	serviceLabel,
	storageHelp,
	storageLabel,
	SERVICE_CHECKS,
	SERVICE_LABELS,
	STORAGE_HELP,
	STORAGE_LABELS,
	SYSTEM_STEP_CHECKS
} from '../system-health';

const check = (over: Partial<SystemDiagnosticCheck>): SystemDiagnosticCheck => ({
	name: 'transcoder',
	status: 'ok',
	...over
});
const path = (over: Partial<PathStatus>): PathStatus => ({
	name: 'MEDIA_ROOT',
	path: '/media',
	exists: true,
	writable: true,
	...over
});
const root = (name: string, free_gb: number): StorageRoot => ({
	name,
	path: `/${name}`,
	total_gb: 100,
	used_gb: 100 - free_gb,
	free_gb,
	percent: 0
});

const diagnostics = (checks: SystemDiagnosticCheck[], paths: PathStatus[]): SystemDiagnosticsResponse => ({
	status: 'ok',
	checks,
	paths
});

describe('healthTally', () => {
	it('is all ok with no issues when every check is ok and every path writable', () => {
		const tally = healthTally(diagnostics([check({})], [path({})]), 'all');
		expect(tally).toEqual({ allOk: true, issueCount: 0, problemCount: 0 });
	});

	it('counts a failing check in scope', () => {
		const tally = healthTally(diagnostics([check({ name: 'drives', status: 'error' })], []), 'all');
		expect(tally).toEqual({ allOk: false, issueCount: 1, problemCount: 1 });
	});

	it('leaves out a failing check the system scope does not cover', () => {
		const tally = healthTally(diagnostics([check({ name: 'drives', status: 'error' })], []), 'system');
		expect(tally).toEqual({ allOk: true, issueCount: 0, problemCount: 0 });
	});

	it('counts a missing path and a read-only one', () => {
		const paths = [path({ name: 'RAW_ROOT', exists: false }), path({ name: 'LOG_DIR', writable: false })];
		const tally = healthTally(diagnostics([], paths), 'all');
		expect(tally).toEqual({ allOk: false, issueCount: 2, problemCount: 2 });
	});

	it('counts a check and a path with the same name as two issues but one problem', () => {
		const checks = [check({ name: 'MEDIA_ROOT', status: 'error' })];
		const tally = healthTally(diagnostics(checks, [path({ exists: false })]), 'all');
		expect(tally).toEqual({ allOk: false, issueCount: 2, problemCount: 1 });
	});
});

describe('the label tables', () => {
	it('name each storage root, say what it is for, and name each service', () => {
		expect(STORAGE_LABELS.MEDIA_ROOT).toBe('Media library');
		expect(STORAGE_HELP.LOG_DIR).toBe('Rip and system logs.');
		expect(SERVICE_CHECKS).toEqual(['ripper_manager', 'transcoder']);
		expect(SERVICE_LABELS.ripper_manager).toBe('Ripper service');
	});
});

describe('storageLabel', () => {
	it('returns the label of a known key', () => {
		expect(storageLabel('MEDIA_ROOT')).toBe('Media library');
	});

	it('returns an unknown key as itself', () => {
		expect(storageLabel('SOMETHING_NEW')).toBe('SOMETHING_NEW');
	});
});

describe('storageHelp', () => {
	it('returns the help line of a known key', () => {
		expect(storageHelp('LOG_DIR')).toBe('Rip and system logs.');
	});

	it('returns an empty line for an unknown key', () => {
		expect(storageHelp('SOMETHING_NEW')).toBe('');
	});
});

describe('serviceLabel', () => {
	it('returns the label of a known key', () => {
		expect(serviceLabel('ripper_manager')).toBe('Ripper service');
	});

	it('returns an unknown key as itself', () => {
		expect(serviceLabel('something_new')).toBe('something_new');
	});
});

describe('checkLabel', () => {
	it('returns the label of a known key', () => {
		expect(checkLabel('makemkv_key')).toBe('MakeMKV key');
	});

	it('returns an unknown key as itself', () => {
		expect(checkLabel('something_new')).toBe('something_new');
	});
});

describe('checkDetail', () => {
	it('shows the detail of an ok check', () => {
		expect(checkDetail(check({ status: 'ok', detail: 'all good' }))).toBe('all good');
	});

	it('shows the detail of a check that is not ok', () => {
		expect(checkDetail(check({ status: 'error', detail: 'disk full' }))).toBe('disk full');
	});

	it('shows OK for an ok check with a null detail', () => {
		expect(checkDetail(check({ status: 'ok', detail: null }))).toBe('OK');
	});

	it('shows OK for an ok check with no detail', () => {
		expect(checkDetail(check({ status: 'ok' }))).toBe('OK');
	});

	it('shows the status of a check that is not ok and has a null detail', () => {
		expect(checkDetail(check({ status: 'warning', detail: null }))).toBe('warning');
	});

	it('shows the status of a check that is not ok and has no detail', () => {
		expect(checkDetail(check({ status: 'error' }))).toBe('error');
	});
});

describe('serviceDescription', () => {
	it('says the ripper manager can start a ripper when ok', () => {
		expect(serviceDescription(check({ name: 'ripper_manager', status: 'ok' }))).toBe(
			'ARM can start a ripper for each drive you enroll.'
		);
	});

	it('says drives cannot be enrolled when the ripper manager is not ok', () => {
		expect(serviceDescription(check({ name: 'ripper_manager', status: 'error' }))).toBe(
			"ARM can't start a ripper for your drives. Drives can't be enrolled until this is fixed."
		);
	});

	it('says the install only rips for a transcoder with location none', () => {
		expect(serviceDescription(check({ location: 'none', status: 'error' }))).toBe(
			'This install only rips; encoding happens elsewhere or not at all.'
		);
	});

	it('says encode containers can run for an ok transcoder elsewhere', () => {
		expect(serviceDescription(check({ location: 'local', status: 'ok' }))).toBe('Encode containers can run.');
	});

	it('says encode containers cannot start for a transcoder that is not ok', () => {
		expect(serviceDescription(check({ location: 'local', status: 'error' }))).toBe(
			"Encode containers can't start right now."
		);
	});
});

describe('serviceBadge', () => {
	it('reads ok as a success badge', () => {
		expect(serviceBadge('ok')).toEqual({ text: 'OK', tone: 'success', glyph: 'check-circle' });
	});

	it('reads error as a danger badge', () => {
		expect(serviceBadge('error')).toEqual({ text: 'Problem', tone: 'danger', glyph: 'x-circle' });
	});

	it('reads any other status as a warning badge', () => {
		expect(serviceBadge('warning')).toEqual({ text: 'Problem', tone: 'warning', glyph: 'warning' });
	});
});

describe('serviceHost', () => {
	it('names a local service as this server', () => {
		expect(serviceHost(check({ location: 'local' }))).toBe('This server');
	});

	it('names a remote service with its host', () => {
		expect(serviceHost(check({ location: 'remote', remote_host: 'nas' }))).toBe('Remote host nas');
	});

	it('names a remote service without a host, trimmed', () => {
		expect(serviceHost(check({ location: 'remote' }))).toBe('Remote host');
	});

	it('returns null for none, a missing location or another one', () => {
		expect(serviceHost(check({ location: 'none' }))).toBeNull();
		expect(serviceHost(check({ location: null }))).toBeNull();
		expect(serviceHost(check({ location: 'elsewhere' }))).toBeNull();
	});
});

describe('locationLabel', () => {
	it('names a local service as this server', () => {
		expect(locationLabel(check({ location: 'local' }))).toBe('This server');
	});

	it('names a remote service with its host', () => {
		expect(locationLabel(check({ location: 'remote', remote_host: 'nas' }))).toBe('Remote host nas');
	});

	it('names a remote service without a host, trimmed', () => {
		expect(locationLabel(check({ location: 'remote' }))).toBe('Remote host');
	});

	it('names no location as ripper only', () => {
		expect(locationLabel(check({ location: 'none' }))).toBe('Ripper only');
	});

	it('returns null for a missing or other location', () => {
		expect(locationLabel(check({ location: null }))).toBeNull();
		expect(locationLabel(check({ location: 'elsewhere' }))).toBeNull();
	});
});

describe('pathState', () => {
	it('reads a missing path as error, writable or not', () => {
		expect(pathState(path({ exists: false }))).toBe('error');
		expect(pathState(path({ exists: false, writable: false }))).toBe('error');
	});

	it('reads a path that is there but not writable as warning', () => {
		expect(pathState(path({ writable: false }))).toBe('warning');
	});

	it('reads a writable path as ok', () => {
		expect(pathState(path({}))).toBe('ok');
	});
});

describe('pathDetail', () => {
	it('reads a missing path as missing, writable or not', () => {
		expect(pathDetail(path({ exists: false }))).toBe('missing');
		expect(pathDetail(path({ exists: false, writable: false }))).toBe('missing');
	});

	it('reads a path that is there but not writable as not writable', () => {
		expect(pathDetail(path({ writable: false }))).toBe('not writable');
	});

	it('reads a writable path as writable', () => {
		expect(pathDetail(path({}))).toBe('writable');
	});
});

describe('freeLabel', () => {
	it('rounds the free space of the named root', () => {
		expect(freeLabel([root('RAW_ROOT', 1), root('MEDIA_ROOT', 41.6)], 'MEDIA_ROOT')).toBe('42 GB free');
	});

	it('says Measuring... with no storage', () => {
		expect(freeLabel(null, 'MEDIA_ROOT')).toBe('Measuring...');
	});

	it('says Measuring... when no root has that name', () => {
		expect(freeLabel([root('RAW_ROOT', 1)], 'MEDIA_ROOT')).toBe('Measuring...');
	});
});

const names = (checks: SystemDiagnosticCheck[]): string[] => checks.map((c) => c.name);
const everyCheck = [
	check({ name: 'ripper_manager' }),
	check({ name: 'config' }),
	check({ name: 'MEDIA_ROOT' }),
	check({ name: 'drives' }),
	check({ name: 'transcoder' })
];

describe('serviceChecks', () => {
	it('keeps the ripper manager and the transcoder in order and drops the rest', () => {
		expect(names(serviceChecks(everyCheck))).toEqual(['ripper_manager', 'transcoder']);
	});
});

describe('otherChecks', () => {
	it('keeps drives and config for all, and drops services and storage roots', () => {
		expect(names(otherChecks(everyCheck, 'all'))).toEqual(['config', 'drives']);
	});

	it('keeps config and drops drives for system', () => {
		expect(names(otherChecks(everyCheck, 'system'))).toEqual(['config']);
	});
});

describe('SYSTEM_STEP_CHECKS', () => {
	it('holds the config, the three storage roots and the two services', () => {
		expect([...SYSTEM_STEP_CHECKS].sort()).toEqual(
			['config', 'MEDIA_ROOT', 'RAW_ROOT', 'LOG_DIR', 'ripper_manager', 'transcoder'].sort()
		);
	});
});

describe('inScope', () => {
	it('takes any check for all', () => {
		expect(inScope('all', 'drives')).toBe(true);
	});

	it('takes a System step check for system', () => {
		expect(inScope('system', 'config')).toBe(true);
	});

	it('leaves out any other check for system', () => {
		expect(inScope('system', 'drives')).toBe(false);
	});
});
