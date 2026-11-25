import { describe, it, expect } from 'vitest';
import type { DriveSummary } from '$lib/api/dashboard';
import { driveSummary, liveSource } from '../summary';

const optical: DriveSummary = { name: 'sr0', kind: 'optical', source: null, retired: false };
const iso: DriveSummary = { name: 'a.iso', kind: 'virtual', source: 'iso', retired: false };
const folder: DriveSummary = { name: 'Disc One', kind: 'virtual', source: 'folder', retired: false };
const retired: DriveSummary = { name: 'b.iso', kind: 'virtual', source: 'iso', retired: true };

describe('driveSummary', () => {
	const drives = { drv_1: optical, drv_iso: iso };

	it('returns the record for a known drive', () => {
		expect(driveSummary(drives, 'drv_iso')).toBe(iso);
	});

	it('returns null for an unknown drive', () => {
		expect(driveSummary(drives, 'drv_2')).toBeNull();
	});

	it('returns null without a drive id', () => {
		expect(driveSummary(drives, null)).toBeNull();
		expect(driveSummary(drives, undefined)).toBeNull();
		expect(driveSummary({ '': iso }, '')).toBeNull();
	});

	it('returns null without a drive map', () => {
		expect(driveSummary(null, 'drv_1')).toBeNull();
		expect(driveSummary(undefined, 'drv_1')).toBeNull();
	});
});

describe('liveSource', () => {
	it('returns the drive for a live ISO or folder source', () => {
		expect(liveSource(iso)).toEqual(iso);
		expect(liveSource(folder)).toEqual(folder);
	});

	it('returns null for a retired virtual drive', () => {
		expect(liveSource(retired)).toBeNull();
	});

	it('returns null for an optical drive', () => {
		expect(liveSource(optical)).toBeNull();
	});

	it('returns null without a drive', () => {
		expect(liveSource(null)).toBeNull();
		expect(liveSource(undefined)).toBeNull();
	});
});
