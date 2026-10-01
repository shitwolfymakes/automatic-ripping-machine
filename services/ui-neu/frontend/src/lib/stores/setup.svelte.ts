import type { SetupStep, SetupStepState, SetupView } from '$lib/types/api.gen';
import { fetchSetup, putSetupStep } from '$lib/api/setup';

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

// "Finish later": stop the first-run redirect for the rest of this browser
// session so the operator can use the app; the next sign-in resumes setup.
export const FINISH_LATER_KEY = 'arm_setup_finish_later';

export function finishLater(): void {
	try {
		sessionStorage.setItem(FINISH_LATER_KEY, '1');
	} catch {
		/* storage blocked: the redirect simply comes back */
	}
}

export function clearFinishLater(): void {
	try {
		sessionStorage.removeItem(FINISH_LATER_KEY);
	} catch {
		/* ignore */
	}
}

export function finishLaterActive(): boolean {
	try {
		return sessionStorage.getItem(FINISH_LATER_KEY) !== null;
	} catch {
		return false;
	}
}
