// The output paths a session would give a job, from the same resolver the
// apply path uses, or the problem to show when a path cannot be resolved; a
// fetch's answer is dropped once it is cancelled.
import { fetchNamingPreview } from '$lib/api/jobs';
import { explainNamingProblem } from '$lib/utils/naming-problem';
import type { JobNamingPreviewResponse } from '$lib/types/api.gen';
import { errorMessage } from '$lib/utils/errors';

export class NamingPreview {
	/** The output paths the chosen session would give the job. */
	preview = $state<JobNamingPreviewResponse | null>(null);
	/** Whether a preview fetch is in flight. */
	loading = $state(false);
	/** The sentence explaining why the paths could not be resolved. */
	problem = $state<string | null>(null);

	/** Clears the last answer, then fetches this job's preview for the
	 *  session, and does nothing at all when there is no session. Returns a
	 *  function that cancels this fetch: once called, the fetch's answer and
	 *  its end of loading are dropped. */
	load = (jobId: string, sessionId: string): (() => void) => {
		this.preview = null;
		this.problem = null;
		if (!sessionId) return () => {};
		this.loading = true;
		let cancelled = false;
		fetchNamingPreview(jobId, sessionId)
			.then((p) => {
				if (!cancelled) this.preview = p;
			})
			.catch((e) => {
				if (cancelled) return;
				this.problem = explainNamingProblem(errorMessage(e, 'Preview failed'));
			})
			.finally(() => {
				if (!cancelled) this.loading = false;
			});
		return () => {
			cancelled = true;
		};
	};
}
