// The music search's release apply: the two confirmation gates (the total
// mismatch, then the title mapping), the resolve and then the PATCH, and the
// feedback line.
import { resolveJob, patchJob } from '$lib/api/jobs';
import type { ResolveBody } from '$lib/jobs/resolve';
import type { JobUpdateRequest } from '$lib/types/api.gen';
import { errorMessage } from '$lib/utils/errors';

export type ApplyFeedback = { type: 'success' | 'error'; message: string };

export interface ReleaseApplyPlan {
	/** The job the release is applied to. */
	jobId: string;
	/** The disc's total length is known and differs from the release's. */
	totalMismatch: boolean;
	/**
	 * Release titles will be written onto disc tracks, so the mapping is
	 * confirmed first.
	 */
	needsMapping: boolean;
	/** The body of the resolve request. */
	resolveBody: ResolveBody;
	/**
	 * The body of the PATCH, or null for none. Called only after the resolve
	 * succeeds, since it reads the release and the mapping open at that time
	 * (#595).
	 */
	patchBody: () => JobUpdateRequest | null;
}

export class MusicReleaseApply {
	/** An apply is in flight. */
	applying = $state(false);
	/** The outcome line of the last apply or detail load. */
	feedback = $state<ApplyFeedback | null>(null);
	/** The total-mismatch gate is open. */
	confirmMismatch = $state(false);
	/** The title-mapping gate is open. */
	mappingPreview = $state(false);

	#mismatchConfirmed = $state(false);
	#mappingConfirmed = $state(false);

	/** Closes both gates and forgets both confirmations. */
	reset = (): void => {
		this.confirmMismatch = false;
		this.#mismatchConfirmed = false;
		this.mappingPreview = false;
		this.#mappingConfirmed = false;
	};

	/** Confirms the total mismatch and closes its gate. */
	acceptMismatch = (): void => {
		this.#mismatchConfirmed = true;
		this.confirmMismatch = false;
	};

	/** Confirms the title mapping and closes its gate. */
	acceptMapping = (): void => {
		this.#mappingConfirmed = true;
		this.mappingPreview = false;
	};

	readonly #savePatch = async (jobId: string, body: JobUpdateRequest | null): Promise<void> => {
		if (!body) return;
		try {
			await patchJob(jobId, body);
		} catch {
			this.feedback = { type: 'success', message: 'Identified; cover/track titles not saved' };
		}
	};

	/** Applies the release, stopping at each gate that is not yet confirmed. */
	apply = async (plan: ReleaseApplyPlan, onapply?: () => void): Promise<void> => {
		if (plan.totalMismatch && !this.#mismatchConfirmed) {
			this.confirmMismatch = true;
			return;
		}
		if (plan.needsMapping && !this.#mappingConfirmed) {
			this.mappingPreview = true;
			return;
		}
		this.applying = true;
		this.feedback = null;
		try {
			await resolveJob(plan.jobId, plan.resolveBody);
			this.feedback = { type: 'success', message: 'Release applied' };
			await this.#savePatch(plan.jobId, plan.patchBody());
			onapply?.();
		} catch (e) {
			this.feedback = { type: 'error', message: errorMessage(e, 'Apply failed') };
		} finally {
			this.applying = false;
		}
	};
}
