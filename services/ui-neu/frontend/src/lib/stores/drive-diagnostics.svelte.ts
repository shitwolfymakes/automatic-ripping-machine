// The Settings page's drive diagnostics: the last result, the running flag,
// the error, the disclosure state and the time of the last run.
import { SvelteDate } from 'svelte/reactivity';
import { fetchDriveDiagnostic } from '$lib/api/drives';
import type { DriveDiagnosticResponse } from '$lib/types/api.gen';
import { errorMessage } from '$lib/utils/errors';

export class DriveDiagnostics {
	running = $state(false);
	result = $state<DriveDiagnosticResponse | null>(null);
	error = $state<string | null>(null);
	open = $state(false);
	lastRun = $state<string | null>(null);

	run = async (): Promise<void> => {
		if (this.running) return;
		this.running = true;
		this.error = null;
		try {
			this.result = await fetchDriveDiagnostic();
			// SvelteDate because lint bars a plain Date in a .svelte.ts module
			// (svelte/prefer-svelte-reactivity); the string is the same.
			this.lastRun = new SvelteDate(Date.now()).toLocaleTimeString();
			this.open = true;
		} catch (e) {
			this.error = errorMessage(e, 'Diagnostic failed');
			this.result = null;
		} finally {
			this.running = false;
		}
	};

	toggle = (): void => {
		this.open = !this.open;
	};
}
