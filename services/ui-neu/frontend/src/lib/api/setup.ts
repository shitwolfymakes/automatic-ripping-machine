import type { DiscRouteSummary, SetupStep, SetupStepState, SetupView } from '$lib/types/api.gen';
import { get, post, put } from './client';

// First-run setup walkthrough state. The
// walkthrough writes settings through each feature's own API; these calls only
// record progress.

export function fetchSetup(): Promise<SetupView> {
	return get<SetupView>('/api/setup');
}

export function putSetupStep(step: SetupStep, state: SetupStepState): Promise<SetupView> {
	return put<SetupView>(`/api/setup/steps/${step}`, { state });
}

export function completeSetup(): Promise<SetupView> {
	return post<SetupView>('/api/setup/complete');
}

export function restartSetup(): Promise<SetupView> {
	return post<SetupView>('/api/setup/restart');
}

/** "Finish later": stop the first-run redirect server-wide (every browser, every sign-in). */
export function deferSetup(): Promise<SetupView> {
	return post<SetupView>('/api/setup/defer');
}

export function dismissSetupChecklist(): Promise<SetupView> {
	return post<SetupView>('/api/setup/checklist/dismiss');
}

export function fetchDiscRoutes(): Promise<DiscRouteSummary[]> {
	return get<DiscRouteSummary[]>('/api/setup/disc-routes');
}
