// The dashboard's All Jobs list: one server-side page of jobs, its status
// filter, its paging and the selection that rides on it.
import { SvelteSet } from 'svelte/reactivity';
import { fetchJobsPage } from '$lib/api/jobs';
import type { JobView } from '$lib/types/api.gen';

// GET /api/jobs pages server-side: the body is one page of JobView[] and
// the filtered total rides in X-Total-Count. 48 per page fills the card
// grid evenly at both two and three columns.
export const JOBS_PER_PAGE = 48;

export class DashboardJobs {
	jobs = $state<JobView[] | null>(null);
	total = $state(0);
	page = $state(1);
	readonly perPage = JOBS_PER_PAGE;
	pages = $derived(Math.max(1, Math.ceil(this.total / this.perPage)));
	error = $state<Error | null>(null);
	loading = $state(true);
	statusFilter = $state('');
	readonly selected = new SvelteSet<string>();
	allVisibleSelected = $derived(
		this.jobs !== null && this.jobs.length > 0 && this.jobs.every((j) => this.selected.has(j.id))
	);
	#request = 0;

	// Reloads the current page only (the poll and ripper events call this too).
	// Calls overlap (poll, events, paging), so only the latest request's
	// response is applied; an earlier, slower one is dropped.
	load = async (): Promise<void> => {
		const request = ++this.#request;
		if (!this.jobs) this.loading = true;
		this.error = null;
		try {
			const result = await fetchJobsPage({
				status: this.statusFilter || undefined,
				limit: this.perPage,
				offset: (this.page - 1) * this.perPage
			});
			if (request !== this.#request) return;
			this.jobs = result.jobs;
			this.total = result.total;
			// A delete (here or elsewhere) can empty the page we are on: step
			// back to the last page that still has rows.
			if (this.jobs.length === 0 && this.page > 1 && this.total > 0) {
				this.page = Math.max(1, Math.ceil(this.total / this.perPage));
				return this.load();
			}
			// Selection only ever covers rows on the visible page.
			for (const id of [...this.selected]) {
				if (!this.jobs.some((j) => j.id === id)) this.selected.delete(id);
			}
		} catch (e) {
			if (request !== this.#request) return;
			this.error = e instanceof Error ? e : new Error('Failed to load jobs');
		} finally {
			if (request === this.#request) this.loading = false;
		}
	};

	setStatusFilter = (v: string): void => {
		this.statusFilter = v;
		this.page = 1;
		this.selected.clear();
		this.load();
	};

	setPage = (p: number): void => {
		this.page = p;
		this.selected.clear();
		this.load();
	};

	toggleSelect = (jobId: string, selected: boolean): void => {
		if (selected) {
			this.selected.add(jobId);
		} else {
			this.selected.delete(jobId);
		}
	};

	toggleSelectAll = (): void => {
		if (!this.jobs) return;
		const selectAll = !this.allVisibleSelected;
		this.selected.clear();
		if (selectAll) {
			for (const j of this.jobs) this.selected.add(j.id);
		}
	};
}
