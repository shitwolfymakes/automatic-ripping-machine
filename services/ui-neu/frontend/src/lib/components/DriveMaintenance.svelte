<script lang="ts">
	import type { DriveRescanResponse } from '$lib/types/api.gen';
	import { rescanDrives } from '$lib/api/drives';
	import ConfirmDialog from './ConfirmDialog.svelte';

	interface Props {
		onrescanned: (summary: DriveRescanResponse) => void;
	}
	let { onrescanned }: Props = $props();

	let scanning = $state(false);
	let confirmOpen = $state(false);
	let summary = $state<DriveRescanResponse | null>(null);
	let error = $state<string | null>(null);

	async function run(force: boolean) {
		scanning = true;
		error = null;
		try {
			summary = await rescanDrives(force);
			onrescanned(summary);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Rescan failed';
		} finally {
			scanning = false;
		}
	}

	let summaryText = $derived(
		summary
			? `${summary.detected ?? 0} detected · ${summary.enrolled ?? 0} enrolled · ${summary.ignored ?? 0} ignored` +
					((summary.pruned ?? 0) > 0 ? ` · ${summary.pruned} removed` : '')
			: ''
	);
</script>

<div class="flex flex-wrap items-center justify-end gap-2">
	<button
		data-testid="drive-rescan"
		onclick={() => run(false)}
		disabled={scanning}
		class="btn btn-sm drive-maintenance-btn drive-maintenance-scan-btn"
		title="Look for optical drives on this host now"
	>{scanning ? 'Scanning...' : 'Scan for drives'}</button>
	<button
		data-testid="drive-force-rescan"
		onclick={() => { confirmOpen = true; }}
		disabled={scanning}
		class="btn btn-sm btn-warning drive-maintenance-btn"
		title="Remove detected drives that aren't connected, then scan"
	>{scanning ? 'Scanning...' : 'Remove Missing Drives'}</button>
	{#if summaryText}
		<span data-testid="drive-rescan-summary" class="basis-full drive-maintenance-right drive-maintenance-summary">{summaryText}</span>
	{/if}
	{#if error}
		<span data-testid="drive-rescan-error" class="basis-full field-error drive-maintenance-right">{error}</span>
	{/if}
</div>

<style>
	.drive-maintenance-right { text-align: right; }
	/* the original border was border-primary/20 (--color-border), lighter
	   than .btn's default border-primary-strong. */
	/* these two were px-3 py-1.5 text-xs originally: 6px vertical padding and
	   the text-xs leading ratio (16px at 12px type). btn-sm's 4px padding plus
	   .btn's text-sm ratio (17.14px at 12px) rendered them 2px shorter and
	   shifted everything below (the Task 7 btn-sm audit case). */
	.drive-maintenance-btn { padding-top: 0.375rem; padding-bottom: 0.375rem; line-height: calc(1 / 0.75); }
	.drive-maintenance-scan-btn { border-color: var(--color-border); }
	/* text-xs text-gray-500 - not panel-hint's block-level note, whose own
	   margin-top would add space above this span that the original,
	   a plain basis-full flex item, never had. */
	.drive-maintenance-summary { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
</style>

<ConfirmDialog
	open={confirmOpen}
	title="Remove missing drives?"
	message="Detected drives that are not currently connected will be removed now. Enrolled and ignored drives are kept, and a reconnected drive reappears on the next scan."
	confirmLabel="Remove and scan"
	variant="danger"
	onconfirm={() => { confirmOpen = false; void run(true); }}
	oncancel={() => { confirmOpen = false; }}
/>
