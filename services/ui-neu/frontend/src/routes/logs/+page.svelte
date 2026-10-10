<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchJobs } from '$lib/api/jobs';
	import type { JobView } from '$lib/types/api.gen';
	import JobFilterBar from '$lib/components/JobFilterBar.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import { effectiveJobStatus } from '$lib/utils/job-status';
	import { driveLabel } from '$lib/utils/drive-name';
	import { dashboard } from '$lib/stores/dashboard';

	let jobs = $state<JobView[]>([]);
	let loading = $state(true);
	let error = $state<Error | null>(null);
	let statusFilter = $state('');
	let search = $state('');

	const filtered = $derived(
		jobs.filter((j) => {
			if (statusFilter && j.status !== statusFilter) return false;
			if (search) {
				const q = search.toLowerCase();
				const hay = `${j.title ?? ''} ${j.id}`.toLowerCase();
				if (!hay.includes(q)) return false;
			}
			return true;
		})
	);

	onMount(async () => {
		try {
			jobs = await fetchJobs();
		} catch (e) {
			error = e instanceof Error ? e : new Error(String(e));
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head>
	<title>ARM - Logs</title>
</svelte:head>

<div class="stack">
	<h1 class="page-title">Logs</h1>
	<p class="logs-page-hint">
		Browse a job's aggregated log. Select a job to view, filter, and download its log.
	</p>

	<!-- Action bar: filters (status / title-id search) -->
	<div class="cluster panel-section logs-page-action-bar">
		<JobFilterBar {statusFilter} onstatusfilter={(v) => (statusFilter = v)} />
		<input
			type="text"
			bind:value={search}
			aria-label="Search jobs by title or id"
			placeholder="Search title or id..."
			class="field-control logs-page-search"
		/>
	</div>

	<LoadState data={jobs} {loading} {error} transitionKey="logs-job-list">
		{#snippet loadingSlot()}
			<p class="logs-page-muted">Loading jobs...</p>
		{/snippet}
		{#snippet empty()}
			<p class="logs-page-muted">No jobs yet.</p>
		{/snippet}
		{#snippet ready(_jobs: JobView[])}
			<!-- data arg is the full list; we render the client-filtered `filtered` derived -->
			{#if filtered.length === 0}
				<p class="logs-page-muted">No jobs match.</p>
			{:else}
				<table class="table responsive-table logs-page-table">
					<thead>
						<tr>
							<th class="table-header logs-page-table-header">Title</th>
							<th class="table-header logs-page-table-header">Status</th>
							<th class="table-header logs-page-table-header">Drive</th>
							<th class="table-header logs-page-table-header">Year</th>
						</tr>
					</thead>
					<tbody>
						{#each filtered as job (job.id)}
							<tr class="table-row">
								<td class="table-cell">
									<a href="/logs/{job.id}" class="btn btn-link">
										{job.title ?? job.id}
									</a>
								</td>
								<td class="table-cell"><StatusBadge status={effectiveJobStatus(job)} /></td>
								<td class="table-cell">{driveLabel(job.drive_id, $dashboard.drive_names)}</td>
								<td class="table-cell">{job.year ?? '-'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		{/snippet}
	</LoadState>
</div>

<style>
	.logs-page-hint { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
	.logs-page-muted { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.logs-page-search { width: auto; min-height: auto; }
	/* original was px-4 py-3 gap-3 (1rem/0.75rem/0.75rem), not
	   panel-section's own uniform 1rem padding or cluster's 0.5rem gap */
	.logs-page-action-bar { gap: 0.75rem; padding: 0.75rem 1rem; }
	/* the original header row was plain (px-4 py-3 font-medium, no
	   uppercase/background/border) - table-header's own styling is tuned
	   for the dashboard/jobs/job-detail tables, which this page's original
	   markup never matched, so it is overridden back to the plain look */
	.logs-page-table-header { padding: 0.75rem 1rem; text-align: left; font-size: 0.875rem; font-weight: 500; letter-spacing: normal; text-transform: none; color: var(--color-text); background: none; }
	.logs-page-table .table-cell { padding: 0.75rem 1rem; }
</style>
