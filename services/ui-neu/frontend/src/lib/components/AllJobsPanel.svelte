<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import { slide } from 'svelte/transition';
	import { get } from 'svelte/store';
	import { bulkDeleteJobs } from '$lib/api/jobs';
	import { bulkDeleteFeedback, type BulkFeedback } from '$lib/utils/bulk-delete-feedback';
	import type { DashboardJobs } from '$lib/stores/dashboardJobs.svelte';
	import JobCard from '$lib/components/JobCard.svelte';
	import JobRow from '$lib/components/JobRow.svelte';
	import JobFilterBar from '$lib/components/JobFilterBar.svelte';
	import BulkActionsMenu from '$lib/components/BulkActionsMenu.svelte';
	import JobPagination from '$lib/components/JobPagination.svelte';
	import CloseButton from '$lib/components/CloseButton.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import { uiPrefs } from '$lib/stores/uiPrefs';
	import { isAdmin } from '$lib/stores/auth';

	let { jobs: jobsList }: { jobs: DashboardJobs } = $props();

	// Opens with the Settings > Interface default; toggling here is for this
	// visit only and does not change that default.
	let viewMode = $state<'card' | 'table'>(get(uiPrefs).dashboardView);

	// Gear menu
	let bulkBusy = $state(false);
	let bulkFeedback = $state<BulkFeedback | null>(null);

	async function handleBulkAction(
		action: 'delete' | 'purge',
		params: { job_ids?: string[]; status?: string },
		description: string
	) {
		if (!confirm(`Are you sure you want to ${description}?`)) return;
		bulkBusy = true;
		bulkFeedback = null;
		try {
			// v3 only exposes bulk delete; purge has no endpoint and the menu
			// routes both actions here.
			const result = await bulkDeleteJobs(params);
			bulkFeedback = bulkDeleteFeedback(result);
			jobsList.selected.clear();
			await jobsList.load();
		} catch (e) {
			bulkFeedback = {
				type: 'error',
				message: errorMessage(e, 'Bulk action failed')
			};
		} finally {
			bulkBusy = false;
		}
	}

	function deleteSelected() {
		const ids = [...jobsList.selected];
		handleBulkAction('delete', { job_ids: ids }, `delete ${ids.length} selected job(s)`);
	}

	// Sortable columns (v3 JobRow renders Title / Year / Rip / Transcode / Type / Disc).
	const columns = [
		{ key: 'title', label: 'Title' },
		{ key: 'year', label: 'Year' },
		{ key: 'status', label: 'Rip' },
		{ key: 'transcode', label: 'Transcode' },
		{ key: 'video_type', label: 'Type' },
		{ key: 'disctype', label: 'Disc' }
	];
</script>

<!-- All Jobs: one panel (header, selection bar, list, footer). Plain divs
     inside, not header/footer/.panel: the winamp-97 scheme styles those
     as the app titlebar and would rebuild the old two-row layout. -->
<section id="all-jobs" class="list-panel">
	<div class="list-panel-header">
		<h2 class="list-panel-title">All Jobs</h2>
		<span class="list-panel-count">{jobsList.total} {jobsList.total === 1 ? 'job' : 'jobs'}</span>
		<JobFilterBar statusFilter={jobsList.statusFilter} onstatusfilter={jobsList.setStatusFilter} />
		<span class="flex-1"></span>
		<div class="dashboard-view-group">
			<button
				onclick={() => (viewMode = 'card')}
				class="btn btn-sm dashboard-view-toggle"
				aria-pressed={viewMode === 'card'}>Cards</button
			>
			<button
				onclick={() => (viewMode = 'table')}
				class="btn btn-sm dashboard-view-toggle"
				aria-pressed={viewMode === 'table'}>Table</button
			>
		</div>
		{#if $isAdmin}
			<BulkActionsMenu selectedJobs={jobsList.selected} {bulkBusy} onaction={handleBulkAction} />
		{/if}
	</div>

	{#if $isAdmin && jobsList.selected.size > 0}
		<div class="dashboard-jobs-selection" data-testid="jobs-selection-bar" transition:slide={{ duration: 120 }}>
			<span class="dashboard-jobs-selection-count">{jobsList.selected.size} selected</span>
			<span class="dashboard-jobs-selection-divider"></span>
			<button onclick={deleteSelected} disabled={bulkBusy} class="btn btn-sm btn-danger">Delete selected</button>
			<span class="flex-1"></span>
			<button onclick={() => jobsList.selected.clear()} class="btn btn-link dashboard-jobs-selection-clear"
				>Clear selection</button
			>
		</div>
	{/if}

	{#if bulkFeedback}
		<div class="dashboard-jobs-feedback" data-tone={bulkFeedback.type}>
			<span>{bulkFeedback.message}</span>
			<CloseButton onclick={() => (bulkFeedback = null)} label="Dismiss" />
		</div>
	{/if}

	<div class="list-panel-body">
		<LoadState data={jobsList.jobs} loading={jobsList.loading} error={jobsList.error}>
			{#snippet loadingSlot()}
				{#if viewMode === 'table'}
					<div class="overflow-x-auto">
						<table class="table responsive-table">
							<thead>
								<tr>
									<th class="table-header w-8"></th>
									{#each columns as col (col.key)}
										<th class="table-header">{col.label}</th>
									{/each}
								</tr>
							</thead>
							<tbody>
								{#each { length: 12 } as _, i (i)}
									<JobRow />
								{/each}
							</tbody>
						</table>
					</div>
				{:else}
					<div class="dashboard-jobs-grid grid md:grid-cols-2 xl:grid-cols-3">
						{#each { length: 6 } as _, i (i)}
							<JobCard />
						{/each}
					</div>
				{/if}
			{/snippet}
			{#snippet ready(list)}
				{#if viewMode === 'table'}
					<div class="overflow-x-auto">
						<table class="table responsive-table">
							<thead>
								<tr>
									<th class="table-header w-8">
										{#if $isAdmin}
											<input
												type="checkbox"
												checked={jobsList.allVisibleSelected}
												onchange={jobsList.toggleSelectAll}
												class="dashboard-select-all-checkbox"
											/>
										{/if}
									</th>
									{#each columns as col (col.key)}
										<th class="table-header">{col.label}</th>
									{/each}
								</tr>
							</thead>
							<tbody>
								{#each list as job (job.id)}
									<JobRow
										{job}
										selected={jobsList.selected.has(job.id)}
										onselect={jobsList.toggleSelect}
										showSelect={$isAdmin}
									/>
								{/each}
							</tbody>
						</table>
					</div>
				{:else}
					<div class="dashboard-jobs-grid grid md:grid-cols-2 xl:grid-cols-3">
						{#each list as job (job.id)}
							<JobCard {job} />
						{/each}
					</div>
				{/if}
			{/snippet}
			{#snippet empty()}
				<p class="dashboard-empty-jobs">No jobs found.</p>
			{/snippet}
		</LoadState>
	</div>

	<div class="dashboard-jobs-footer">
		<JobPagination
			page={jobsList.page}
			pages={jobsList.pages}
			perPage={jobsList.perPage}
			total={jobsList.total}
			onpage={jobsList.setPage}
		/>
	</div>
</section>

<style>
	/* Cards / Table: one tinted track, the active view filled in primary */
	.dashboard-view-group {
		display: flex;
		gap: 2px;
		padding: 3px;
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--color-primary) 8%, transparent);
	}
	.dashboard-view-toggle {
		border-color: transparent;
		border-radius: calc(var(--radius-md) * 0.75);
		padding: 0.3125rem 0.75rem;
		color: var(--color-text-secondary);
	}
	.dashboard-view-toggle:hover {
		background: var(--color-primary-tint-2);
	}
	.dashboard-view-toggle[aria-pressed='true'] {
		background: var(--color-primary);
		color: var(--color-on-primary);
	}
	.dashboard-jobs-selection {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
		padding: 0.5rem 1rem;
		border-top: 1px solid color-mix(in srgb, var(--color-primary) 30%, transparent);
		background: color-mix(in srgb, var(--color-primary) 12%, var(--color-surface));
	}
	.dashboard-jobs-selection-count {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-primary-text);
	}
	.dashboard-jobs-selection-divider {
		width: 1px;
		height: 18px;
		background: color-mix(in srgb, var(--color-primary) 30%, transparent);
	}
	.dashboard-jobs-selection-clear {
		font-size: 0.8125rem;
	}
	.dashboard-jobs-feedback {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.375rem 0.5rem 0.375rem 1rem;
		border-top: 1px solid var(--color-border);
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
	.dashboard-jobs-feedback[data-tone='success'] {
		color: var(--color-success);
	}
	.dashboard-jobs-feedback[data-tone='error'] {
		color: var(--color-danger);
	}
	.dashboard-jobs-grid {
		padding: 0.75rem;
		gap: 0.75rem;
	}
	.dashboard-jobs-footer {
		padding: 0.625rem 1rem;
		border-top: 1px solid var(--color-border);
	}
	.dashboard-select-all-checkbox {
		width: 1rem;
		height: 1rem;
		border-radius: var(--radius-sm);
		accent-color: var(--color-primary);
	}
	.dashboard-empty-jobs {
		padding: 2rem 0;
		text-align: center;
		color: var(--color-text-faint);
	}
</style>
