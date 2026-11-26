import type { StepCommitResult } from '$lib/setup/steps';

/** What the stubbed step reports: its commit() and the setBlocked it was given. */
export const stubState: {
	commit: () => Promise<StepCommitResult>;
	setBlocked: ((reason: string | null) => void) | undefined;
} = {
	commit: async () => 'done',
	setBlocked: undefined
};
