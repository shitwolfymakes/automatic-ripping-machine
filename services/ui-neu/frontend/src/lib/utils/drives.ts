import type { DriveView } from '$lib/types/api.gen';

export const DETACHED_LABEL = '○ detached: reconnect the drive';
export const NO_SERIAL_LABEL = 'no serial, identified by port';

// Settings > Drives lists optical drives only (spec 7.5); an in-flight ISO
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
