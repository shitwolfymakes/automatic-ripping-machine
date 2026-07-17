import type { SessionView, RipPresetView, TranscodePresetView, MediaType } from '$lib/types/api.gen';
import { fetchSessions } from '$lib/api/sessions';
import { fetchRipPresets } from '$lib/api/ripPresets';
import { fetchTranscodePresets } from '$lib/api/transcodePresets';

export type JoinedSession = SessionView & {
	ripPreset: RipPresetView | undefined;
	transcodePreset: TranscodePresetView | undefined;
};

const MEDIA_TYPES: MediaType[] = ['movie', 'tv', 'music', 'data', 'iso'];

export function createSessionsData() {
	let rawSessions = $state<SessionView[]>([]);
	let rips = $state<RipPresetView[]>([]);
	let tcs = $state<TranscodePresetView[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);

	const ripById = $derived(new Map(rips.map((p) => [p.id, p])));
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
			error = e instanceof Error ? e.message : 'Failed to load sessions';
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
		typeCounts: () => {
			const counts: Record<string, number> = { all: rawSessions.length };
			for (const m of MEDIA_TYPES) counts[m] = rawSessions.filter((s) => s.media_type === m).length;
			return counts as Record<MediaType | 'all', number>;
		},
		loading: () => loading,
		error: () => error,
		load
	};
}
