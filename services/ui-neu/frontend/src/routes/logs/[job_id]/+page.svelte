<script lang="ts">
	import { onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { jobLogDownloadUrl } from '$lib/api/logs';
	import { createJobLog } from '$lib/stores/jobLog.svelte';
	import LogView from '$lib/components/LogView.svelte';

	const DEFAULT_LIMIT = 1000;

	const jobId = $derived($page.params.job_id ?? '');

	// One store instance per mounted page; SvelteKit reuses this component
	// across /logs/:id -> /logs/:other navigations, so the jobId effect below
	// tears down the old subscription and starts a fresh one for the new id.
	let log = $state(createJobLog(jobId, { limit: DEFAULT_LIMIT }));

	const entries = $derived(log.entries);
	const loading = $derived(log.loading);
	const error = $derived(log.error);

	const truncated = $derived(entries.length >= DEFAULT_LIMIT);

	async function load() {
		await log.load();
	}

	let liveJobId: string | null = null;
	$effect(() => {
		// Rebuild the store whenever the route param changes (SvelteKit reuses
		// this component across /logs/:id -> /logs/:other navigations): tear
		// down the old live subscription before starting the new job's feed.
		// Guarded on jobId (read explicitly, tracked) rather than on `log`
		// itself, so writing `log` here doesn't re-trigger this same effect.
		if (jobId === liveJobId) return;
		liveJobId = jobId;
		log.stop();
		const next = createJobLog(jobId, { limit: DEFAULT_LIMIT });
		log = next;
		next.load();
		next.start(); // live-tail while this page is open; harmless once the job goes terminal (no more lines emitted)
	});

	onDestroy(() => {
		log.stop();
	});
</script>

<div class="space-y-4">
	<div>
		<a href="/logs" class="text-sm text-primary-text hover:underline dark:text-primary-text-dark">&lt;- All logs</a>
		<h1 class="text-2xl font-bold text-gray-900 dark:text-white">Job log</h1>
		<p class="font-mono text-xs text-gray-500">{jobId}</p>
	</div>

	<!-- Action bar: log actions (Refresh / Download) -->
	<div
		class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-primary/15 bg-page px-4 py-3 dark:border-primary/20 dark:bg-primary/5"
	>
		<span class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Actions</span>
		<div class="flex items-center gap-2">
			<button onclick={load} class="rounded-lg border border-primary/25 px-3 py-2 text-sm hover:bg-primary/5">
				Refresh
			</button>
			<a
				href={jobLogDownloadUrl(jobId)}
				class="rounded-lg border border-primary/25 px-3 py-2 text-sm hover:bg-primary/5"
				class:pointer-events-none={entries.length === 0}
				class:opacity-50={entries.length === 0}
			>
				Download .zip
			</a>
		</div>
	</div>

	{#if truncated}
		<p class="text-xs text-amber-600 dark:text-amber-400">
			Showing the last {DEFAULT_LIMIT} lines. Download the .zip for the full log.
		</p>
	{/if}

	{#if loading}
		<p class="text-sm text-gray-500">Loading log...</p>
	{:else}
		<LogView {entries} {error} search={true} maxHeightClass="max-h-[70vh]" />
	{/if}
</div>
