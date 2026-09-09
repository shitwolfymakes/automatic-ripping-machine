<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchJobStats, type JobStats } from '$lib/api/system';
	import SectionFrame from './SectionFrame.svelte';

	let stats = $state<JobStats | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			stats = await fetchJobStats();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load stats';
		}
	});
</script>

<SectionFrame label="Ripping Statistics" accent="var(--color-success)">
	<div class="job-stats-card-grid">
		<div class="job-stats-card-tile">
			<div class="job-stats-card-value">{stats ? stats.total : '-'}</div>
			<div class="job-stats-card-label">Total Rips</div>
		</div>
		<div class="job-stats-card-tile">
			<div class="job-stats-card-value job-stats-card-value-success">{stats ? (stats.by_status.success ?? 0) : '-'}</div>
			<div class="job-stats-card-label">Success</div>
		</div>
		<div class="job-stats-card-tile">
			<div class="job-stats-card-value job-stats-card-value-danger">{stats ? (stats.by_status.fail ?? 0) : '-'}</div>
			<div class="job-stats-card-label">Failed</div>
		</div>
		<div class="job-stats-card-tile">
			<div class="job-stats-card-value job-stats-card-value-info">
				{stats ? (stats.by_status.ripping ?? 0) + (stats.by_status.transcoding ?? 0) : '-'}
			</div>
			<div class="job-stats-card-label">Active</div>
		</div>
	</div>
	{#if stats && Object.keys(stats.by_type).length > 0}
		<div class="job-stats-card-types">
			{#each Object.entries(stats.by_type) as [type, count]}
				<div class="job-stats-card-type">
					<span class="job-stats-card-type-name">{type}</span>
					<span class="badge">{count}</span>
				</div>
			{/each}
		</div>
	{/if}
</SectionFrame>

<style>
	.job-stats-card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; }
	@media (min-width: 640px) { .job-stats-card-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
	.job-stats-card-tile { text-align: center; }
	.job-stats-card-value { font-size: 1.5rem; line-height: 2rem; font-weight: 700; color: var(--color-text); }
	.job-stats-card-value-success { color: var(--color-success); }
	.job-stats-card-value-danger { color: var(--color-danger); }
	.job-stats-card-value-info { color: var(--color-info); }
	.job-stats-card-label { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.job-stats-card-types { margin-top: 0.75rem; display: flex; flex-wrap: wrap; gap: 0.75rem; border-top: 1px solid var(--color-border); padding-top: 0.75rem; }
	.job-stats-card-type { display: flex; align-items: center; gap: 0.375rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.job-stats-card-type-name { font-weight: 500; text-transform: capitalize; }
</style>
