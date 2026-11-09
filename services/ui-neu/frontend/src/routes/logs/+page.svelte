<script lang="ts">
	import { onMount } from 'svelte';
	import type { JobView } from '$lib/types/api.gen';
	import JobFilterBar from '$lib/components/JobFilterBar.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import PosterImage from '$lib/components/PosterImage.svelte';
	import { effectiveJobStatus } from '$lib/utils/job-status';
	import { driveLabel } from '$lib/utils/drive-name';
	import { jobPoster } from '$lib/utils/poster';
	import {
		discKindLabel,
		discPosition,
		filterLogJobs,
		jobTypeConfig,
		logCountText,
		orderByLastModified,
		shortJobId
	} from '$lib/utils/log-list';
	import { calendarTimeAgo, formatShortDateTime } from '$lib/utils/format';
	import { dashboard } from '$lib/stores/dashboard';
	import { LogListing } from '$lib/stores/logListing.svelte';

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
									{@const type = jobTypeConfig(job)}
									{@const drive = driveLabel(job.drive_id, $dashboard.drive_names)}
									{@const logAt = listing.modified.get(job.id)}
									<tr class="table-row">
										<td class="table-cell" data-label="Title">
											<div class="logs-panel-title-cell">
												<PosterImage
													url={jobPoster(job)}
													alt=""
													class="logs-panel-poster {job.disc_type === 'cd' ? 'logs-panel-poster-square' : ''}"
												/>
												<div class="min-w-0">
													<a href="/logs/{job.id}" class="logs-panel-title-link">{job.title || job.id}</a>
													<div class="logs-panel-id" title={job.id}>{shortJobId(job.id)}</div>
												</div>
											</div>
										</td>
										<td class="table-cell" data-label="Status">
											<StatusBadge status={effectiveJobStatus(job)} />
										</td>
										<td class="table-cell" data-label="Type">
											<span class="logs-panel-chips">
												<span class="logs-panel-chip" style:--jt-bg={type.badgeBg} style:--jt-text={type.badgeText}
													>{type.label}</span
												>
												<span class="logs-panel-chip logs-panel-chip-neutral"
													>{discKindLabel(job, $dashboard.drive_source_kinds)}</span
												>
											</span>
										</td>
										<td class="table-cell logs-panel-nowrap" data-label="Disc">{discPosition(job)}</td>
										<td class="table-cell" data-label="Drive">
											{#if drive}
												<span class="logs-panel-drive" title={drive}>{drive}</span>
											{:else}
												-
											{/if}
										</td>
										<td class="table-cell logs-panel-nowrap" data-label="Last modified">
											{#if logAt}
												{@const relative = calendarTimeAgo(logAt)}
												{#if relative}
													<div>{relative}</div>
													<div class="logs-panel-muted logs-panel-small">{formatShortDateTime(logAt)}</div>
												{:else}
													<div>{formatShortDateTime(logAt)}</div>
												{/if}
											{:else}
												<span class="logs-panel-muted">No log yet</span>
											{/if}
										</td>
									</tr>
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
	.logs-panel-small {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.logs-panel-nowrap {
		white-space: nowrap;
	}
	.logs-panel-title-cell {
		display: flex;
		align-items: center;
		gap: 0.625rem;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.logs-panel-poster) {
		height: 2.5rem;
		width: 1.75rem;
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	/* :global: forwarded through PosterImage's class prop; CD covers are square */
	:global(.logs-panel-poster-square) {
		width: 2.5rem;
	}
	.logs-panel-title-link {
		font-weight: 500;
		color: var(--color-primary-text);
	}
	.logs-panel-id {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.logs-panel-chips {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}
	/* the type pill matches JobRow's .job-row-type-pill */
	.logs-panel-chip {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		white-space: nowrap;
		background: var(--jt-bg);
		color: var(--jt-text);
	}
	.logs-panel-chip-neutral {
		background: none;
		border: 1px solid var(--color-border);
		color: var(--color-text-secondary);
	}
	.logs-panel-drive {
		display: inline-block;
		max-width: 12rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		vertical-align: bottom;
	}
</style>
