// What the review card loads for its job: the job detail, each track's
// generated file name, and the session names.
import { SvelteMap } from 'svelte/reactivity';
import { fetchJob, fetchNamingPreview } from '$lib/api/jobs';
import { fetchSessions } from '$lib/api/sessions';
import type { JobDetailView, SessionView } from '$lib/types/api.gen';

export class DiscReviewData {
	detail = $state<JobDetailView | null>(null);
	// The generated file name per track (the applied session's naming), for the
	// Info table's Episode column; empty until a session names the tracks.
	fileNames = $state<Map<string, string>>(new SvelteMap());
	initialLoading = $state(true);
	sessions = $state<SessionView[]>([]);
	sessionNames = $derived(new SvelteMap(this.sessions.map((s) => [s.id, s.name])));
	readonly #jobId: () => string | undefined;
	// Each load takes a number; only the newest may write. Job events and a tick's
	// refresh overlap, and an older answer arriving last must not put stale tracks back.
	#latestLoad = 0;

	constructor(jobId: () => string | undefined) {
		this.#jobId = jobId;
	}

	loadDetail = async (): Promise<void> => {
		const id = this.#jobId();
		if (!id) return;
		const load = ++this.#latestLoad;
		try {
			const detail = await fetchJob(id);
			if (load !== this.#latestLoad) return;
			this.detail = detail;
		} catch {
			// A failed refresh keeps the last detail (and its tracks) on the card.
		} finally {
			this.initialLoading = false;
		}
		try {
			const preview = await fetchNamingPreview(id);
			if (load !== this.#latestLoad) return;
			this.fileNames = new SvelteMap((preview.items ?? []).map((i) => [i.track_id, i.output_name]));
		} catch {
			// No session routed yet (409) or a nicety that failed: the table shows the episode instead.
			if (load === this.#latestLoad) this.fileNames = new SvelteMap();
		}
	};

	loadSessions = async (): Promise<void> => {
		try {
			this.sessions = await fetchSessions();
		} catch {
			this.sessions = [];
		}
	};
}
