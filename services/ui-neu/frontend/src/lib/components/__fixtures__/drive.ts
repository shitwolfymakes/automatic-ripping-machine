import type { DriveView } from '$lib/types/api.gen';

// An enrolled, online, present drive with no overrides. Pass the fields a test
// cares about.
export function createDrive(overrides: Partial<DriveView> = {}): DriveView {
	return {
		id: 'drv_1',
		hostname: 'arm-host',
		device_path: '/dev/sr0',
		display_name: 'Main Drive',
		status: 'online',
		last_seen_at: null,
		media_status: null,
		media_status_at: null,
		default_session_id: null,
		rip_speed: null,
		drive_mode: null,
		uhd_capable: false,
		prescan_cache_mb: null,
		prescan_timeout: null,
		prescan_retries: null,
		disc_enum_timeout: null,
		created_at: null,
		updated_at: null,
		lifecycle: 'enrolled',
		present: true,
		identity_kind: 'by_id',
		serial: 'SN123',
		by_id_name: 'usb-VENDOR_MODEL_SN123-0:0',
		vendor: 'VENDOR',
		model: 'MODEL',
		last_error: null,
		current_job: null,
		...overrides
	};
}
