<script lang="ts">
	import { onDestroy } from 'svelte';
	import { jobLogDownloadUrl, type LogEntry } from '$lib/api/logs';
	import { createJobLog } from '$lib/stores/jobLog.svelte';
	import { logService, serviceLabel, type LogService } from '$lib/utils/log-service';
	import { isJobActive } from '$lib/utils/job-type';

	interface Props {
		jobId: string;
		status: string | null;
		defaultOpen?: boolean;
	}

	let { jobId, status, defaultOpen }: Props = $props();

	const log = createJobLog(jobId, { limit: 200 });

	let open = $state(defaultOpen ?? isJobActive(status));
	let filter = $state<'all' | LogService>('all');
	let following = $state(true);
	let viewEl = $state<HTMLDivElement | null>(null);

	const FILTERS: { key: 'all' | LogService; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'backend', label: 'Backend' },
		{ key: 'ripper', label: 'Ripper' },
		{ key: 'transcode', label: 'Transcode' }
	];

	const filtered = $derived(
		filter === 'all' ? log.entries : log.entries.filter((e) => logService(e.service) === filter)
	);

	function segment(active: boolean): string {
		return `rounded-md px-3 py-1.5 text-xs font-medium ${
			active
				? 'bg-primary text-on-primary'
				: 'bg-primary/10 text-gray-600 hover:bg-primary/15 dark:bg-primary/15 dark:text-gray-300'
		}`;
	}

	function chipClass(service: LogService): string {
		switch (service) {
			case 'backend':
				return 'bg-primary/15 text-primary-text dark:bg-primary/20 dark:text-primary-text-dark';
			case 'ripper':
				return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400';
			case 'transcode':
				return 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400';
			default:
				return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
		}
	}

	function levelClass(level: string): string {
		switch ((level ?? '').toLowerCase()) {
			case 'warning':
				return 'text-amber-400';
			case 'error':
			case 'critical':
				return 'text-red-400';
			default:
				return 'text-gray-300';
		}
	}

	function timeLabel(entry: LogEntry): string {
		if (!entry.timestamp) return '';
		const d = new Date(entry.timestamp);
		if (Number.isNaN(d.getTime())) return '';
		return d.toLocaleTimeString([], { hour12: false });
	}

	function isAtBottom(): boolean {
		if (viewEl === null) return true;
		return viewEl.scrollHeight - viewEl.scrollTop - viewEl.clientHeight < 24;
	}

	function onScroll(): void {
		following = isAtBottom();
	}

	function jumpToLatest(): void {
		following = true;
		scrollToBottom();
	}

	function scrollToBottom(): void {
		if (viewEl === null) return;
		viewEl.scrollTop = viewEl.scrollHeight;
	}

	$effect(() => {
		// Follow new lines (filtered.length as the reactive trigger) while
		// the user hasn't scrolled up.
		void filtered.length;
		if (following) scrollToBottom();
	});

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
		<div class="mt-3 flex flex-col gap-3">
			<div class="flex gap-1 rounded-lg bg-primary/5 p-1 dark:bg-primary/10" role="radiogroup" aria-label="Log filter">
				{#each FILTERS as f}
					<button
						type="button"
						role="radio"
						aria-checked={filter === f.key}
						data-testid="job-log-filter-{f.key}"
						onclick={() => { filter = f.key; }}
						class={segment(filter === f.key)}
					>{f.label}</button>
				{/each}
			</div>

			{#if log.error}
				<p class="text-sm text-red-600 dark:text-red-400">{log.error.message}</p>
			{:else if log.entries.length === 0}
				<p class="text-sm text-gray-500 dark:text-gray-400">No log lines for this job yet.</p>
			{:else}
				<div class="relative">
					<div
						bind:this={viewEl}
						onscroll={onScroll}
						data-testid="job-log-view"
						class="max-h-96 overflow-y-auto rounded-lg border border-primary/20 bg-black/90 p-3 font-mono text-xs dark:border-primary/20"
					>
						{#each filtered as entry, i (i)}
							{@const svc = logService(entry.service)}
							<div class="flex items-start gap-2 py-0.5" data-testid="job-log-line" data-service={svc}>
								<span class="shrink-0 text-gray-500 tabular-nums">{timeLabel(entry)}</span>
								<span class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold {chipClass(svc)}">
									{serviceLabel(svc)}
								</span>
								<span class="break-all {levelClass(entry.level)}">{entry.event}</span>
							</div>
						{/each}
					</div>
					{#if !following}
						<button
							type="button"
							onclick={jumpToLatest}
							data-testid="job-log-jump"
							class="absolute bottom-3 right-3 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-on-primary shadow-md"
						>
							Jump to latest
						</button>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</section>
