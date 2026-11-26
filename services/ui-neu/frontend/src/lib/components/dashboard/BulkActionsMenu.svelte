<script lang="ts">
	import Flyout from '../shared/Flyout.svelte';
	import FlyoutItem from '../shared/FlyoutItem.svelte';
	import FlyoutDivider from '../shared/FlyoutDivider.svelte';
	import Glyph from '../shared/Glyph.svelte';

	interface Props {
		// Job ids are strings.
		selectedJobs: Set<string>;
		bulkBusy: boolean;
		onaction: (action: 'delete', params: { job_ids?: string[]; status?: string }, description: string) => void;
	}

	let { selectedJobs, bulkBusy, onaction }: Props = $props();

	// v3 only supports bulk DELETE (no bulk purge endpoint). Every action
	// routes through bulkDeleteJobs.
	type BulkItem = {
		action: 'delete';
		label: string;
		description: string;
		params: { job_ids?: string[]; status?: string };
	};

	function bulkActions(): BulkItem[] {
		return [
			{
				action: 'delete',
				label: 'Delete All Failed',
				description: 'delete all failed jobs',
				params: { status: 'failed' }
			},
			{
				action: 'delete',
				label: 'Delete All Successful',
				description: 'delete all successful jobs',
				params: { status: 'ripped' }
			}
		];
	}

	function selectedActions(): BulkItem[] {
		const ids = [...selectedJobs];
		const n = selectedJobs.size;
		return [
			{
				action: 'delete',
				label: 'Delete Selected',
				description: `delete ${n} selected job(s)`,
				params: { job_ids: ids }
			}
		];
	}
</script>

<!-- Gear menu. The selection count lives in the dashboard's selection bar;
     "Delete Selected" stays in the flyout for keyboard users who open the menu. -->
<Flyout align="right" width="w-56" label="Bulk actions">
	{#snippet trigger({ toggle, open })}
		<!-- .btn: the same control height and type size as the status filter and the Details buttons -->
		<button
			type="button"
			onclick={toggle}
			disabled={bulkBusy}
			aria-expanded={open}
			class="btn bulk-actions-trigger inline-flex items-center gap-1.5"
		>
			{#if bulkBusy}
				<span class="bulk-actions-spinner" aria-hidden="true"></span>
			{:else}
				<Glyph name="gear" class="h-3.5 w-3.5" />
			{/if}
			Actions
			<Glyph name="chevron-down" class="chevron" />
		</button>
	{/snippet}
	{#snippet children({ close })}
		{#if selectedJobs.size > 0}
			<FlyoutDivider label={`Selected (${selectedJobs.size})`} />
			{#each selectedActions() as item (item.action)}
				<FlyoutItem
					onclick={() => {
						onaction(item.action, item.params, item.description);
						close();
					}}
				>
					{item.label}
				</FlyoutItem>
			{/each}
			<FlyoutDivider />
		{/if}

		<FlyoutDivider label="Bulk Actions" />
		{#each bulkActions() as item (item.params.status)}
			<FlyoutItem
				onclick={() => {
					onaction(item.action, item.params, item.description);
					close();
				}}
			>
				{item.label}
			</FlyoutItem>
		{/each}
	{/snippet}
</Flyout>

<style>
	/* .btn's block padding plus its border comes to 38px; dropping the padding
	   lets min-height (--control-h) set it, level with the status filter. */
	.bulk-actions-trigger {
		padding-block: 0;
	}
	/* the chevron flips a full 180deg (open = pointing up); .btn's shared
	   .chevron rule only rotates 90deg, tuned for a right-pointing chevron. */
	/* :global: .chevron is rendered by the child Glyph component, outside this component's own scoped template */
	.bulk-actions-trigger[aria-expanded='true'] :global(.chevron) {
		transform: rotate(180deg);
	}
	.bulk-actions-trigger:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.bulk-actions-spinner {
		display: inline-block;
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 9999px;
		border: 2px solid currentColor;
		border-top-color: transparent;
	}
	@media (prefers-reduced-motion: no-preference) {
		.bulk-actions-spinner {
			animation: bulk-actions-spin 1s linear infinite;
		}
	}
	@keyframes bulk-actions-spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
