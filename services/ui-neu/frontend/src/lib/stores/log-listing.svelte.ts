// The logs page's list: every job, the log index's modified times, the
// loading flag and the load error.
import { SvelteMap } from 'svelte/reactivity';
import { fetchAllJobs } from '$lib/api/jobs';
import { fetchJobLogIndex } from '$lib/api/logs';
import type { JobView } from '$lib/types/api.gen';
import { indexLogFiles } from '$lib/logs/list';

export class LogListing {
	jobs = $state<JobView[]>([]);
	total = $state(0);
	// job id -> the log file's modified_at; a job missing here has no log yet
	modified = $state<Map<string, string>>(new SvelteMap());
	loading = $state(true);
	error = $state<Error | null>(null);

	load = async (): Promise<void> => {
		// Every job, not one page: the list sorts by log modified time and
		// filters client-side, which a server page would cut short. The log
		// index is best-effort: if it fails the jobs still list, each showing
		// "No log yet".
		const [page, index] = await Promise.allSettled([fetchAllJobs(), fetchJobLogIndex()]);
		if (page.status === 'fulfilled') {
			this.jobs = page.value.jobs;
			this.total = page.value.total;
		} else {
			const e = page.reason;
			this.error = e instanceof Error ? e : new Error(String(e));
		}
		if (index.status === 'fulfilled') {
			this.modified = indexLogFiles(index.value);
		}
		this.loading = false;
	};
}
