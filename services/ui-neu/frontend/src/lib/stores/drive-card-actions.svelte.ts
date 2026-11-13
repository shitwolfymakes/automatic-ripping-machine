// The full drive card's actions: manual rip, unenroll, 4K and rip mode, with
// each one's busy flag, the unenroll confirmation and the two error
// messages.
import type { DriveView } from '$lib/types/api.gen';
import { unenrollDrive, updateDrive } from '$lib/api/drives';
import { triggerManual } from '$lib/api/jobs';
import { errorMessage } from '$lib/utils/errors';

export class DriveCardActions {
	selectedSessionId = $state('');
	triggering = $state(false);
	manualError = $state<string | null>(null);
	unenrolling = $state(false);
	unenrollError = $state<string | null>(null);
	confirmUnenrollOpen = $state(false);
	togglingUhd = $state(false);
	togglingMode = $state(false);

	/** Reloads the drive list; unenroll waits for it. */
	readonly #refresh: () => void | Promise<void>;

	constructor(refresh: () => void | Promise<void>) {
		this.#refresh = refresh;
	}

	startManualRip = async (driveId: string): Promise<void> => {
		if (this.triggering) return;
		this.triggering = true;
		this.manualError = null;
		try {
			await triggerManual({ drive_id: driveId, session_id: this.selectedSessionId || null });
			this.selectedSessionId = '';
			this.#refresh();
		} catch (e) {
			this.manualError = errorMessage(e, 'Manual rip failed');
		} finally {
			this.triggering = false;
		}
	};

	requestUnenroll = (): void => {
		this.unenrollError = null;
		this.confirmUnenrollOpen = true;
	};

	confirmUnenroll = async (driveId: string): Promise<void> => {
		this.confirmUnenrollOpen = false;
		this.unenrolling = true;
		try {
			await unenrollDrive(driveId);
			await this.#refresh();
		} catch (e) {
			this.unenrollError = errorMessage(e, 'Unenroll failed');
		} finally {
			this.unenrolling = false;
		}
	};

	cancelUnenroll = (): void => {
		this.confirmUnenrollOpen = false;
	};

	toggleUhd = async (drive: Pick<DriveView, 'id' | 'uhd_capable'>): Promise<void> => {
		this.togglingUhd = true;
		try {
			await updateDrive(drive.id, { uhd_capable: !drive.uhd_capable });
			this.#refresh();
		} catch {
			// ignore
		} finally {
			this.togglingUhd = false;
		}
	};

	// '' = no mode of its own: follow the global auto-rip default (null on the wire).
	setMode = async (driveId: string, next: string): Promise<void> => {
		this.togglingMode = true;
		try {
			await updateDrive(driveId, { drive_mode: next === '' ? null : (next as 'auto' | 'manual') });
			this.#refresh();
		} catch {
			// ignore
		} finally {
			this.togglingMode = false;
		}
	};
}
