import { describe, it, expect } from 'vitest';
import type { DriveView } from '$lib/types/api.gen';
import {
	DETACHED_LABEL,
	NO_SERIAL_LABEL,
	driveStatusLabel,
	isDriveDetached,
	isRipperOfflinePresent,
	isRipping,
	opticalOnly,
	partitionDrives,
	prescanOverrideCount,
	serialLabel,
	startRipBlockedReason
} from '$lib/drives/drives';

function drive(over: Partial<DriveView> = {}): DriveView {
	return {
		id: 'drv_1',
		hostname: 'arm-ripper-abc',
		device_path: '/dev/sr0',
		display_name: null,
		status: 'online',
		last_seen_at: null,
		media_status: null,
		media_status_at: null,
		default_session_id: null,
		rip_speed: null,
		drive_mode: null,
		uhd_capable: null,
		prescan_cache_mb: null,
		prescan_timeout: null,
		prescan_retries: null,
		disc_enum_timeout: null,
		created_at: null,
		updated_at: null,
		lifecycle: 'enrolled',
		present: true,
		identity_kind: 'by_id',
		serial: 'AAAABBBB000E',
		by_id_name: 'usb-X_AAAABBBB000E-0:0',
		vendor: 'PIONEER',
		model: 'BD-RW BDR-S12JX',
		last_error: null,
		current_job: null,
		...over
	} as DriveView;
}

describe('drives/drives', () => {
	it('partitions by lifecycle', () => {
		const p = partitionDrives([
			drive({ id: 'a', lifecycle: 'detected' }),
			drive({ id: 'b' }),
			drive({ id: 'c', lifecycle: 'ignored' })
		]);
		expect(p.enrolled.map((d) => d.id)).toEqual(['b']);
		expect(p.detected.map((d) => d.id)).toEqual(['a']);
		expect(p.ignored.map((d) => d.id)).toEqual(['c']);
	});
	it('leaves virtual drives (in-flight ISO rips) out of every list', () => {
		const p = partitionDrives([
			drive({ id: 'opt' }),
			drive({ id: 'iso', kind: 'virtual', source_kind: 'iso', device_path: '/source/x.iso' })
		]);
		expect(p.enrolled.map((d) => d.id)).toEqual(['opt']);
		expect(opticalOnly([drive({ id: 'iso', kind: 'virtual' }), drive({ id: 'opt', kind: 'optical' })])).toEqual([
			expect.objectContaining({ id: 'opt' })
		]);
	});
	it('labels error before detached, detached before plain offline', () => {
		expect(
			driveStatusLabel(
				drive({ status: 'error', media_status: 'detached', present: false, last_error: 'identity mismatch: x' })
			)
		).toBe('error: identity mismatch: x');
		expect(driveStatusLabel(drive({ status: 'offline', present: false }))).toBe(DETACHED_LABEL);
		expect(driveStatusLabel(drive({ status: 'offline', media_status: 'detached' }))).toBe(DETACHED_LABEL);
		expect(driveStatusLabel(drive({ status: 'offline', present: true }))).toBe('offline');
		expect(driveStatusLabel(drive())).toBe('online');
	});
	it('serialLabel warns on port identity', () => {
		expect(serialLabel(drive())).toEqual({ text: 'AAAABBBB000E', warn: false });
		expect(serialLabel(drive({ serial: null, identity_kind: 'port' }))).toEqual({ text: NO_SERIAL_LABEL, warn: true });
	});
	it('isRipping reads the current job', () => {
		expect(isRipping(drive({ current_job: { id: 'job_1', title: null, status: 'ripping' } }))).toBe(true);
		expect(isRipping(drive())).toBe(false);
	});
});

describe('isDriveDetached', () => {
	it('is true when the media status is detached', () => {
		expect(isDriveDetached(drive({ media_status: 'detached' }))).toBe(true);
	});
	it('is true when the drive is offline and not present', () => {
		expect(isDriveDetached(drive({ status: 'offline', present: false }))).toBe(true);
	});
	it('is false for an online drive', () => {
		expect(isDriveDetached(drive())).toBe(false);
	});
	it('is false for an error drive, even with detached media', () => {
		expect(isDriveDetached(drive({ status: 'error', media_status: 'detached' }))).toBe(false);
	});
});

describe('isRipperOfflinePresent', () => {
	it('is true when the drive is offline and present', () => {
		expect(isRipperOfflinePresent(drive({ status: 'offline', present: true }))).toBe(true);
	});
	it('is false when the drive is offline and not present', () => {
		expect(isRipperOfflinePresent(drive({ status: 'offline', present: false }))).toBe(false);
	});
	it('is false when the drive is offline, present and its media is detached', () => {
		expect(isRipperOfflinePresent(drive({ status: 'offline', present: true, media_status: 'detached' }))).toBe(false);
	});
	it('is false for an online drive', () => {
		expect(isRipperOfflinePresent(drive())).toBe(false);
	});
	it('is false for an error drive', () => {
		expect(isRipperOfflinePresent(drive({ status: 'error' }))).toBe(false);
	});
});

describe('startRipBlockedReason', () => {
	const job = { id: 'job_1', title: null, status: 'ripping' } as const;

	it('puts a live job ahead of every other reason', () => {
		const d = drive({ current_job: job, status: 'offline', present: false, media_status: 'no_disc' });
		expect(startRipBlockedReason(d)).toBe('The drive already has a job in progress');
	});
	it('puts a detached drive ahead of an offline ripper and the media status', () => {
		expect(startRipBlockedReason(drive({ status: 'offline', present: false, media_status: 'no_disc' }))).toBe(
			'The drive is not connected'
		);
	});
	it('puts an offline ripper ahead of the media status', () => {
		expect(startRipBlockedReason(drive({ status: 'offline', present: true, media_status: 'no_disc' }))).toBe(
			"The drive's ripper is offline"
		);
	});
	it.each([
		['no_disc', 'No disc in the drive'],
		['tray_open', 'The tray is open'],
		['not_ready', 'The drive is not ready yet'],
		['unavailable', 'The drive cannot be opened: check its permissions']
	] as const)('blocks on media status %s', (media_status, reason) => {
		expect(startRipBlockedReason(drive({ media_status }))).toBe(reason);
	});
	it.each(['loaded', 'unknown', null] as const)('lets media status %s through', (media_status) => {
		expect(startRipBlockedReason(drive({ media_status }))).toBeNull();
	});
	it('reports a detached media status as not connected, not as a media reason', () => {
		expect(startRipBlockedReason(drive({ media_status: 'detached' }))).toBe('The drive is not connected');
	});
});

describe('prescanOverrideCount', () => {
	it('is 0 when no field is set', () => {
		expect(prescanOverrideCount(drive())).toBe(0);
	});
	it.each(['prescan_cache_mb', 'prescan_timeout', 'prescan_retries', 'disc_enum_timeout'] as const)(
		'counts %s alone',
		(field) => {
			expect(prescanOverrideCount(drive({ [field]: 0 }))).toBe(1);
		}
	);
	it('is 4 when all fields are set', () => {
		expect(
			prescanOverrideCount(drive({ prescan_cache_mb: 1, prescan_timeout: 2, prescan_retries: 3, disc_enum_timeout: 4 }))
		).toBe(4);
	});
});
