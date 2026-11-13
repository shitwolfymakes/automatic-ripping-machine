// The drive lifecycle lists' per-drive actions (enroll, ignore and un-ignore),
// with each drive's busy kind and last error; a success tells the caller to
// reload.
import { enrollDrive, ignoreDrive, unignoreDrive } from '$lib/api/drives';
import { errorMessage } from '$lib/utils/errors';

export class DriveLifecycleActions {
	/** Which kind of action is pending, by drive id. */
	busy = $state<Record<string, 'enroll' | 'other'>>({});
	/** The last failure message, by drive id. */
	errors = $state<Record<string, string>>({});

	/** Reloads the lists after a successful action. */
	readonly #onchanged: () => void;

	constructor(onchanged: () => void) {
		this.#onchanged = onchanged;
	}

	readonly #run = async (id: string, kind: 'enroll' | 'other', action: () => Promise<unknown>): Promise<void> => {
		this.busy = { ...this.busy, [id]: kind };
		const { [id]: _drop, ...rest } = this.errors;
		this.errors = rest;
		try {
			await action();
			this.#onchanged();
		} catch (e) {
			this.errors = { ...this.errors, [id]: errorMessage(e, 'Action failed') };
		} finally {
			const { [id]: _done, ...left } = this.busy;
			this.busy = left;
		}
	};

	/** Enrolls the drive, which starts its ripper. */
	enroll = (id: string): Promise<void> => this.#run(id, 'enroll', () => enrollDrive(id));

	/** Ignores the drive. */
	ignore = (id: string): Promise<void> => this.#run(id, 'other', () => ignoreDrive(id));

	/** Un-ignores the drive. */
	unignore = (id: string): Promise<void> => this.#run(id, 'other', () => unignoreDrive(id));
}
