import { describe, expect, it } from 'vitest';
import type { PathStatus, StorageRoot, SystemDiagnosticCheck } from '$lib/types/api.gen';
import {
	checkLabel,
	freeLabel,
	inScope,
	locationLabel,
	pathDetail,
	pathState,
	serviceBadge,
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

describe('the label tables', () => {
	it('name each storage root, say what it is for, and name each service', () => {
		expect(STORAGE_LABELS.MEDIA_ROOT).toBe('Media library');
		expect(STORAGE_HELP.LOG_DIR).toBe('Rip and system logs.');
		expect(SERVICE_CHECKS).toEqual(['ripper_manager', 'transcoder']);
		expect(SERVICE_LABELS.ripper_manager).toBe('Ripper service');
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
