<script lang="ts">
	import { onDestroy } from 'svelte';
	import { jobLogDownloadUrl } from '$lib/api/logs';
	import { createJobLog } from '$lib/stores/jobLog.svelte';
	import { isLive } from '$lib/utils/job-status-groups';
	import type { JobView } from '$lib/types/api.gen';
	import LogView from '$lib/components/LogView.svelte';

	interface Props {
		jobId: string;
		job: Pick<JobView, 'status' | 'transcode_progress'>;
		defaultOpen?: boolean;
	}

	let { jobId, job, defaultOpen }: Props = $props();

	const log = createJobLog(jobId, { limit: 200 });

	let open = $state(defaultOpen ?? isLive(job));

	// Lifecycle: fetch once always; subscribe to the live feed only while the
	// job is live (this includes an in-flight transcode), and tear the
	// subscription down the moment it stops being live (job prop changing, or
	// unmount).
	let started = false;
	$effect(() => {
		const active = isLive(job);
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

<!-- The toggle, counts and links render inside LogView's title bar, so the
     whole section is one terminal window (collapsed = title bar only). -->
{#snippet titlebar()}
	<button
		type="button"
		onclick={() => {
			open = !open;
		}}
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
		<a href="/logs/{jobId}" data-testid="job-log-open" class="btn btn-link"> Open full log </a>
		<a href={jobLogDownloadUrl(jobId)} data-testid="job-log-download" class="btn btn-link"> Download .zip </a>
	</div>
{/snippet}

<section>
	<LogView
		entries={log.entries}
		error={log.error}
		loading={log.loading && log.entries.length === 0}
		search
		header={titlebar}
		collapsed={!open}
	/>
</section>

<style>
	.job-log-panel-toggle {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.9375rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-terminal-ink);
	}
	.job-log-panel-toggle .chevron {
		transition: transform var(--motion-fast) var(--ease);
	}
	.job-log-panel-toggle[aria-expanded='true'] .chevron {
		transform: rotate(90deg);
	}
	.job-log-panel-count {
		font-size: 0.8125rem;
		line-height: 1.25rem;
		font-weight: 400;
		color: color-mix(in srgb, var(--color-terminal-ink) 55%, transparent);
	}
	/* success reads on the fixed dark well in both modes; mixed towards the
	   ink so the light-mode green is not too dim there */
	.job-log-panel-live {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 400;
		color: color-mix(in srgb, var(--color-success) 70%, var(--color-terminal-ink));
	}
	.job-log-panel-live-dot {
		height: 0.5rem;
		width: 0.5rem;
		border-radius: 9999px;
		background: var(--color-success);
	}
</style>
