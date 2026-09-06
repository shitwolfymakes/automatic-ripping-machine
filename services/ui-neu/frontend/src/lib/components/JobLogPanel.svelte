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
			class="flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-white"
		>
			<svg class="h-4 w-4 transition-transform {open ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
			Log
			<span class="text-sm font-normal text-gray-500 dark:text-gray-400">({log.entries.length} lines)</span>
			{#if log.live}
				<span class="flex items-center gap-1.5 text-xs font-normal text-green-600 dark:text-green-400">
					<span class="h-2 w-2 rounded-full bg-green-500"></span>
					live
				</span>
			{/if}
		</button>
		<div class="flex items-center gap-3 text-sm">
			<a
				href="/logs/{jobId}"
				data-testid="job-log-open"
				class="text-primary-text hover:underline dark:text-primary-text-dark"
			>
				Open full log
			</a>
			<a
				href={jobLogDownloadUrl(jobId)}
				data-testid="job-log-download"
				class="text-primary-text hover:underline dark:text-primary-text-dark"
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
