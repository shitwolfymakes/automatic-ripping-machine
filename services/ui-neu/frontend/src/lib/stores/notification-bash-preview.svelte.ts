// The bash hook test panel's talk with the preview endpoint: the latest
// preview, the last test run, and whether a run is in flight.
import { previewBash, type BashPreviewRequest, type BashPreviewResult } from '$lib/api/channels';
import { failedPreview, failedRun } from '../notifications/bash-results';
import { errorMessage } from '$lib/utils/errors';

export class BashPreview {
	/** The latest preview, or null before the first one arrives. */
	preview = $state<BashPreviewResult | null>(null);
	/** The last test run's result, or null before the first run. */
	lastRun = $state<BashPreviewResult['result'] | null>(null);
	/** A test run is in flight. */
	running = $state(false);
	#timer: ReturnType<typeof setTimeout> | undefined;

	/**
	 * Previews 300 ms from now, dropping a preview already waiting. The
	 * request is built when the wait ends, so it reads the form as it is
	 * then.
	 */
	schedule = (request: () => BashPreviewRequest): void => {
		this.cancel();
		this.#timer = setTimeout(async () => {
			try {
				this.preview = await previewBash(request());
			} catch (e) {
				this.preview = failedPreview(errorMessage(e, 'preview failed'));
			}
		}, 300);
	};

	/** Drops the preview waiting to run, if there is one. */
	cancel = (): void => {
		clearTimeout(this.#timer);
	};

	/** Runs the hook now, keeping the preview it returns and its result. */
	run = async (request: BashPreviewRequest): Promise<void> => {
		this.running = true;
		try {
			const res = await previewBash(request);
			this.preview = res;
			this.lastRun = res.result ?? null;
		} catch (e) {
			this.lastRun = failedRun(errorMessage(e, 'test failed'));
		} finally {
			this.running = false;
		}
	};
}
