import { errorMessage } from '$lib/utils/errors';
// A preset form's save: whether one is in flight, and the last one's
// error line.
export class PresetSave {
	/** A save is in flight. */
	submitting = $state(false);
	/** The last save's error message; null while one runs or after a success. */
	error = $state<string | null>(null);

	/**
	 * Runs the save and passes its result to `onsaved`. A failure keeps
	 * its message, or "Save failed" for something other than an Error.
	 */
	run = async <T>(save: () => Promise<T>, onsaved: (result: T) => void): Promise<void> => {
		this.submitting = true;
		this.error = null;
		try {
			onsaved(await save());
		} catch (e) {
			this.error = errorMessage(e, 'Save failed');
		} finally {
			this.submitting = false;
		}
	};
}
