import type { DriveMediaStatus, DriveView } from '$lib/types/api.gen';

export const DETACHED_LABEL = '○ detached: reconnect the drive';
export const NO_SERIAL_LABEL = 'no serial, identified by port';

// Settings > Drives lists optical drives only; an in-flight ISO
// rip is a virtual drive and never shows there.
export function opticalOnly(drives: DriveView[]): DriveView[] {
	return drives.filter((d) => (d.kind ?? 'optical') === 'optical');
}

export function partitionDrives(all: DriveView[]): {
	enrolled: DriveView[];
	detected: DriveView[];
	ignored: DriveView[];
} {
	const drives = opticalOnly(all);
	return {
		enrolled: drives.filter((d) => d.lifecycle === 'enrolled'),
		detected: drives.filter((d) => d.lifecycle === 'detected'),
		ignored: drives.filter((d) => d.lifecycle === 'ignored')
	};
}

export function isRipping(d: DriveView): boolean {
	return d.current_job?.status === 'ripping';
}

/** The drive's ripper still owns a job (scan, identify, review or rip): the backend refuses Unenroll. */
export function hasLiveJob(d: DriveView): boolean {
	return d.current_job != null;
}

export function driveStatusLabel(d: DriveView): string {
	if (d.status === 'error') return d.last_error ? `error: ${d.last_error}` : 'error';
	if (d.media_status === 'detached' || (d.status === 'offline' && !d.present)) return DETACHED_LABEL;
	return d.status;
}

/** The drive is shown as detached: not in error, and its media is detached or it is offline and not present. */
export function isDriveDetached(d: DriveView): boolean {
	return driveStatusLabel(d) === DETACHED_LABEL;
}

/** The drive is present, but its ripper is offline. */
export function isRipperOfflinePresent(d: DriveView): boolean {
	return d.status === 'offline' && d.present === true && !isDriveDetached(d);
}

const MEDIA_BLOCK_REASONS: Partial<Record<DriveMediaStatus, string>> = {
	no_disc: 'No disc in the drive',
	tray_open: 'The tray is open',
	not_ready: 'The drive is not ready yet',
	unavailable: 'The drive cannot be opened: check its permissions'
};

// Why Start rip cannot work right now, or null when it can. The
// backend refuses a trigger while the drive rips (409) or reports no disc
// ready (400), and the ripper silently drops one while it owns any job or
// when no ripper is listening, so gate the button up front instead of
// letting the click spin and fail (or do nothing). `unknown` is let through
// like the backend does: the ripper decides once it scans.
export function startRipBlockedReason(d: DriveView): string | null {
	if (hasLiveJob(d)) return 'The drive already has a job in progress';
	if (isDriveDetached(d)) return 'The drive is not connected';
	if (isRipperOfflinePresent(d)) return "The drive's ripper is offline";
	return MEDIA_BLOCK_REASONS[d.media_status ?? 'unknown'] ?? null;
}

/** How many of the four prescan override fields are set on the drive. */
export function prescanOverrideCount(d: DriveView): number {
	return [d.prescan_cache_mb, d.prescan_timeout, d.prescan_retries, d.disc_enum_timeout].filter((v) => v != null)
		.length;
}

export function serialLabel(d: DriveView): { text: string; warn: boolean } {
	return d.serial ? { text: d.serial, warn: false } : { text: NO_SERIAL_LABEL, warn: true };
}

/** The name an operator recognises: their friendly name, else vendor + model, else the node. */
export function driveTitle(d: DriveView): string {
	return d.display_name || [d.vendor, d.model].filter(Boolean).join(' ') || d.device_path;
}

/** What the tray holds, from the ripper's heartbeat. The disc type isn't known until a scan. */
export function mediaLabel(d: DriveView): string {
	switch (d.media_status) {
		case 'loaded':
			return 'Disc in drive';
		case 'no_disc':
			return 'No disc';
		case 'tray_open':
			return 'Tray open';
		case 'not_ready':
			return 'Not ready';
		default:
			return 'Unknown';
	}
}

/** The bus chip (USB / SATA), derived server-side from the by-id prefix. */
export function connectionLabel(d: DriveView): string | null {
	switch (d.connection) {
		case 'usb':
			return 'USB';
		case 'sata':
			return 'SATA';
		case 'other':
			return 'Other';
		default:
			return null;
	}
}
