// The MakeMKV key's status line: what a drive's ripper last reported
// about the key, shown under the key field in Settings and setup.
import type { ConfigView, DriveView } from '$lib/types/api.gen';
import { driveTitle } from '$lib/drives/drives';

/** A key status for a StatusStrip: its tone, title and message. */
interface MakemkvKeyStatus {
	tone: 'ok' | 'danger' | 'muted' | 'busy';
	title: string;
	message: string | null;
}

/** The key's status: valid, naming the drive that checked it when that
 * drive is listed; not accepted, with the state the ripper reported; or,
 * until a drive has checked it, waiting for one, or for a drive to be
 * enrolled (a virtual drive doesn't count). Null until the config has
 * loaded. */
export function makemkvKeyStatus(cfg: ConfigView | null, drives: readonly DriveView[]): MakemkvKeyStatus | null {
	if (!cfg) return null;
	if (cfg.makemkv_key_valid === true) {
		const checker = drives.find((d) => d.id === cfg.makemkv_key_checked_by_drive_id) ?? null;
		return {
			tone: 'ok',
			title: checker ? `Valid, checked by ${driveTitle(checker)}` : 'Valid',
			message: null
		};
	}
	if (cfg.makemkv_key_valid === false)
		return { tone: 'danger', title: 'Key not accepted', message: cfg.makemkv_key_state ?? null };
	const enrolled = drives.filter((d) => d.lifecycle === 'enrolled' && d.kind !== 'virtual');
	if (enrolled.length === 0) return { tone: 'muted', title: 'Will be checked when you enroll a drive', message: null };
	return { tone: 'busy', title: 'Waiting for a drive to check the key...', message: null };
}
