<script lang="ts">
	import { onDestroy } from 'svelte';
	import { jobLogDownloadUrl } from '$lib/api/logs';
	import { createJobLog } from '$lib/stores/jobLog.svelte';
	import { isJobActive } from '$lib/utils/job-type';
	import LogView from '$lib/components/LogView.svelte';

	interface Props {
		jobId: string;
		status: string | null;
		defaultOpen?: boolean;
	}

	let { jobId, status, defaultOpen }: Props = $props();

	const log = createJobLog(jobId, { limit: 200 });

	let open = $state(defaultOpen ?? isJobActive(status));

	// Lifecycle: fetch once always; subscribe to the live feed only while the
	// job is active, and tear the subscription down the moment it goes
	// terminal (status prop changing, or unmount).
	let started = false;
	$effect(() => {
		const active = isJobActive(status);
		if (active && !started) {
			started = true;
			log.start();
		} else if (!active && started) {
			started = false;
			log.stop();
		}
	});

	$effect(() => {
		void jobId;
		log.load();
	});

	onDestroy(() => {
		log.stop();
	});
</script>

<section>
	<div class="flex flex-wrap items-center justify-between gap-2">
		<button
			type="button"
			onclick={() => { open = !open; }}
			class="job-log-panel-toggle"
			aria-expanded={open}
		>
			<svg class="h-4 w-4 chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
			Log
			<span class="job-log-panel-count">({log.entries.length} lines)</span>
			{#if log.live}
				<span class="job-log-panel-live">
					<span class="job-log-panel-live-dot"></span>
					live
				</span>
			{/if}
		</button>
		<div class="flex items-center gap-3">
			<a
				href="/logs/{jobId}"
				data-testid="job-log-open"
				class="btn btn-link"
			>
				Open full log
			</a>
			<a
				href={jobLogDownloadUrl(jobId)}
				data-testid="job-log-download"
				class="btn btn-link"
			>
				Download .zip
			</a>
		</div>
	</div>

	{#if open}
		<div class="mt-3">
			<LogView entries={log.entries} loading={log.loading} error={log.error} live={log.live} />
		</div>
	{/if}
</section>

<style>
	.job-log-panel-toggle { display: flex; align-items: center; gap: 0.5rem; font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.job-log-panel-toggle .chevron { transition: transform var(--motion-fast) var(--ease); }
	.job-log-panel-toggle[aria-expanded="true"] .chevron { transform: rotate(90deg); }
	.job-log-panel-count { font-size: 0.875rem; line-height: 1.25rem; font-weight: 400; color: var(--color-text-muted); }
	.job-log-panel-live { display: flex; align-items: center; gap: 0.375rem; font-size: 0.75rem; line-height: 1rem; font-weight: 400; color: var(--color-success); }
	.job-log-panel-live-dot { height: 0.5rem; width: 0.5rem; border-radius: 9999px; background: var(--color-success); }
</style>
