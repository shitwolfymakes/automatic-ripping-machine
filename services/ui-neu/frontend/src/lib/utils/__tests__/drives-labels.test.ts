import { describe, it, expect } from 'vitest';
import { connectionLabel, driveTitle, mediaLabel } from '../drives';
import type { DriveView } from '$lib/types/api.gen';

const d = (over: Partial<DriveView>) => ({ device_path: '/dev/sr0', ...over }) as DriveView;

describe('drive labels', () => {
	it('driveTitle prefers the friendly name, then vendor + model, then the node', () => {
		expect(driveTitle(d({ display_name: 'Living room', vendor: 'LG', model: 'X' }))).toBe('Living room');
		expect(driveTitle(d({ display_name: null, vendor: 'LG', model: 'WH16NS60' }))).toBe('LG WH16NS60');
		expect(driveTitle(d({ display_name: null, vendor: null, model: null }))).toBe('/dev/sr0');
	});

	it('mediaLabel names the tray state, never a disc type', () => {
		expect(mediaLabel(d({ media_status: 'loaded' }))).toBe('Disc in drive');
		expect(mediaLabel(d({ media_status: 'no_disc' }))).toBe('No disc');
		expect(mediaLabel(d({ media_status: 'tray_open' }))).toBe('Tray open');
		expect(mediaLabel(d({ media_status: 'not_ready' }))).toBe('Not ready');
		expect(mediaLabel(d({ media_status: null }))).toBe('Unknown');
	});

	it('connectionLabel', () => {
		expect(connectionLabel(d({ connection: 'usb' }))).toBe('USB');
		expect(connectionLabel(d({ connection: 'sata' }))).toBe('SATA');
		expect(connectionLabel(d({ connection: 'other' }))).toBe('Other');
		expect(connectionLabel(d({ connection: null }))).toBeNull();
	});
});
