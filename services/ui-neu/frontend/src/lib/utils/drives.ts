import type { DriveView } from '$lib/types/api.gen';

export const DETACHED_LABEL = '○ detached: reconnect the drive';
export const NO_SERIAL_LABEL = 'no serial, identified by port';

export function partitionDrives(drives: DriveView[]): {
	enrolled: DriveView[];
	detected: DriveView[];
	ignored: DriveView[];
} {
	return {
		enrolled: drives.filter((d) => d.lifecycle === 'enrolled'),
		detected: drives.filter((d) => d.lifecycle === 'detected'),
		ignored: drives.filter((d) => d.lifecycle === 'ignored')
	};
}

export function isRipping(d: DriveView): boolean {
	return d.status === 'ripping' || d.current_job?.status === 'ripping';
}

export function driveStatusLabel(d: DriveView): string {
	if (d.status === 'error') return d.last_error ? `error: ${d.last_error}` : 'error';
	if (d.media_status === 'detached' || (d.status === 'offline' && !d.present)) return DETACHED_LABEL;
	return d.status;
}

export function serialLabel(d: DriveView): { text: string; warn: boolean } {
	return d.serial ? { text: d.serial, warn: false } : { text: NO_SERIAL_LABEL, warn: true };
}
