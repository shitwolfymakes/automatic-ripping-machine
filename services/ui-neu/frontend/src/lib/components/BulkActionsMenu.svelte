<script lang="ts">
	import type { JobStats } from './JobStatsPanel.svelte';
	import Flyout from './Flyout.svelte';
	import FlyoutItem from './FlyoutItem.svelte';
	import FlyoutDivider from './FlyoutDivider.svelte';

	interface Props {
		// v3 job ids are strings (was Set<number> under the BFF).
		selectedJobs: Set<string>;
		jobsStats: JobStats | null;
		bulkBusy: boolean;
		onaction: (
			action: 'delete',
			params: { job_ids?: string[]; status?: string },
			description: string
		) => void;
	}

	let { selectedJobs, jobsStats, bulkBusy, onaction }: Props = $props();

	// v3 only supports bulk DELETE (bulkPurgeJobs is MISSING), so the purge
	// menu items are gone. Every remaining action routes through bulkDeleteJobs.
	type BulkItem = { action: 'delete'; label: string; description: string; params: { job_ids?: string[]; status?: string } };

	function bulkActions(): BulkItem[] {
		return [
			{ action: 'delete', label: `Delete All Failed${jobsStats?.fail ? ` (${jobsStats.fail})` : ''}`, description: `delete all failed jobs${jobsStats?.fail ? ` (${jobsStats.fail})` : ''}`, params: { status: 'failed' } },
			{ action: 'delete', label: `Delete All Successful${jobsStats?.success ? ` (${jobsStats.success})` : ''}`, description: `delete all successful jobs${jobsStats?.success ? ` (${jobsStats.success})` : ''}`, params: { status: 'ripped' } }
		];
	}

	function selectedActions(): BulkItem[] {
		const ids = [...selectedJobs];
		const n = selectedJobs.size;
		return [
			{ action: 'delete', label: 'Delete Selected', description: `delete ${n} selected job(s)`, params: { job_ids: ids } }
		];
	}
</script>

<!-- Selection count -->
{#if selectedJobs.size > 0}
	<span class="bulk-actions-count">{selectedJobs.size} selected</span>
{/if}

<!-- Gear menu -->
<Flyout align="right" width="w-56" label="Bulk actions">
	{#snippet trigger({ toggle })}
		<button onclick={toggle} disabled={bulkBusy} class="chip bulk-actions-trigger inline-flex items-center gap-1">
			{#if bulkBusy}
				<span class="bulk-actions-spinner" aria-hidden="true"></span>
			{:else}
				&#9881;
			{/if}
			Actions &#9662;
		</button>
	{/snippet}
	{#snippet children({ close })}
		{#if selectedJobs.size > 0}
			<FlyoutDivider label={`Selected (${selectedJobs.size})`} />
			{#each selectedActions() as item}
				<FlyoutItem onclick={() => { onaction(item.action, item.params, item.description); close(); }}>
					{item.label}
				</FlyoutItem>
			{/each}
			<FlyoutDivider />
		{/if}

		<FlyoutDivider label="Bulk Actions" />
		{#each bulkActions() as item}
			<FlyoutItem onclick={() => { onaction(item.action, item.params, item.description); close(); }}>
				{item.label}
			</FlyoutItem>
		{/each}
	{/snippet}
</Flyout>

<style>
	.bulk-actions-count { font-size: 0.875rem; font-weight: 500; color: var(--color-text-secondary); }
	.bulk-actions-trigger:disabled { opacity: 0.5; cursor: not-allowed; }
	.bulk-actions-spinner {
		display: inline-block;
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 9999px;
		border: 2px solid currentColor;
		border-top-color: transparent;
	}
	@media (prefers-reduced-motion: no-preference) {
		.bulk-actions-spinner { animation: bulk-actions-spin 1s linear infinite; }
	}
	@keyframes bulk-actions-spin {
		to { transform: rotate(360deg); }
	}
</style>
