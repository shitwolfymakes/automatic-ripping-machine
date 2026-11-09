// The review card's text, built from the job's state.

/** The job states that decide the review card's status label. */
export interface StatusLabelFlags {
	/** The disc was ripped before. */
	previouslyRipped: boolean;
	/** An identity suggestion is waiting to be confirmed. */
	suggestion: boolean;
	/** The job is at the review gate. */
	reviewGate: boolean;
	/** The rip is done and a session can be applied. */
	postRip: boolean;
}

/** The status bar's label; the first matching state wins. */
export function reviewStatusLabel(flags: StatusLabelFlags): string {
	if (flags.previouslyRipped) return 'Already ripped: Rip again or Discard';
	if (flags.suggestion) return 'Confirm the title: use it or search';
	if (flags.reviewGate) return 'Ready: Review & Start';
	if (flags.postRip) return 'Ripped: Apply Session';
	return 'Awaiting Review';
}
