<script lang="ts">
	import { onMount } from 'svelte';
	import type { JobView } from '$lib/types/api.gen';
	import JobFilterBar from '$lib/components/JobFilterBar.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import LogJobRow from '$lib/components/logs/LogJobRow.svelte';
	import { filterLogJobs, logCountText, orderByLastModified } from '$lib/logs/list';
	import { LogListing } from '$lib/stores/log-listing.svelte';

	const COLUMNS = ['Title', 'Status', 'Type', 'Disc', 'Drive', 'Last modified'];

	const listing = new LogListing();
	let statusFilter = $state('');
	let search = $state('');

	const ordered = $derived(orderByLastModified(listing.jobs, listing.modified));
	const filtered = $derived(filterLogJobs(ordered, statusFilter, search));
	const countText = $derived(logCountText(filtered.length, listing.total, !!(statusFilter || search)));

	onMount(() => {
		listing.load();
	});
</script>

<svelte:head>
	<title>ARM - Logs</title>
</svelte:head>

<!-- One panel in the dashboard All Jobs style. Plain divs inside, not
     header/.panel: the winamp-97 scheme styles those as the app titlebar. -->
<section class="list-panel logs-panel">
	<div class="list-panel-header">
		<h1 class="list-panel-title">Job logs</h1>
		<span class="list-panel-count">{countText}</span>
		<JobFilterBar {statusFilter} onstatusfilter={(v) => (statusFilter = v)} />
		<span class="flex-1"></span>
		<input
			type="text"
			bind:value={search}
			aria-label="Search jobs by title or id"
			placeholder="Search title or id"
			class="field-control logs-panel-search"
		/>
	</div>

	<div class="list-panel-body">
		<LoadState data={listing.jobs} loading={listing.loading} error={listing.error}>
			{#snippet loadingSlot()}
				<p class="logs-panel-muted logs-panel-message">Loading jobs...</p>
			{/snippet}
			{#snippet empty()}
				<p class="logs-panel-muted logs-panel-message">No jobs yet.</p>
			{/snippet}
			{#snippet ready(_jobs: JobView[])}
				<!-- data arg is the full list; we render the ordered, client-filtered `filtered` derived -->
				{#if filtered.length === 0}
					<p class="logs-panel-muted logs-panel-message">No jobs match.</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="table responsive-table">
							<thead>
								<tr>
									{#each COLUMNS as col (col)}
										<th class="table-header">{col}</th>
									{/each}
								</tr>
							</thead>
							<tbody>
								{#each filtered as job (job.id)}
									<LogJobRow {job} logAt={listing.modified.get(job.id)} />
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			{/snippet}
		</LoadState>
	</div>
</section>

<style>
	.logs-panel-search {
		width: 14rem;
		max-width: 100%;
		min-height: auto;
	}
	.logs-panel-message {
		padding: 2rem 1rem;
		text-align: center;
	}
	.logs-panel-muted {
		color: var(--color-text-muted);
	}
</style>
