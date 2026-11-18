// The review card's job actions: cancel, delete, start the rip and pause
// the countdown, with each one's busy flag, the delete confirmation and
// the error banner's message.
import type { JobView } from '$lib/types/api.gen';
import { abandonJob, deleteJob, startWaitingJob, pauseWaitingJob, resolveJob } from '$lib/api/jobs';
import { cancelIsoRip } from '$lib/api/iso';
import { errorMessage } from '$lib/utils/errors';

/** What the card does once an action lands. */
interface JobActionCallbacks {
	/** The card leaves the dashboard. */
	dismiss: () => void;
	/** The dashboard reloads. */
	refresh: () => void;
}

export class DiscReviewJobActions {
	cancelling = $state(false);
	deleting = $state(false);
	starting = $state(false);
	pauseBusy = $state(false);
	confirmDelete = $state(false);
	errorMessage = $state<string | null>(null);

	readonly #done: JobActionCallbacks;

	constructor(done: JobActionCallbacks) {
		this.#done = done;
	}

	cancel = async (job: JobView | undefined, isoName: string | null): Promise<void> => {
		if (!job) return;
		this.cancelling = true;
		this.errorMessage = null;
		try {
			if (isoName && job.drive_id) {
				await cancelIsoRip(job.drive_id);
			} else {
				await abandonJob(job.id);
			}
			this.#done.dismiss();
			this.#done.refresh();
		} catch (e) {
			this.errorMessage = errorMessage(e, 'Failed to cancel the job');
		} finally {
			this.cancelling = false;
		}
	};

	// A rip that already finished cannot be abandoned; the backend offers
	// delete instead. Raw files stay on disk, as on the job page.
	remove = async (job: JobView | undefined): Promise<void> => {
		if (!job) return;
		this.confirmDelete = false;
		this.deleting = true;
		this.errorMessage = null;
		try {
			await deleteJob(job.id);
			this.#done.dismiss();
			this.#done.refresh();
		} catch (e) {
			this.errorMessage = errorMessage(e, 'Failed to delete the job');
		} finally {
			this.deleting = false;
		}
	};

	// Action-row "Start rip": save + start. Resolving the job's current identity
	// (title/year/disc, preferring the freshly-loaded detail) is the save — it
	// also unblocks the parked ripper for an awaiting_user_id disc. For an
	// awaiting_review disc the rip is held by the countdown, so additionally skip
	// it via rip-start-review. Then dismiss the card; the disc is on its way.
	startRip = async (
		job: JobView | undefined,
		detailJob: JobView | undefined,
		isReviewGate: () => boolean
	): Promise<void> => {
		if (!job) return;
		const j = detailJob ?? job;
		const startTitle = (j.title ?? '').trim();
		if (!startTitle) {
			this.errorMessage = 'A title is required to start. Open Info or Search to set one.';
			return;
		}
		this.starting = true;
		this.errorMessage = null;
		try {
			await resolveJob(job.id, {
				title: startTitle,
				year: j.year ?? null,
				disc_number: j.disc_number ?? null,
				disc_total: j.disc_total ?? null
			});
			if (isReviewGate()) {
				await startWaitingJob(job.id);
			}
			this.#done.dismiss();
			this.#done.refresh();
		} catch (e) {
			this.errorMessage = errorMessage(e, 'Failed to start the rip');
		} finally {
			this.starting = false;
		}
	};

	setPaused = async (job: JobView | undefined, paused: boolean): Promise<void> => {
		if (!job) return;
		this.pauseBusy = true;
		this.errorMessage = null;
		try {
			await pauseWaitingJob(job.id, paused);
			this.#done.refresh();
		} catch (e) {
			this.errorMessage = errorMessage(e, 'Failed to update pause');
		} finally {
			this.pauseBusy = false;
		}
	};

	dismissError = (): void => {
		this.errorMessage = null;
	};
}
