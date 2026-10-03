import { describe, it, expect } from 'vitest';
import type { DriveView } from '$lib/types/api.gen';
import { DETACHED_LABEL, NO_SERIAL_LABEL, driveStatusLabel, isRipping, partitionDrives, serialLabel } from '$lib/utils/drives';

function drive(over: Partial<DriveView> = {}): DriveView {
	return {
		id: 'drv_1', hostname: 'arm-ripper-abc', device_path: '/dev/sr0', display_name: null, status: 'online',
		last_seen_at: null, media_status: null, media_status_at: null, default_session_id: null, rip_speed: null,
		drive_mode: null, uhd_capable: null, prescan_cache_mb: null, prescan_timeout: null, prescan_retries: null,
		disc_enum_timeout: null, created_at: null, updated_at: null, lifecycle: 'enrolled', present: true,
		identity_kind: 'by_id', serial: 'AAAABBBB000E', by_id_name: 'usb-X_AAAABBBB000E-0:0', vendor: 'PIONEER',
		model: 'BD-RW BDR-S12JX', last_error: null, current_job: null, ...over
	} as DriveView;
}

describe('utils/drives', () => {
	it('partitions by lifecycle', () => {
		const p = partitionDrives([drive({ id: 'a', lifecycle: 'detected' }), drive({ id: 'b' }), drive({ id: 'c', lifecycle: 'ignored' })]);
		expect(p.enrolled.map((d) => d.id)).toEqual(['b']);
		expect(p.detected.map((d) => d.id)).toEqual(['a']);
		expect(p.ignored.map((d) => d.id)).toEqual(['c']);
	});
	it('labels error before detached, detached before plain offline', () => {
		expect(driveStatusLabel(drive({ status: 'error', media_status: 'detached', present: false, last_error: 'identity mismatch: x' }))).toBe('error: identity mismatch: x');
		expect(driveStatusLabel(drive({ status: 'offline', present: false }))).toBe(DETACHED_LABEL);
		expect(driveStatusLabel(drive({ status: 'offline', media_status: 'detached' }))).toBe(DETACHED_LABEL);
		expect(driveStatusLabel(drive({ status: 'offline', present: true }))).toBe('offline');
		expect(driveStatusLabel(drive())).toBe('online');
	});
	it('serialLabel warns on port identity', () => {
		expect(serialLabel(drive())).toEqual({ text: 'AAAABBBB000E', warn: false });
		expect(serialLabel(drive({ serial: null, identity_kind: 'port' }))).toEqual({ text: NO_SERIAL_LABEL, warn: true });
	});
	it('isRipping reads status or the current job', () => {
		expect(isRipping(drive({ status: 'ripping' }))).toBe(true);
		expect(isRipping(drive({ current_job: { id: 'job_1', title: null, status: 'ripping' } }))).toBe(true);
		expect(isRipping(drive())).toBe(false);
	});
});
