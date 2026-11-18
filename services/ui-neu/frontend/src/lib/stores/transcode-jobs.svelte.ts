// The transcoder page's job list for the selected tab: loading it, the
// per-tab cache, switching tabs and the poll timer.
import { fetchTranscoderJobs } from '$lib/api/transcoder';
import { getJobsCache, setJobsCache } from '$lib/stores/transcoder';
import type { TranscodeTaskView } from '$lib/types/api.gen';
import { sortTranscodeTasks } from '$lib/transcode/sort';

const emptyJobs: TranscodeTaskView[] = [];

// v3 statuses: queued | in_progress | done | failed. The UI tabs map onto
// these; "online" is implied by a successful poll (store.initialized).
const TAB_STATUS: Record<string, string | undefined> = {
	all: undefined,
	queued: 'queued',
	in_progress: 'in_progress',
	done: 'done',
	failed: 'failed'
};

export class TranscodeJobs {
	activeTab = $state('all');
	// Seed jobs from the per-tab cache so a revisit paints the last cards
	// immediately instead of dropping to a skeleton.
	jobs = $state<TranscodeTaskView[]>(getJobsCache('all') ?? emptyJobs);
	sorted = $derived([...this.jobs].sort(sortTranscodeTasks));
	loading = $state(getJobsCache('all') == null);
	error = $state<Error | null>(null);
	#timer: ReturnType<typeof setInterval> | null = null;

	load = async (showLoading = true): Promise<void> => {
		if (showLoading) this.loading = true;
		this.error = null;
		try {
			this.jobs = await fetchTranscoderJobs({ status: TAB_STATUS[this.activeTab] });
			setJobsCache(this.activeTab, this.jobs);
		} catch (e) {
			this.error = e instanceof Error ? e : new Error('Failed to load jobs');
			this.jobs = emptyJobs;
		} finally {
			this.loading = false;
		}
	};

	switchTab = (tab: string): void => {
		this.activeTab = tab;
		// Show cached cards instantly for a previously-viewed tab; only the
		// first view of a tab shows the loading skeleton.
		this.load(getJobsCache(tab) == null);
	};

	startPolling = (): void => {
		this.stopPolling();
		this.#timer = setInterval(() => this.load(false), 5000);
	};

	stopPolling = (): void => {
		if (this.#timer) {
			clearInterval(this.#timer);
			this.#timer = null;
		}
	};
}
