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

<div class="stack">
	<div>
		<a href="/logs" class="btn btn-link">&lt;- All logs</a>
		<h1 class="page-title">Job log</h1>
		<p class="mono log-detail-page-id">{jobId}</p>
	</div>

	<!-- Action bar: log actions (Refresh / Download) -->
	<div class="cluster panel-section log-detail-page-actions">
		<span class="eyebrow">Actions</span>
		<div class="cluster">
			<button onclick={load} class="btn log-detail-page-action-btn">
				Refresh
			</button>
			<a
				href={jobLogDownloadUrl(jobId)}
				class="btn log-detail-page-action-btn"
				aria-disabled={entries.length === 0}
			>
				Download .zip
			</a>
		</div>
	</div>

	{#if truncated}
		<p class="log-detail-page-truncated">
			Showing the last {DEFAULT_LIMIT} lines. Download the .zip for the full log.
		</p>
	{/if}

	{#if loading}
		<p class="log-detail-page-loading">Loading log...</p>
	{:else}
		<LogView {entries} {error} search={true} maxHeightClass="max-h-[70vh]" />
	{/if}
</div>

<style>
	.log-detail-page-id { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.log-detail-page-actions { justify-content: space-between; }
	.log-detail-page-truncated { font-size: 0.75rem; line-height: 1rem; color: var(--color-on-warning-soft); }
	.log-detail-page-loading { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* original was px-3 py-2 (0.75rem/0.5rem), not .btn's default 0.5rem
	   1rem; text-sm matches .btn's own bundled font-size/line-height so no
	   size modifier is needed, just the padding restated */
	.log-detail-page-action-btn { padding: 0.5rem 0.75rem; }
	a[aria-disabled="true"] { pointer-events: none; opacity: 0.5; }
</style>
