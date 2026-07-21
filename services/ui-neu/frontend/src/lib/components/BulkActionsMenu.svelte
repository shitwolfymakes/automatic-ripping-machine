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

	const pillBase = 'px-2.5 py-1 rounded-md text-xs font-semibold cursor-pointer transition-colors';

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
	<span class="text-sm font-medium text-gray-600 dark:text-gray-300">{selectedJobs.size} selected</span>
{/if}

<!-- Gear menu -->
<Flyout align="right" width="w-56" label="Bulk actions">
	{#snippet trigger({ toggle })}
		<button
			onclick={toggle}
			disabled={bulkBusy}
			class="{pillBase} inline-flex items-center gap-1 bg-primary/10 text-gray-700 hover:bg-primary/20 dark:bg-primary/15 dark:text-gray-300 dark:hover:bg-primary/25 disabled:opacity-50"
		>
			{#if bulkBusy}
				<span class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
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
