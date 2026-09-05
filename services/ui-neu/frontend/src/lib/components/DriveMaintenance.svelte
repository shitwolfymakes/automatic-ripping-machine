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

<div class="flex flex-wrap items-center gap-2">
	<button
		data-testid="drive-rescan"
		onclick={() => run(false)}
		disabled={scanning}
		class="rounded-lg border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary-text transition-colors hover:bg-primary/10 disabled:opacity-50 dark:border-primary/20 dark:text-primary-text-dark dark:hover:bg-primary/15"
		title="Look for optical drives on this host now"
	>{scanning ? 'Scanning...' : 'Scan for drives'}</button>
	<button
		data-testid="drive-force-rescan"
		onclick={() => { confirmOpen = true; }}
		disabled={scanning}
		class="rounded-lg border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-50 disabled:opacity-50 dark:border-amber-700 dark:text-amber-400 dark:hover:bg-amber-900/20"
		title="Remove detected drives that aren't connected, then scan"
	>{scanning ? 'Scanning...' : 'Remove Missing Drives'}</button>
	{#if summaryText}
		<span data-testid="drive-rescan-summary" class="basis-full text-xs text-gray-500 dark:text-gray-400">{summaryText}</span>
	{/if}
	{#if error}
		<span data-testid="drive-rescan-error" class="basis-full text-xs text-red-600 dark:text-red-400">{error}</span>
	{/if}
</div>

<ConfirmDialog
	open={confirmOpen}
	title="Remove missing drives?"
	message="Detected drives that are not currently connected will be removed now. Enrolled and ignored drives are kept, and a reconnected drive reappears on the next scan."
	confirmLabel="Remove and scan"
	variant="danger"
	onconfirm={() => { confirmOpen = false; void run(true); }}
	oncancel={() => { confirmOpen = false; }}
/>
