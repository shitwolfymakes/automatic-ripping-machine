// The Settings page's "Run setup again" action: the busy flag, the restart
// request that sends the user back to the setup wizard, and the error line
// when the request fails.
import { goto } from '$app/navigation';
import { restartSetup } from '$lib/api/setup';
import { errorMessage } from '$lib/utils/errors';
import { TimedFeedback } from './timed-feedback.svelte';

export class SetupRestart {
	running = $state(false);
	/** The failed request's error, held until the next run. */
	readonly feedback = new TimedFeedback();

	run = async (): Promise<void> => {
		this.running = true;
		this.feedback.clear();
		try {
			await restartSetup();
			goto('/setup/system');
		} catch (e) {
			this.feedback.hold('error', errorMessage(e, 'Could not restart setup'));
		} finally {
			this.running = false;
		}
	};
}
