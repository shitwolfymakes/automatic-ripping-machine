<script lang="ts">
	import type { LogEntry } from '$lib/api/logs';
	import { logService, serviceLabel, type LogService } from '$lib/utils/log-service';

	interface Props {
		entries: LogEntry[];
		loading?: boolean;
		error?: Error | null;
		live?: boolean;
		search?: boolean;
		maxHeightClass?: string;
	}

	let {
		entries,
		loading = false,
		error = null,
		live = false,
		search = false,
		maxHeightClass = 'max-h-96'
	}: Props = $props();

	type Level = 'all' | 'error' | 'warning' | 'info' | 'debug';

	let serviceFilter = $state<'all' | LogService>('all');
	let levelFilter = $state<Level>('all');
	let searchText = $state('');
	let following = $state(true);
	let viewEl = $state<HTMLDivElement | null>(null);

	const SERVICE_FILTERS: { key: 'all' | LogService; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'backend', label: 'Backend' },
		{ key: 'ripper', label: 'Ripper' },
		{ key: 'transcode', label: 'Transcode' }
	];

	const LEVEL_FILTERS: { key: Level; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'error', label: 'Error' },
		{ key: 'warning', label: 'Warning' },
		{ key: 'info', label: 'Info' },
		{ key: 'debug', label: 'Debug' }
	];

	function levelOf(entry: LogEntry): string {
		return (entry.level ?? '').toLowerCase();
	}

	function matchesSearch(entry: LogEntry): boolean {
		if (!search || !searchText) return true;
		const needle = searchText.toLowerCase();
		return `${entry.event ?? ''} ${entry.logger ?? ''}`.toLowerCase().includes(needle);
	}

	const filtered = $derived(
		entries.filter((e) => {
			if (serviceFilter !== 'all' && logService(e.service) !== serviceFilter) return false;
			if (levelFilter !== 'all' && levelOf(e) !== levelFilter) return false;
			if (!matchesSearch(e)) return false;
			return true;
		})
	);

	const isFiltered = $derived(filtered.length !== entries.length);

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
</script>

<div class="flex flex-col gap-3">
	<div class="flex flex-wrap items-center gap-2">
		<div class="flex gap-1 rounded-lg bg-primary/5 p-1 dark:bg-primary/10" role="radiogroup" aria-label="Log filter">
			{#each SERVICE_FILTERS as f}
				<button
					type="button"
					role="radio"
					aria-checked={serviceFilter === f.key}
					data-testid="job-log-filter-{f.key}"
					onclick={() => {
						serviceFilter = f.key;
					}}
					class={segment(serviceFilter === f.key)}
				>{f.label}</button>
			{/each}
		</div>
		<div class="flex gap-1 rounded-lg bg-primary/5 p-1 dark:bg-primary/10" role="radiogroup" aria-label="Log level filter">
			{#each LEVEL_FILTERS as f}
				<button
					type="button"
					role="radio"
					aria-checked={levelFilter === f.key}
					data-testid="job-log-level-{f.key}"
					onclick={() => {
						levelFilter = f.key;
					}}
					class={segment(levelFilter === f.key)}
				>{f.label}</button>
			{/each}
		</div>
		{#if search}
			<input
				type="text"
				bind:value={searchText}
				placeholder="Filter lines"
				data-testid="job-log-search"
				class="ml-auto rounded-lg border border-primary/25 bg-primary/5 px-3 py-1.5 text-sm dark:border-primary/30 dark:bg-primary/10 dark:text-white"
			/>
		{/if}
	</div>

	{#if isFiltered}
		<p data-testid="job-log-count" class="text-xs text-gray-500 dark:text-gray-400">
			Showing {filtered.length} of {entries.length} lines
		</p>
	{/if}

	{#if error}
		<p class="text-sm text-red-600 dark:text-red-400">{error.message}</p>
	{:else if entries.length === 0}
		<p class="text-sm text-gray-500 dark:text-gray-400">No log lines for this job yet.</p>
	{:else}
		<div class="relative">
			<div
				bind:this={viewEl}
				onscroll={onScroll}
				data-testid="job-log-view"
				class="{maxHeightClass} overflow-y-auto rounded-lg border border-primary/20 bg-black/90 p-3 font-mono text-xs dark:border-primary/20"
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
