import { it, expect } from 'vitest';
import { driveLabel } from './drive-name';

it('returns the friendly name when the drive id is known', () => {
	expect(driveLabel('drv_1', { drv_1: 'Main Drive' })).toBe('Main Drive');
});

it('falls back to the raw id when the drive id is not in driveNames', () => {
	expect(driveLabel('drv_2', { drv_1: 'Main Drive' })).toBe('drv_2');
});

it('falls back to the raw id when driveNames is missing or null', () => {
	expect(driveLabel('drv_1')).toBe('drv_1');
	expect(driveLabel('drv_1', null)).toBe('drv_1');
});

it('returns empty string for a null or undefined drive id', () => {
	expect(driveLabel(null, { drv_1: 'Main Drive' })).toBe('');
	expect(driveLabel(undefined, { drv_1: 'Main Drive' })).toBe('');
});
