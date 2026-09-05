<script lang="ts">
	import { onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { jobLogDownloadUrl } from '$lib/api/logs';
	import { createJobLog } from '$lib/stores/jobLog.svelte';

	const DEFAULT_LIMIT = 1000;

	const jobId = $derived($page.params.job_id ?? '');

	// One store instance per mounted page; SvelteKit reuses this component
	// across /logs/:id -> /logs/:other navigations, so the jobId effect below
	// tears down the old subscription and starts a fresh one for the new id.
	let log = $state(createJobLog(jobId, { limit: DEFAULT_LIMIT }));

	let levelFilter = $state('');
	let search = $state('');

	const entries = $derived(log.entries);
	const loading = $derived(log.loading);
	const error = $derived(log.error);

	const truncated = $derived(entries.length >= DEFAULT_LIMIT);

	const filtered = $derived(
		entries.filter((e) => {
			if (levelFilter && (e.level ?? '').toLowerCase() !== levelFilter) return false;
			if (search && !`${e.event ?? ''} ${e.logger ?? ''}`.toLowerCase().includes(search.toLowerCase()))
				return false;
			return true;
		})
	);

	async function load() {
		await log.load();
	}

	function levelClass(level: string): string {
		switch ((level ?? '').toLowerCase()) {
			case 'error': return 'text-red-600 dark:text-red-400';
			case 'warning': return 'text-amber-600 dark:text-amber-400';
			case 'debug': return 'text-gray-400';
			default: return 'text-gray-700 dark:text-gray-300';
		}
	}

	// Colored pill for the level cell — distinct background so the eye can scan
	// severity down the column at a glance.
	function levelBadgeClass(level: string): string {
		switch ((level ?? '').toLowerCase()) {
			case 'error': return 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300';
			case 'warning': return 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300';
			case 'debug': return 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400';
			default: return 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300';
		}
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

	<!-- Action bar: filters (Level / message search) -->
	<div
		class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-primary/15 bg-page px-4 py-3 dark:border-primary/20 dark:bg-primary/5"
	>
		<label class="text-sm">
			Level
			<select
				bind:value={levelFilter}
				class="ml-1 rounded-lg border border-primary/25 bg-primary/5 px-2 py-1 text-sm dark:border-primary/30 dark:bg-primary/10 dark:text-white"
			>
				<option value="">All</option>
				<option value="error">Error</option>
				<option value="warning">Warning</option>
				<option value="info">Info</option>
				<option value="debug">Debug</option>
			</select>
		</label>
		<input
			type="text"
			bind:value={search}
			placeholder="Filter messages..."
			aria-label="Filter log messages"
			class="rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-sm dark:border-primary/30 dark:bg-primary/10 dark:text-white"
		/>
	</div>

	{#if truncated}
		<p class="text-xs text-amber-600 dark:text-amber-400">
			Showing the first {DEFAULT_LIMIT} lines - download the .zip for the full log.
		</p>
	{/if}

	{#if loading}
		<p class="text-sm text-gray-500">Loading log...</p>
	{:else if error}
		<p class="text-sm text-red-600 dark:text-red-400">Could not load log: {error.message}</p>
	{:else if entries.length === 0}
		<p class="text-sm text-gray-500">No log entries for this job.</p>
	{:else if filtered.length === 0}
		<p class="text-sm text-gray-500">No entries match.</p>
	{:else}
		<div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
			<table class="w-full text-left font-mono text-xs">
				<thead class="bg-gray-50 dark:bg-gray-800/50">
					<tr class="border-b border-gray-200 dark:border-gray-700">
						<th class="whitespace-nowrap px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Time</th>
						<th class="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Level</th>
						<th class="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Logger</th>
						<th class="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Message</th>
					</tr>
				</thead>
				<tbody>
					{#each filtered as e, i (i)}
						<tr class="border-b border-gray-100 align-top last:border-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/40">
							<td class="whitespace-nowrap px-3 py-1.5 text-gray-400 tabular-nums">{e.timestamp ?? ''}</td>
							<td class="px-3 py-1.5">
								<span class="inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase {levelBadgeClass(e.level)}">{e.level}</span>
							</td>
							<td class="whitespace-nowrap px-3 py-1.5 text-gray-500 dark:text-gray-400">{e.logger}</td>
							<td class="px-3 py-1.5 break-all {levelClass(e.level)}">{e.event}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
