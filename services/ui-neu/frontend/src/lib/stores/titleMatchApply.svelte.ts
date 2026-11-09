// The title search's apply: the title guard, the three ways a match is applied,
// and the feedback line tagged with the row and the result list it is for.
import type { JobView, MetadataCandidate, ResolveResponse } from '$lib/types/api.gen';
import { resolveJob, updateJobTitle } from '$lib/api/jobs';
import { titleMatchBody, titleResolveBody, type TitleApplyValues } from '$lib/utils/job-resolve';
import { isSeriesKind } from '$lib/utils/match';

export type FeedbackAt = { row: number; list: number };
export type TitleFeedback = { type: 'success' | 'error'; message: string } & FeedbackAt;

export interface TitleApplyPlan {
	/**
	 * The job, read each time the apply needs it. The plain resolve reads its
	 * id and manual poster again after the resolve's await, when the job may
	 * have changed.
	 */
	job: () => JobView;
	/** The match Use was clicked on. */
	candidate: MetadataCandidate;
	/** The values applied. */
	values: TitleApplyValues;
	/** The poster was typed while editing. */
	posterIsManual: boolean;
	/** The row and the result list the apply started on. */
	at: FeedbackAt;
}

export class TitleMatchApply {
	/** An apply is in flight. */
	applying = $state(false);
	/**
	 * The outcome line of the last apply. Tagged with the row and result list a
	 * Use started on, so a result that lands after the operator moved on is not
	 * shown under another row.
	 */
	feedback = $state<TitleFeedback | null>(null);

	/**
	 * Applies the match, then calls `done` with the resolve response, if a
	 * resolve ran.
	 */
	apply = async (plan: TitleApplyPlan, done: (resolved: ResolveResponse | undefined) => void): Promise<void> => {
		const { at, candidate: c, values } = plan;
		if (!values.title) {
			this.feedback = { type: 'error', message: 'Title is required', ...at };
			return;
		}
		this.applying = true;
		this.feedback = null;
		// The candidate's ids name a title of its own kind; after a type edit they don't apply.
		const idsApply = isSeriesKind(c.kind) === values.isSeries;
		let resolved: ResolveResponse | undefined;
		try {
			if (plan.job().actions.can_resolve && idsApply && c.provider) {
				resolved = await resolveJob(plan.job().id, titleMatchBody(c, values, plan.posterIsManual));
				this.feedback = { type: 'success', message: 'Identified', ...at };
			} else if (plan.job().actions.can_resolve) {
				resolved = await resolveJob(plan.job().id, titleResolveBody(values));
				let message = 'Identified';
				if (values.poster !== (plan.job().poster_url_manual ?? null)) {
					try {
						await updateJobTitle(plan.job().id, { poster_url_manual: values.poster });
					} catch {
						message = 'Identified; poster not saved';
					}
				}
				this.feedback = { type: 'success', message, ...at };
			} else {
				// Non-resolvable status (created/ripping/failed/abandoned): poster only.
				await updateJobTitle(plan.job().id, { poster_url_manual: values.poster });
				this.feedback = { type: 'success', message: 'Poster updated', ...at };
			}
			done(resolved);
		} catch (e) {
			this.feedback = { type: 'error', message: e instanceof Error ? e.message : 'Apply failed', ...at };
		} finally {
			this.applying = false;
		}
	};
}
