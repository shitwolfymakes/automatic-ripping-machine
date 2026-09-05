<script lang="ts">
	import type { DriveView } from '$lib/types/api.gen';
	import { enrollDrive, ignoreDrive, unignoreDrive } from '$lib/api/drives';
	import { serialLabel } from '$lib/utils/drives';
	import { formatDateTime } from '$lib/utils/format';

	interface Props { detected: DriveView[]; ignored: DriveView[]; onchanged: () => void }
	let { detected, ignored, onchanged }: Props = $props();

	let ignoredOpen = $state(false);
	let busy = $state<string | null>(null);
	let error = $state<string | null>(null);

	async function run(id: string, action: () => Promise<unknown>) {
		busy = id;
		error = null;
		try {
			await action();
			onchanged();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Action failed';
		} finally {
			busy = null;
		}
	}
	const rowBtn = 'rounded-md px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50';
</script>

{#snippet row(d: DriveView, ignoredRow: boolean)}
	{@const serial = serialLabel(d)}
	<div data-testid={`${ignoredRow ? 'ignored' : 'detected'}-row-${d.id}`} class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-primary/15 px-3 py-2 text-sm dark:border-primary/15">
		<span class="font-medium text-gray-900 dark:text-white">{d.model ?? d.hostname}</span>
		<span class={serial.warn ? 'text-amber-600 dark:text-amber-400' : 'text-gray-500 dark:text-gray-400'}>{serial.text}</span>
		<code class="text-xs text-gray-500 dark:text-gray-400">{d.device_path}</code>
		<span class="text-xs text-gray-400">{d.last_seen_at ? formatDateTime(d.last_seen_at) : '-'}</span>
		<span class="ml-auto flex gap-2">
			{#if ignoredRow}
				<button data-testid={`unignore-${d.id}`} disabled={busy === d.id} onclick={() => run(d.id, () => unignoreDrive(d.id))} class="{rowBtn} border border-primary/20 text-primary-text hover:bg-primary/10 dark:text-primary-text-dark">Un-ignore</button>
			{:else}
				<button data-testid={`ignore-${d.id}`} disabled={busy === d.id} onclick={() => run(d.id, () => ignoreDrive(d.id))} class="{rowBtn} border border-primary/20 text-primary-text hover:bg-primary/10 dark:text-primary-text-dark">Ignore</button>
			{/if}
			<button data-testid={`enroll-${d.id}`} disabled={busy === d.id} onclick={() => run(d.id, () => enrollDrive(d.id))} class="{rowBtn} bg-primary/15 text-primary-text hover:bg-primary/25 dark:text-primary-text-dark">Enroll</button>
		</span>
	</div>
{/snippet}

<div class="space-y-3 rounded-lg border border-primary/20 bg-surface p-3 shadow-xs dark:border-primary/20 dark:bg-surface-dark" data-testid="drive-lifecycle-panel">
	<h3 class="text-sm font-semibold text-gray-900 dark:text-white">Detected</h3>
	{#if error}
		<p data-testid="lifecycle-error" class="text-xs text-red-600 dark:text-red-400">{error}</p>
	{/if}
	{#if detected.length === 0}
		<p data-testid="detected-empty" class="text-sm text-gray-400">No unenrolled drives. Plug one in and it appears here on the next scan.</p>
	{:else}
		<div class="space-y-2">
			{#each detected as d (d.id)}{@render row(d, false)}{/each}
		</div>
	{/if}

	{#if ignored.length > 0}
		<button data-testid="ignored-toggle" aria-expanded={ignoredOpen} onclick={() => { ignoredOpen = !ignoredOpen; }} class="text-sm font-semibold text-gray-700 hover:underline dark:text-gray-300">
			Ignored ({ignored.length}) {ignoredOpen ? '▾' : '▸'}
		</button>
		{#if ignoredOpen}
			<div class="space-y-2">
				{#each ignored as d (d.id)}{@render row(d, true)}{/each}
			</div>
		{/if}
	{/if}
</div>
