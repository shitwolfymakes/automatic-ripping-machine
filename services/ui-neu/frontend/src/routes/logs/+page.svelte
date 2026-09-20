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

<div class="space-y-4">
	<h1 class="text-2xl font-bold text-gray-900 dark:text-white">Logs</h1>
	<p class="text-sm text-gray-600 dark:text-gray-400">
		Browse a job's aggregated log. Select a job to view, filter, and download its log.
	</p>

	<!-- Action bar: filters (status / title-id search) -->
	<div
		class="flex flex-wrap items-center gap-3 rounded-lg border border-primary/15 bg-page px-4 py-3 dark:border-primary/20 dark:bg-primary/5"
	>
		<JobFilterBar {statusFilter} onstatusfilter={(v) => (statusFilter = v)} />
		<input
			type="text"
			bind:value={search}
			aria-label="Search jobs by title or id"
			placeholder="Search title or id..."
			class="rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-sm dark:border-primary/30 dark:bg-primary/10 dark:text-white"
		/>
	</div>

	<LoadState data={jobs} {loading} {error} transitionKey="logs-job-list">
		{#snippet loadingSlot()}
			<p class="text-sm text-gray-500">Loading jobs...</p>
		{/snippet}
		{#snippet empty()}
			<p class="text-sm text-gray-500">No jobs yet.</p>
		{/snippet}
		{#snippet ready(_jobs: JobView[])}
			<!-- data arg is the full list; we render the client-filtered `filtered` derived -->
			{#if filtered.length === 0}
				<p class="text-sm text-gray-500">No jobs match.</p>
			{:else}
				<table class="responsive-table w-full text-left text-sm">
					<thead>
						<tr class="border-b border-gray-200 dark:border-gray-700">
							<th class="px-4 py-3 font-medium">Title</th>
							<th class="px-4 py-3 font-medium">Status</th>
							<th class="px-4 py-3 font-medium">Drive</th>
							<th class="px-4 py-3 font-medium">Year</th>
						</tr>
					</thead>
					<tbody>
						{#each filtered as job (job.id)}
							<tr class="border-b border-gray-100 dark:border-gray-800">
								<td class="px-4 py-3">
									<a href="/logs/{job.id}" class="text-primary-text hover:underline dark:text-primary-text-dark">
										{job.title ?? job.id}
									</a>
								</td>
								<td class="px-4 py-3"><StatusBadge status={effectiveJobStatus(job)} /></td>
								<td class="px-4 py-3">{driveLabel(job.drive_id, $dashboard.drive_names)}</td>
								<td class="px-4 py-3">{job.year ?? '-'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		{/snippet}
	</LoadState>
</div>
