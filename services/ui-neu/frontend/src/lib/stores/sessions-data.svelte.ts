import type { SessionView, RipPresetView, TranscodePresetView } from '$lib/types/api.gen';
import { countByMediaType } from '$lib/sessions/sessions';
import { fetchSessions } from '$lib/api/sessions';
import { fetchRipPresets } from '$lib/api/rip-presets';
import { fetchTranscodePresets } from '$lib/api/transcode-presets';
import { errorMessage } from '$lib/utils/errors';

export type JoinedSession = SessionView & {
	ripPreset: RipPresetView | undefined;
	transcodePreset: TranscodePresetView | undefined;
};

export function createSessionsData() {
	let rawSessions = $state<SessionView[]>([]);
	let rips = $state<RipPresetView[]>([]);
	let tcs = $state<TranscodePresetView[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);

	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- lookup map rebuilt by $derived, never mutated
	const ripById = $derived(new Map(rips.map((p) => [p.id, p])));
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- lookup map rebuilt by $derived, never mutated
	const tcById = $derived(new Map(tcs.map((p) => [p.id, p])));

	const joined = $derived<JoinedSession[]>(
		rawSessions.map((s) => ({
			...s,
			ripPreset: ripById.get(s.rip_preset_id),
			transcodePreset: s.transcode_preset_id ? tcById.get(s.transcode_preset_id) : undefined
		}))
	);

	async function load() {
		loading = true;
		error = null;
		try {
			const [s, r, t] = await Promise.all([fetchSessions(), fetchRipPresets(), fetchTranscodePresets()]);
			rawSessions = s;
			rips = r;
			tcs = t;
		} catch (e) {
			error = errorMessage(e, 'Failed to load sessions');
		} finally {
			loading = false;
		}
	}

	return {
		sessions: () => joined,
		ripPresets: () => rips,
		transcodePresets: () => tcs,
		ripUsage: (id: string) => rawSessions.filter((s) => s.rip_preset_id === id).length,
		transcodeUsage: (id: string) => rawSessions.filter((s) => s.transcode_preset_id === id).length,
		typeCounts: () => countByMediaType(rawSessions),
		loading: () => loading,
		error: () => error,
		load
	};
}
