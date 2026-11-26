import { it, expect } from 'vitest';
import type { DriveSummary } from '$lib/api/dashboard';
import { driveLabel } from '../name';

const drives: Record<string, DriveSummary> = {
	drv_1: { name: 'Main Drive', kind: 'optical', source: null, retired: false }
};

it('returns the friendly name when the drive id is known', () => {
	expect(driveLabel('drv_1', drives)).toBe('Main Drive');
});

it('falls back to the raw id when the drive id is not in drives', () => {
	expect(driveLabel('drv_2', drives)).toBe('drv_2');
});

it('falls back to the raw id when drives is missing or null', () => {
	expect(driveLabel('drv_1')).toBe('drv_1');
	expect(driveLabel('drv_1', null)).toBe('drv_1');
});

it('returns empty string for a null or undefined drive id', () => {
	expect(driveLabel(null, drives)).toBe('');
	expect(driveLabel(undefined, drives)).toBe('');
});
