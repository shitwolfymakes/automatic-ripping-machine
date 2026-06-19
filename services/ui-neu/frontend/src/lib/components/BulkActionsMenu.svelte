<script lang="ts">
	import type { JobStats } from './JobStatsPanel.svelte';

	interface Props {
		// v3 job ids are strings (was Set<number> under the BFF).
		selectedJobs: Set<string>;
		jobsStats: JobStats | null;
		gearOpen: boolean;
		bulkBusy: boolean;
		onaction: (
			action: 'delete',
			params: { job_ids?: string[]; status?: string },
			description: string
		) => void;
		ontoggle: () => void;
	}

	let { selectedJobs, jobsStats, gearOpen, bulkBusy, onaction, ontoggle }: Props = $props();

	const pillBase = 'px-2.5 py-1 rounded-md text-xs font-semibold cursor-pointer transition-colors';
	const menuItemBase = 'w-full px-3 py-2 text-left text-sm';
	const menuItemNormal = `${menuItemBase} text-gray-700 hover:bg-primary/5 dark:text-gray-300 dark:hover:bg-primary/10`;

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
<div class="relative">
	<button
		onclick={(e: MouseEvent) => { e.stopPropagation(); ontoggle(); }}
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

	{#if gearOpen}
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			onclick={(e: MouseEvent) => e.stopPropagation()}
			class="absolute right-0 z-50 mt-1 w-56 rounded-lg border border-primary/20 bg-surface py-1 shadow-lg dark:border-primary/25 dark:bg-surface-dark"
		>
			{#if selectedJobs.size > 0}
				<div class="px-3 py-1.5 text-xs font-semibold text-gray-400 dark:text-gray-500">Selected ({selectedJobs.size})</div>
				{#each selectedActions() as item}
					<button
						onclick={() => onaction(item.action, item.params, item.description)}
						class={menuItemNormal}
					>{item.label}</button>
				{/each}
				<div class="my-1 border-t border-gray-200 dark:border-gray-700"></div>
			{/if}

			<div class="px-3 py-1.5 text-xs font-semibold text-gray-400 dark:text-gray-500">Bulk Actions</div>
			{#each bulkActions() as item}
				<button
					onclick={() => onaction(item.action, item.params, item.description)}
					class={menuItemNormal}
				>{item.label}</button>
			{/each}
		</div>
	{/if}
</div>
