import type { SetupStep, SetupStepState, SetupView } from '$lib/types/api.gen';
import { deferSetup, fetchSetup, putSetupStep } from '$lib/api/setup';

// First-run walkthrough state shared by the /setup route, the dashboard
// checklist card and Settings > System (setup spec 2026-10-01 §5.11).

export const setupState = $state<{ view: SetupView | null; loading: boolean; error: string | null }>({
	view: null,
	loading: false,
	error: null
});

export async function loadSetup(): Promise<SetupView> {
	setupState.loading = true;
	try {
		const view = await fetchSetup();
		setupState.view = view;
		setupState.error = null;
		return view;
	} catch (e) {
		setupState.error = e instanceof Error ? e.message : 'Could not load setup';
		throw e;
	} finally {
		setupState.loading = false;
	}
}

export async function markStep(step: SetupStep, state: SetupStepState): Promise<SetupView> {
	const view = await putSetupStep(step, state);
	setupState.view = view;
	return view;
}

// "Finish later": recorded on the server, so the first-run redirect stops for
// every browser and sign-in, not just this tab. Settings > System "Run setup
// again" (restartSetup) picks it back up. Throws if the server didn't record it.
export async function finishLater(): Promise<SetupView> {
	const view = await deferSetup();
	setupState.view = view;
	return view;
}
