// The Settings page's "Run setup again" action: the busy flag and the
// restart request that sends the user back to the setup wizard.
import { goto } from '$app/navigation';
import { restartSetup } from '$lib/api/setup';

export class SetupRestart {
	running = $state(false);

	run = async (): Promise<void> => {
		this.running = true;
		try {
			await restartSetup();
			goto('/setup/system');
		} finally {
			this.running = false;
		}
	};
}
