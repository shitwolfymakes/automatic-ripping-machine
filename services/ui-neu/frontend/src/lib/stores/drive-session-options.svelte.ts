// The Settings page's drive session options: the sessions and transcode
// presets the Drives tab's cards offer in their pickers.
import { fetchSessions } from '$lib/api/sessions';
import { fetchTranscodePresets } from '$lib/api/transcode-presets';
import type { SessionView, TranscodePresetView } from '$lib/types/api.gen';

export class DriveSessionOptions {
	sessions = $state<SessionView[]>([]);
	// Only consulted on a ripper-only deployment, where DriveCard's session
	// pickers drop encode sessions (it needs each preset's tool to tell).
	transcodePresets = $state<TranscodePresetView[]>([]);

	load = async (): Promise<void> => {
		if (this.sessions.length > 0) return;
		// Fetched together so the passthrough filter never sees sessions
		// without their presets. A preset-fetch failure is independent and
		// non-fatal: preset-backed sessions just stay hidden on a ripper-only
		// box (never mis-offered as passthrough).
		const [sessionsResult, presetsResult] = await Promise.allSettled([fetchSessions(), fetchTranscodePresets()]);
		if (presetsResult.status === 'fulfilled') this.transcodePresets = presetsResult.value;
		// non-fatal on rejection: the Start-rip session picker just stays empty
		if (sessionsResult.status === 'fulfilled') this.sessions = sessionsResult.value;
	};
}
